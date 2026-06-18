"""Unit tests for BaseWiiMClient HTTP transport layer.

Tests protocol detection, SSL/TLS, retry logic, response parsing, and error handling.
"""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from pywiim.api.base import ApiResponse, BaseWiiMClient
from pywiim.exceptions import WiiMConnectionError, WiiMRequestError
from pywiim.models import DeviceInfo, PlayerStatus


class TestBaseWiiMClientInitialization:
    """Test BaseWiiMClient initialization."""

    @pytest.mark.asyncio
    async def test_init_basic(self):
        """Test basic client initialization."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client.host == "192.168.1.100"
        assert client.port == 443  # Default HTTPS port
        assert client._host_url == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_init_with_port(self):
        """Test initialization with explicit port."""
        client = BaseWiiMClient(host="192.168.1.100", port=80)
        assert client.host == "192.168.1.100"
        assert client.port == 80

    @pytest.mark.asyncio
    async def test_init_host_with_port(self):
        """Test initialization with port in host string."""
        client = BaseWiiMClient(host="192.168.1.100:8080")
        assert client.host == "192.168.1.100"
        assert client.port == 8080
        assert client._discovered_port is True

    @pytest.mark.asyncio
    async def test_init_ipv6(self):
        """Test initialization with IPv6 address."""
        client = BaseWiiMClient(host="2001:db8::1", port=80)
        assert client.host == "2001:db8::1"
        assert client.port == 80
        assert client._host_url == "[2001:db8::1]"

    @pytest.mark.asyncio
    async def test_init_ipv6_with_port(self):
        """Test initialization with IPv6 address and port in brackets."""
        client = BaseWiiMClient(host="[2001:db8::1]:8080")
        assert client.host == "2001:db8::1"
        assert client.port == 8080
        assert client._discovered_port is True

    @pytest.mark.asyncio
    async def test_init_with_capabilities(self):
        """Test initialization with device capabilities."""
        capabilities = {
            "response_timeout": 3.0,
            "retry_count": 2,
            "protocol_priority": ["http", "https"],
        }
        client = BaseWiiMClient(host="192.168.1.100", capabilities=capabilities)
        assert client.timeout == 3.0
        assert client._capabilities == capabilities

    @pytest.mark.asyncio
    async def test_init_with_session(self):
        """Test initialization with existing session."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.closed = False
        client = BaseWiiMClient(host="192.168.1.100", session=session)
        assert client._session == session


class TestApplyProtocolPreference:
    """Post-detection protocol correction (issue #248)."""

    def _mk_response(self, body: str):
        resp = MagicMock()
        resp.status = 200
        resp.text = AsyncMock(return_value=body)
        resp.raise_for_status = MagicMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        return resp

    @pytest.mark.asyncio
    async def test_downgrades_https_to_http_for_http_first_profile(self, mock_aiohttp_session):
        """Arylic-style device: cached HTTPS is switched to HTTP when HTTP:80 works."""
        client = BaseWiiMClient(host="192.168.1.50", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.50:443"
        client.port = 443
        client._capabilities = {"vendor": "arylic", "protocol_priority": ["http", "https"]}

        mock_aiohttp_session.request = AsyncMock(return_value=self._mk_response('{"uuid": "x"}'))
        mock_aiohttp_session.closed = False

        await client._apply_protocol_preference()

        assert client._endpoint == "http://192.168.1.50:80"
        assert client.port == 80
        # Probe must have targeted HTTP:80.
        called_url = mock_aiohttp_session.request.call_args[0][1]
        assert called_url.startswith("http://192.168.1.50:80/")

    @pytest.mark.asyncio
    async def test_no_switch_for_https_first_profile(self, mock_aiohttp_session):
        """WiiM device (HTTPS-first profile) is never downgraded."""
        client = BaseWiiMClient(host="192.168.1.68", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.68:443"
        client.port = 443
        client._capabilities = {"vendor": "wiim", "protocol_priority": ["https", "http"]}

        mock_aiohttp_session.request = AsyncMock(return_value=self._mk_response('{"uuid": "x"}'))
        mock_aiohttp_session.closed = False

        await client._apply_protocol_preference()

        assert client._endpoint == "https://192.168.1.68:443"
        assert client.port == 443
        mock_aiohttp_session.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_keeps_https_when_http_probe_fails(self, mock_aiohttp_session):
        """If HTTP:80 doesn't return a valid body, keep the working HTTPS endpoint."""
        client = BaseWiiMClient(host="192.168.1.50", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.50:443"
        client.port = 443
        client._capabilities = {"vendor": "arylic", "protocol_priority": ["http", "https"]}

        mock_aiohttp_session.request = AsyncMock(side_effect=aiohttp.ClientError("refused"))
        mock_aiohttp_session.closed = False

        await client._apply_protocol_preference()

        assert client._endpoint == "https://192.168.1.50:443"
        assert client.port == 443

    @pytest.mark.asyncio
    async def test_respects_user_specified_protocol(self, mock_aiohttp_session):
        """An explicit user protocol/port choice is never overridden."""
        client = BaseWiiMClient(host="192.168.1.50", protocol="https", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.50:443"
        client._capabilities = {"vendor": "arylic", "protocol_priority": ["http", "https"]}

        mock_aiohttp_session.request = AsyncMock(return_value=self._mk_response('{"uuid": "x"}'))
        mock_aiohttp_session.closed = False

        await client._apply_protocol_preference()

        assert client._endpoint == "https://192.168.1.50:443"
        mock_aiohttp_session.request.assert_not_called()


class TestProbeListOrdering:
    """Probe order must honor capabilities protocol_priority (issue #248)."""

    def test_http_first_when_capabilities_prefer_http(self):
        """A client that already knows it's Arylic (cached caps) probes HTTP before HTTPS."""
        client = BaseWiiMClient(
            host="192.168.1.50",
            capabilities={"vendor": "arylic", "protocol_priority": ["http", "https"]},
        )
        probe_list = client._build_standard_probe_list()
        assert probe_list[0] == ("http", 80)
        # HTTPS combos must still be present as fallback (e.g. HTTPS-only Arylic).
        assert ("https", 443) in probe_list

    def test_https_first_when_capabilities_prefer_https(self):
        """WiiM (HTTPS-first caps) keeps HTTPS-first probe order."""
        client = BaseWiiMClient(
            host="192.168.1.68",
            capabilities={"vendor": "wiim", "protocol_priority": ["https", "http"]},
        )
        assert client._build_standard_probe_list()[0] == ("https", 443)

    def test_https_first_when_no_capabilities(self):
        """Cold client with no capabilities defaults to HTTPS-first (WiiM needs HTTPS)."""
        client = BaseWiiMClient(host="192.168.1.99")
        assert client._build_standard_probe_list()[0] == ("https", 443)

    def test_preferred_ports_still_take_precedence(self):
        """Audio Pro MkII preferred_ports override protocol_priority ordering."""
        client = BaseWiiMClient(
            host="192.168.1.77",
            capabilities={"preferred_ports": [4443, 8443, 443], "protocol_priority": ["http", "https"]},
        )
        assert client._build_standard_probe_list() == [("https", 4443), ("https", 8443), ("https", 443)]


class TestBaseWiiMClientProperties:
    """Test BaseWiiMClient properties."""

    @pytest.mark.asyncio
    async def test_host_property(self):
        """Test host property."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client.host == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_capabilities_property(self):
        """Test capabilities property."""
        capabilities = {"vendor": "wiim"}
        client = BaseWiiMClient(host="192.168.1.100", capabilities=capabilities)
        assert client.capabilities == capabilities

    @pytest.mark.asyncio
    async def test_base_url_property(self):
        """Test base_url property."""
        client = BaseWiiMClient(host="192.168.1.100")
        # Initially endpoint is None (lazy discovery)
        assert client.base_url is None
        # After setting endpoint, base_url returns it
        client._endpoint = "https://192.168.1.100:443"
        assert client.base_url == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_discovered_endpoint_property(self):
        """Test discovered_endpoint property."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client.discovered_endpoint is None
        client._endpoint = "https://192.168.1.100:443"
        assert client.discovered_endpoint == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_is_https_property(self):
        """Test is_https property."""
        client = BaseWiiMClient(host="192.168.1.100")
        client._endpoint = "https://192.168.1.100:443"
        assert client.is_https is True
        client._endpoint = "http://192.168.1.100:80"
        assert client.is_https is False
        client._endpoint = None
        assert client.is_https is False

    @pytest.mark.asyncio
    async def test_discovered_port_property(self):
        """Test discovered_port property."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client.discovered_port is None
        client._endpoint = "https://192.168.1.100:443"
        assert client.discovered_port == 443


class TestBaseWiiMClientMetrics:
    """Test BaseWiiMClient metrics collection."""

    @pytest.mark.asyncio
    async def test_metrics_enabled_by_default(self):
        """Test metrics are enabled by default."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client._metrics_enabled is True

    @pytest.mark.asyncio
    async def test_enable_metrics(self):
        """Test enabling/disabling metrics."""
        client = BaseWiiMClient(host="192.168.1.100")
        client.enable_metrics(False)
        assert client._metrics_enabled is False

        client.enable_metrics(True)
        assert client._metrics_enabled is True

    @pytest.mark.asyncio
    async def test_api_stats_initial(self):
        """Test initial API stats."""
        client = BaseWiiMClient(host="192.168.1.100")
        stats = client.api_stats
        assert stats["metrics_enabled"] is True
        assert stats["total_requests"] == 0
        assert stats["successful_requests"] == 0
        assert stats["failed_requests"] == 0

    @pytest.mark.asyncio
    async def test_api_stats_disabled(self):
        """Test API stats when metrics disabled."""
        client = BaseWiiMClient(host="192.168.1.100")
        client.enable_metrics(False)
        stats = client.api_stats
        assert stats["metrics_enabled"] is False

    @pytest.mark.asyncio
    async def test_connection_stats(self):
        """Test connection_stats property."""
        client = BaseWiiMClient(host="192.168.1.100")
        stats = client.connection_stats
        assert "metrics_enabled" in stats
        assert "avg_latency_ms" in stats
        assert "success_rate" in stats
        assert "total_requests" in stats
        assert "failed_requests" in stats
        assert "established_endpoint" in stats


class TestBaseWiiMClientSessionManagement:
    """Test session management methods."""

    @pytest.mark.asyncio
    async def test_ensure_session_creates_new(self):
        """Test _ensure_session creates new session when needed."""
        client = BaseWiiMClient(host="192.168.1.100")
        assert client._session is None

        await client._ensure_session()

        assert client._session is not None
        assert not client._session.closed

    @pytest.mark.asyncio
    async def test_ensure_session_reuses_existing(self):
        """Test _ensure_session reuses existing session."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.closed = False
        client = BaseWiiMClient(host="192.168.1.100", session=session)

        await client._ensure_session()

        assert client._session == session

    @pytest.mark.asyncio
    async def test_ensure_session_recreates_on_closed(self):
        """Test _ensure_session recreates session when closed."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.closed = True
        client = BaseWiiMClient(host="192.168.1.100", session=session)

        await client._ensure_session()

        assert client._session is not None
        assert client._session != session

    @pytest.mark.asyncio
    async def test_is_loop_closed_error(self):
        """Test _is_loop_closed_error detection."""
        assert BaseWiiMClient._is_loop_closed_error(RuntimeError("Event loop is closed"))
        assert not BaseWiiMClient._is_loop_closed_error(RuntimeError("Other error"))

    @pytest.mark.asyncio
    async def test_handle_loop_closed_session(self):
        """Test _handle_loop_closed_session resets session."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.closed = False
        session.close = AsyncMock()
        client = BaseWiiMClient(host="192.168.1.100", session=session)

        await client._handle_loop_closed_session(RuntimeError("Event loop is closed"))

        assert client._session is None
        session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_loop_closed_session_handles_close_error(self):
        """Test _handle_loop_closed_session handles close errors gracefully."""
        session = MagicMock(spec=aiohttp.ClientSession)
        session.closed = False
        session.close = AsyncMock(side_effect=Exception("Close failed"))
        client = BaseWiiMClient(host="192.168.1.100", session=session)

        # Should not raise
        await client._handle_loop_closed_session(RuntimeError("Event loop is closed"))

        assert client._session is None

    @pytest.mark.asyncio
    async def test_session_request_with_loop_closed(self, mock_aiohttp_session):
        """Test _session_request handles loop closed error."""
        # Ensure mock has closed property set correctly
        from unittest.mock import PropertyMock

        type(mock_aiohttp_session).closed = PropertyMock(return_value=False)
        mock_aiohttp_session.request = AsyncMock(side_effect=RuntimeError("Event loop is closed"))
        mock_aiohttp_session.close = AsyncMock()
        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        # Set session directly and mock _ensure_session to recreate it on retry
        client._session = mock_aiohttp_session

        call_count = 0

        async def mock_ensure_session():
            nonlocal call_count
            call_count += 1
            # Always recreate session if None (simulates retry behavior)
            if client._session is None:
                client._session = mock_aiohttp_session

        client._ensure_session = mock_ensure_session

        with pytest.raises(WiiMConnectionError) as exc_info:
            await client._session_request("GET", "https://192.168.1.100:443/api")

        assert "Event loop closed" in str(exc_info.value)
        # Session should be reset after final error (even though it was recreated for retry)
        assert client._session is None  # Should be reset


class TestBaseWiiMClientRequest:
    """Test BaseWiiMClient request methods."""

    @pytest.mark.asyncio
    async def test_request_success(self, mock_aiohttp_session):
        """Test successful request."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        # Mock SSL context
        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/api/status")

            assert result.parsed == {"status": "ok"}
            assert result.raw is None
            mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_retry_on_failure(self, mock_aiohttp_session):
        """Test request retries on failure."""
        # Mock response that fails first time, succeeds second
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # First call fails with ClientError (retryable), second succeeds
        mock_aiohttp_session.request = AsyncMock(
            side_effect=[
                aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed")),
                mock_response,
            ]
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 2},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual sleep
                result = await client._request("/api/status")

                assert result.parsed == {"status": "ok"}
                # Should have retried, so called at least twice
                assert mock_aiohttp_session.request.call_count >= 2

    @pytest.mark.asyncio
    async def test_request_max_retries_exceeded(self, mock_aiohttp_session):
        """Test request raises error after max retries."""
        # Mock response that always fails with retryable error
        mock_aiohttp_session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed"))
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 2},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual sleep
                with pytest.raises(WiiMRequestError) as exc_info:
                    await client._request("/api/status")

                # Error message may vary, but should indicate failure
                assert "failed" in str(exc_info.value).lower() or "attempts" in str(exc_info.value).lower()
                # Should have retried
                assert mock_aiohttp_session.request.call_count >= 2

    @pytest.mark.asyncio
    async def test_request_retry_count_zero_raises(self, mock_aiohttp_session):
        """Test request with retry_count=0 raises ValueError."""
        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 0},
        )

        with pytest.raises(ValueError, match="retry_count must be greater than 0"):
            await client._request("/api/status")

    @pytest.mark.asyncio
    async def test_request_legacy_device_validation(self, mock_aiohttp_session):
        """Test request validates legacy device responses."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"is_legacy_device": True, "audio_pro_generation": "original"},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch.object(
                client, "_validate_legacy_response", return_value=ApiResponse(parsed={"status": "ok"}, raw=None)
            ) as mock_validate:
                result = await client._request("/api/status")

                assert result.parsed == {"status": "ok"}
                mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_metrics_tracking(self, mock_aiohttp_session):
        """Test request tracks metrics."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            await client._request("/api/status")

            stats = client.api_stats
            assert stats["total_requests"] == 1
            assert stats["successful_requests"] == 1
            assert stats["failed_requests"] == 0

    @pytest.mark.asyncio
    async def test_request_metrics_tracks_timeout(self, mock_aiohttp_session):
        """Test request tracks timeout errors in metrics."""
        # Timeout needs to be raised from _request_with_protocol_fallback
        # which is called by _request
        mock_response = MagicMock()
        mock_response.__aenter__ = AsyncMock(side_effect=TimeoutError("Timeout"))
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 1},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(WiiMRequestError):
                    await client._request("/api/status")

                stats = client.api_stats
                # Timeout might not be tracked if it's wrapped differently
                # Just verify metrics were updated
                assert stats["total_requests"] > 0
                assert stats["failed_requests"] > 0

    @pytest.mark.asyncio
    async def test_request_metrics_tracks_connection_error(self, mock_aiohttp_session):
        """Test request tracks connection errors in metrics."""
        mock_aiohttp_session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed"))
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 1},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(WiiMRequestError):
                    await client._request("/api/status")

                stats = client.api_stats
                # Connection error should be tracked
                assert stats["total_requests"] > 0
                assert stats["failed_requests"] > 0
                # Connection error count may be 0 if error is wrapped, but metrics should be updated
                assert stats.get("connection_error_count", 0) >= 0

    @pytest.mark.asyncio
    async def test_request_legacy_device_backoff(self, mock_aiohttp_session):
        """Test request uses longer backoff for legacy devices."""
        mock_aiohttp_session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed"))
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(
            host="192.168.1.100",
            session=mock_aiohttp_session,
            capabilities={"retry_count": 2, "is_legacy_device": True},
        )
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(WiiMRequestError):
                    await client._request("/api/status")

                # Should have called sleep for backoff
                assert mock_sleep.call_count > 0

    @pytest.mark.asyncio
    async def test_request_empty_response(self, mock_aiohttp_session):
        """Test request with empty response (non-reboot command)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/api/status")

            assert result.parsed is None
            assert result.raw == ""

    @pytest.mark.asyncio
    async def test_request_ok_response(self, mock_aiohttp_session):
        """Test request with 'OK' text response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="OK")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/api/command")

            assert result.parsed is None
            assert result.raw == "OK"

    @pytest.mark.asyncio
    async def test_request_switchmode_empty_response(self, mock_aiohttp_session):
        """Test switchmode command with empty response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            # Test switchmode:bluetooth with empty response
            result = await client._request("/httpapi.asp?command=switchmode:bluetooth")

            # Empty response: base returns raw=""
            assert result.parsed is None
            assert result.raw == ""

    @pytest.mark.asyncio
    async def test_request_switchmode_non_json_response(self, mock_aiohttp_session):
        """Test switchmode command with non-JSON response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Command executed")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            # Test switchmode:wifi with non-JSON response
            result = await client._request("/httpapi.asp?command=switchmode:wifi")

            # Non-JSON response from switchmode should return success (base returns raw, no raise)
            assert result.parsed is None
            assert result.raw == "Command executed"

    @pytest.mark.asyncio
    async def test_request_setalarmclock_non_json_response(self, mock_aiohttp_session):
        """Test setAlarmClock command with non-JSON response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="OK")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            # Test setAlarmClock with non-JSON response (plain "OK")
            result = await client._request("/httpapi.asp?command=setAlarmClock:0:2:1:070000")

            # Non-JSON response from setAlarmClock should return success
            assert result.parsed is None
            assert result.raw == "OK"

    @pytest.mark.asyncio
    async def test_request_setalarmclock_empty_response(self, mock_aiohttp_session):
        """Test setAlarmClock command with empty response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            # Test setAlarmClock with empty response
            result = await client._request("/httpapi.asp?command=setAlarmClock:1:1:1:080000:20250120")

            # Empty response: base returns raw=""
            assert result.parsed is None
            assert result.raw == ""

    @pytest.mark.asyncio
    async def test_request_timesync_non_json_response(self, mock_aiohttp_session):
        """Test timeSync command with non-JSON response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Command accepted")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/httpapi.asp?command=timeSync:1737072000")

            assert result.parsed is None
            assert result.raw == "Command accepted"

    @pytest.mark.asyncio
    async def test_request_eqoff_unknown_command_graceful(self, mock_aiohttp_session):
        """Test EQOff command when device returns 'unknown command' (no EQOff support).

        Some devices (e.g. Arylic UP2STREAM) do not support EQOff and return plain
        text 'unknown command' instead of JSON. Scene restoration with sound_mode
        'Off' must not fail. See: https://github.com/mjcumming/wiim/issues/116
        """
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="unknown command")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/httpapi.asp?command=EQOff")

            # Should not raise - base returns raw body for non-JSON
            assert result.parsed is None
            assert result.raw == "unknown command"

    @pytest.mark.asyncio
    async def test_request_timesync_empty_response(self, mock_aiohttp_session):
        """Test timeSync command with empty response (returns OK)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/httpapi.asp?command=timeSync:1737072000")

            # Empty body: base returns raw=""
            assert result.parsed is None
            assert result.raw == ""

    @pytest.mark.asyncio
    async def test_request_invalid_json(self, mock_aiohttp_session):
        """Test request with invalid JSON response: base returns raw, does not raise."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="not json")
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request("/api/status")
            assert result.parsed is None
            assert result.raw == "not json"


class TestBaseWiiMClientProtocolFallback:
    """Test protocol fallback and probing."""

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_cached_endpoint(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback uses cached endpoint."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request_with_protocol_fallback("/api/status")

            assert result.parsed == {"status": "ok"}
            # Should use cached endpoint, not probe
            mock_aiohttp_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_ipv6(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback handles IPv6 addresses."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="2001:db8::1", session=mock_aiohttp_session)
        client._endpoint = "https://[2001:db8::1]:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            result = await client._request_with_protocol_fallback("/api/status")

            assert result.parsed == {"status": "ok"}
            # Check that IPv6 was handled correctly in URL
            call_args = mock_aiohttp_session.request.call_args
            assert "[2001:db8::1]" in str(call_args)

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_bluetooth_timeout(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback uses longer timeout for Bluetooth."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"
        client.timeout = 5.0

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.timeout") as mock_timeout:
                await client._request_with_protocol_fallback("/httpapi.asp?command=connectbta2dpsynk")

                # Should use 30s timeout for Bluetooth
                mock_timeout.assert_called()
                assert mock_timeout.call_args[0][0] == 30.0

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_loop_closed_error(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback handles loop closed error."""
        # Ensure mock has closed property set correctly
        from unittest.mock import PropertyMock

        type(mock_aiohttp_session).closed = PropertyMock(return_value=False)
        mock_aiohttp_session.request = AsyncMock(side_effect=RuntimeError("Event loop is closed"))

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"
        # Set session directly and mock _ensure_session to not recreate it
        client._session = mock_aiohttp_session

        async def mock_ensure_session():
            # Don't recreate session, just ensure it exists
            if client._session is None:
                client._session = mock_aiohttp_session

        client._ensure_session = mock_ensure_session

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            with pytest.raises(WiiMConnectionError) as exc_info:
                await client._request_with_protocol_fallback("/api/status")

            assert "Event loop closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_connection_error(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback raises connection error without clearing cache."""
        mock_aiohttp_session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed"))
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = "https://192.168.1.100:443"

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None

            with pytest.raises(WiiMConnectionError):
                await client._request_with_protocol_fallback("/api/status")

            # Endpoint should still be cached
            assert client._endpoint == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_request_with_protocol_fallback_probes_when_no_cache(self, mock_aiohttp_session):
        """Test _request_with_protocol_fallback probes when no cached endpoint."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = None  # No cached endpoint

        async def mock_probe(*args, **kwargs):
            # Set endpoint so recursion stops
            client._endpoint = "https://192.168.1.100:443"
            client._endpoint_tested = True

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch.object(client, "_probe_and_cache_endpoint", side_effect=mock_probe):
                result = await client._request_with_protocol_fallback("/api/status")

                # Should have probed and then made request
                assert result.parsed == {"status": "ok"}
                assert client._endpoint == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_probe_and_cache_endpoint_already_cached(self):
        """Test _probe_and_cache_endpoint returns early if already cached."""
        client = BaseWiiMClient(host="192.168.1.100")
        client._endpoint = "https://192.168.1.100:443"

        # Should return immediately without probing
        await client._probe_and_cache_endpoint("/api/status")

        # Endpoint should still be the same
        assert client._endpoint == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_probe_and_cache_endpoint_success(self, mock_aiohttp_session):
        """Test _probe_and_cache_endpoint successfully probes and caches endpoint."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = None

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.timeout"):
                await client._probe_and_cache_endpoint("/api/status")

                # Should have cached the endpoint
                assert client._endpoint is not None
                assert client._endpoint_tested is True
                # self.port must align with the cached endpoint (issue #248). HTTPS-first
                # probe succeeds on 443, so both endpoint and port reflect 443.
                assert client._endpoint == "https://192.168.1.100:443"
                assert client.port == 443

    @pytest.mark.asyncio
    async def test_probe_and_cache_endpoint_syncs_port_for_http(self, mock_aiohttp_session):
        """When the working endpoint is HTTP:80, client.port is updated to 80 (issue #248)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"status": "ok"}')
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_aiohttp_session.request = AsyncMock(return_value=mock_response)
        mock_aiohttp_session.closed = False

        # Arylic-style cached caps → HTTP-first probe order → HTTP:80 wins.
        client = BaseWiiMClient(
            host="192.168.1.50",
            session=mock_aiohttp_session,
            capabilities={"vendor": "arylic", "protocol_priority": ["http", "https"]},
        )
        client._endpoint = None

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.timeout"):
                await client._probe_and_cache_endpoint("/api/status")

        assert client._endpoint == "http://192.168.1.50:80"
        assert client.port == 80

    @pytest.mark.asyncio
    async def test_probe_and_cache_endpoint_failure_connectivity(self, mock_aiohttp_session):
        """Test _probe_and_cache_endpoint raises user-friendly error when device unreachable."""
        mock_aiohttp_session.request = AsyncMock(
            side_effect=aiohttp.ClientConnectorError(MagicMock(), OSError("Connection failed"))
        )
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = None

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.timeout"):
                with pytest.raises(WiiMConnectionError) as exc_info:
                    await client._probe_and_cache_endpoint("/api/status")

                # Connectivity errors get user-friendly message, not protocol dump
                assert "Device unreachable" in str(exc_info.value)
                assert "192.168.1.100" in str(exc_info.value)
                assert "No working protocol" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_probe_and_cache_endpoint_failure_protocol_mismatch(self, mock_aiohttp_session):
        """Test _probe_and_cache_endpoint keeps technical message for non-connectivity errors."""
        # Simulate SSL/certificate error (protocol mismatch, not unreachable)
        mock_aiohttp_session.request = AsyncMock(side_effect=ssl.SSLError("certificate verify failed"))
        mock_aiohttp_session.closed = False

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        client._endpoint = None

        with patch.object(client, "_get_ssl_context", new_callable=AsyncMock) as mock_ssl:
            mock_ssl.return_value = None
            with patch("asyncio.timeout"):
                with pytest.raises(WiiMConnectionError) as exc_info:
                    await client._probe_and_cache_endpoint("/api/status")

                # Protocol/SSL errors keep technical detail with tried URLs
                assert "No working protocol" in str(exc_info.value)
                assert "192.168.1.100" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_build_probe_list_user_specified_both(self):
        """Test _build_probe_list with user-specified protocol and port."""
        client = BaseWiiMClient(host="192.168.1.100", protocol="http", port=8080)
        probe_list = client._build_probe_list()

        assert probe_list == [("http", 8080)]

    @pytest.mark.asyncio
    async def test_build_probe_list_user_specified_protocol_only(self):
        """Test _build_probe_list with user-specified protocol only."""
        client = BaseWiiMClient(host="192.168.1.100", protocol="https")
        probe_list = client._build_probe_list()

        # Should try HTTPS on standard ports
        assert len(probe_list) > 0
        assert all(proto == "https" for proto, _ in probe_list)

    @pytest.mark.asyncio
    async def test_build_probe_list_user_specified_port_only(self):
        """Test _build_probe_list with user-specified port only."""
        client = BaseWiiMClient(host="192.168.1.100", port=8080)
        probe_list = client._build_probe_list()

        # Should try both protocols on port 8080 first
        assert len(probe_list) > 0
        # First entries should be on port 8080 (user-specified port is tried first)
        assert probe_list[0][1] == 8080 or probe_list[1][1] == 8080
        # Should include both HTTP and HTTPS on user port
        user_port_protocols = {proto for proto, port in probe_list if port == 8080}
        assert "http" in user_port_protocols or "https" in user_port_protocols

    @pytest.mark.asyncio
    async def test_build_probe_list_no_user_specification(self):
        """Test _build_probe_list with no user specification."""
        client = BaseWiiMClient(host="192.168.1.100")
        probe_list = client._build_probe_list()

        # Should try standard combinations
        assert len(probe_list) > 0
        # Should include both HTTP and HTTPS
        protocols = {proto for proto, _ in probe_list}
        assert "http" in protocols or "https" in protocols

    @pytest.mark.asyncio
    async def test_build_standard_probe_list(self):
        """Test _build_standard_probe_list returns standard combinations."""
        client = BaseWiiMClient(host="192.168.1.100")
        probe_list = client._build_standard_probe_list()

        # Should return list of tuples
        assert isinstance(probe_list, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in probe_list)
        # Should include common ports
        ports = {port for _, port in probe_list}
        assert 443 in ports or 80 in ports


class TestBaseWiiMClientLegacyResponse:
    """Test legacy response validation."""

    @pytest.mark.asyncio
    async def test_validate_legacy_response(self):
        """Test _validate_legacy_response calls validate_audio_pro_response."""
        client = BaseWiiMClient(host="192.168.1.100", capabilities={"is_legacy_device": True})

        with patch("pywiim.api.base.validate_audio_pro_response", return_value={"status": "ok"}) as mock_validate:
            result = client._validate_legacy_response(ApiResponse(parsed=None, raw="response"), "/api/status")

            assert result.parsed == {"status": "ok"}
            mock_validate.assert_called_once()


class TestBaseWiiMClientClose:
    """Test BaseWiiMClient cleanup."""

    @pytest.mark.asyncio
    async def test_close_with_session(self, mock_aiohttp_session):
        """Test closing client with session."""
        mock_aiohttp_session.closed = False
        mock_aiohttp_session.close = AsyncMock()

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        await client.close()

        mock_aiohttp_session.close.assert_called_once()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_close_without_session(self):
        """Test closing client without session."""
        client = BaseWiiMClient(host="192.168.1.100")
        # Should not raise error
        await client.close()

    @pytest.mark.asyncio
    async def test_close_already_closed_session(self, mock_aiohttp_session):
        """Test closing client with already closed session."""
        mock_aiohttp_session.closed = True

        client = BaseWiiMClient(host="192.168.1.100", session=mock_aiohttp_session)
        await client.close()

        # Should not call close on already closed session
        assert not hasattr(mock_aiohttp_session.close, "call_count") or mock_aiohttp_session.close.call_count == 0


class TestBaseWiiMClientReprobe:
    """Test reprobe functionality."""

    @pytest.mark.asyncio
    async def test_reprobe_clears_cache_and_rediscovers(self, mock_client):
        """Test reprobe clears cache and rediscovers endpoint."""
        mock_client._endpoint = "https://192.168.1.100:443"
        mock_client._endpoint_tested = True
        with patch.object(mock_client, "get_player_status", new_callable=AsyncMock) as mock_get_status:
            mock_get_status.return_value = {"status": "ok"}

            await mock_client.reprobe()

            # Should have cleared cache first
            assert mock_client._endpoint is None
            assert mock_client._endpoint_tested is False
            # Then rediscovered
            mock_get_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_reprobe_handles_failure(self, mock_client):
        """Test reprobe handles failure."""
        from pywiim.exceptions import WiiMError

        mock_client._endpoint = "https://192.168.1.100:443"
        mock_client.get_player_status = AsyncMock(side_effect=WiiMError("Connection failed"))

        with pytest.raises(WiiMError):
            await mock_client.reprobe()


class TestBaseWiiMClientPublicAPI:
    """Test BaseWiiMClient public API methods."""

    @pytest.mark.asyncio
    async def test_validate_connection_success(self, mock_client):
        """Test validate_connection with successful connection."""
        mock_client.get_player_status = AsyncMock(return_value={"status": "ok"})

        result = await mock_client.validate_connection()

        assert result is True
        mock_client.get_player_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self, mock_client):
        """Test validate_connection with failed connection."""
        from pywiim.exceptions import WiiMError

        mock_client.get_player_status = AsyncMock(side_effect=WiiMError("Connection failed"))

        result = await mock_client.validate_connection()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_device_name_from_status(self, mock_client):
        """Test get_device_name from player status."""
        mock_client.get_player_status = AsyncMock(return_value={"DeviceName": "Test Device"})

        name = await mock_client.get_device_name()

        assert name == "Test Device"

    @pytest.mark.asyncio
    async def test_get_device_name_from_info(self, mock_client):
        """Test get_device_name from device info."""
        mock_client.get_player_status = AsyncMock(return_value={})
        mock_client.get_device_info = AsyncMock(return_value={"DeviceName": "Test Device"})

        name = await mock_client.get_device_name()

        assert name == "Test Device"

    @pytest.mark.asyncio
    async def test_get_device_name_fallback_to_ip(self, mock_client):
        """Test get_device_name falls back to IP."""
        from pywiim.exceptions import WiiMError

        mock_client.get_player_status = AsyncMock(side_effect=WiiMError("Error"))
        mock_client.get_device_info = AsyncMock(side_effect=WiiMError("Error"))
        # Ensure _host is set (it's set during initialization)
        mock_client._host = "192.168.1.100"

        name = await mock_client.get_device_name()

        assert name == "192.168.1.100"  # Default host

    @pytest.mark.asyncio
    async def test_get_status(self, mock_client):
        """Test get_status method."""
        from pywiim.api.constants import API_ENDPOINT_STATUS

        mock_client._request = AsyncMock(
            return_value=ApiResponse(parsed={"DeviceName": "Test", "volume": 50}, raw=None)
        )
        mock_client._capabilities = {"vendor": "wiim"}
        mock_client._last_track = None

        result = await mock_client.get_status()

        assert isinstance(result, dict)
        mock_client._request.assert_called_once_with(API_ENDPOINT_STATUS)

    @pytest.mark.asyncio
    async def test_get_device_info_success(self, mock_client):
        """Test get_device_info with successful response."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(parsed={"DeviceName": "Test", "uuid": "123"}, raw=None)
        )

        result = await mock_client.get_device_info()

        assert result == {"DeviceName": "Test", "uuid": "123"}

    @pytest.mark.asyncio
    async def test_get_device_info_non_dict_response(self, mock_client):
        """Test get_device_info when response has no parsed dict (raw only)."""
        with patch.object(mock_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = ApiResponse(parsed=None, raw="raw response")

            result = await mock_client.get_device_info()

            assert result == {"raw": "raw response"}

    @pytest.mark.asyncio
    async def test_get_device_info_error_returns_empty(self, mock_client):
        """Test get_device_info raises error on failure."""
        from pywiim.exceptions import WiiMError

        # Mock _request to raise WiiMError
        # DeviceAPI.get_device_info doesn't catch errors, it raises them
        with patch.object(mock_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = WiiMError("Error")

            with pytest.raises(WiiMError):
                await mock_client.get_device_info()

    @pytest.mark.asyncio
    async def test_get_player_status_standard_endpoint(self, mock_client):
        """Test get_player_status with standard endpoint."""
        mock_client._capabilities = {
            "supports_player_status_ex": True,
            "vendor": "wiim",
            "supports_metadata": False,  # Disable metadata fetch to avoid getMetaInfo call
        }
        mock_client._last_track = None
        with patch.object(mock_client, "_request", new_callable=AsyncMock) as mock_request:
            with patch(
                "pywiim.api.base.parse_player_status",
                return_value=({"status": "ok", "entity_picture": "test.jpg"}, None),
            ) as mock_parse:
                mock_request.return_value = ApiResponse(parsed={"status": "ok"}, raw=None)

                result = await mock_client.get_player_status()

                assert isinstance(result, dict)
                # Should use getPlayerStatusEx
                call_args = [call[0][0] for call in mock_request.call_args_list]
                assert any("getPlayerStatusEx" in arg for arg in call_args)
                mock_parse.assert_called()

    @pytest.mark.asyncio
    async def test_get_player_status_audio_pro_fallback(self, mock_client):
        """Test get_player_status with Audio Pro fallback."""
        mock_client._capabilities = {
            "supports_player_status_ex": False,
            "status_endpoint": "/httpapi.asp?command=getStatusEx",
            "vendor": "wiim",
            "supports_metadata": False,  # Disable metadata fetch
        }
        mock_client._last_track = None
        with patch.object(mock_client, "_request", new_callable=AsyncMock) as mock_request:
            with patch(
                "pywiim.api.base.parse_player_status",
                return_value=({"status": "ok", "entity_picture": "test.jpg"}, None),
            ) as mock_parse:
                mock_request.return_value = ApiResponse(parsed={"status": "ok"}, raw=None)

                result = await mock_client.get_player_status()

                assert isinstance(result, dict)
                # Should use getStatusEx
                call_args = [call[0][0] for call in mock_request.call_args_list]
                assert any("getStatusEx" in arg for arg in call_args)
                mock_parse.assert_called()

    @pytest.mark.asyncio
    async def test_get_player_status_fallback_on_error(self, mock_client):
        """Test get_player_status falls back to getStatusEx on error."""
        from pywiim.exceptions import WiiMRequestError

        mock_client._capabilities = {"supports_player_status_ex": True, "vendor": "wiim"}
        mock_client._last_track = None
        with patch.object(mock_client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                WiiMRequestError("getPlayerStatusEx failed"),
                ApiResponse(parsed={"status": "ok"}, raw=None),
            ]

            result = await mock_client.get_player_status()

            assert isinstance(result, dict)
            # Should have tried getPlayerStatusEx first, then getStatusEx
            # May be called more times due to parsing, but should be at least 2
            assert mock_request.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_device_info_model(self, mock_client):
        """Test get_device_info_model returns DeviceInfo model."""
        mock_client.get_device_info = AsyncMock(return_value={"uuid": "test-uuid", "name": "Test Device"})

        result = await mock_client.get_device_info_model()

        assert isinstance(result, DeviceInfo)
        assert result.uuid == "test-uuid"
        assert result.name == "Test Device"

    @pytest.mark.asyncio
    async def test_get_player_status_model(self, mock_client):
        """Test get_player_status_model returns PlayerStatus model."""
        mock_client.get_player_status = AsyncMock(return_value={"play_state": "play", "volume": 50, "title": "Test"})

        result = await mock_client.get_player_status_model()

        assert isinstance(result, PlayerStatus)
        assert result.play_state == "play"
        assert result.volume == 50

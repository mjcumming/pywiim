"""Basic unit tests for UPnP client.

These are basic tests that mock the async_upnp_client dependencies.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from async_upnp_client.exceptions import UpnpError


class TestUpnpClient:
    """Test UpnpClient class."""

    def test_init(self):
        """Test UpnpClient initialization."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)

        assert client.host == "192.168.1.100"
        assert client.description_url == "http://192.168.1.100/description.xml"
        assert client._device is None
        assert client._dmr_device is None

    @pytest.mark.asyncio
    async def test_create_http(self):
        """Test creating UPnP client with HTTP description URL."""
        from pywiim.upnp.client import UpnpClient

        with (
            patch("pywiim.upnp.client.UpnpFactory") as mock_factory,
            patch("pywiim.upnp.client.ClientSession") as _mock_session,
            patch("pywiim.upnp.client.TCPConnector") as _mock_connector,
        ):
            mock_device = MagicMock()
            mock_av_transport = MagicMock()
            mock_rendering_control = MagicMock()

            mock_device.service = MagicMock(
                side_effect=lambda x: (
                    mock_av_transport
                    if "AVTransport" in x
                    else mock_rendering_control if "RenderingControl" in x else None
                )
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.async_create_device = AsyncMock(return_value=mock_device)
            mock_factory.return_value = mock_factory_instance

            client = await UpnpClient.create("192.168.1.100", "http://192.168.1.100/description.xml")

            assert client.host == "192.168.1.100"
            assert client._device == mock_device

    @pytest.mark.asyncio
    async def test_create_https(self):
        """Test creating UPnP client with HTTPS description URL."""
        from pywiim.upnp.client import UpnpClient

        with (
            patch("pywiim.upnp.client.UpnpFactory") as mock_factory,
            patch("pywiim.upnp.client.ClientSession") as _mock_session,
            patch("pywiim.upnp.client.TCPConnector") as _mock_connector,
        ):
            mock_device = MagicMock()
            mock_av_transport = MagicMock()
            mock_rendering_control = MagicMock()

            mock_device.service = MagicMock(
                side_effect=lambda x: (
                    mock_av_transport
                    if "AVTransport" in x
                    else mock_rendering_control if "RenderingControl" in x else None
                )
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.async_create_device = AsyncMock(return_value=mock_device)
            mock_factory.return_value = mock_factory_instance

            client = await UpnpClient.create("192.168.1.100", "https://192.168.1.100/description.xml")

            assert client.host == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_av_transport_property(self):
        """Test getting AVTransport service."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        client._av_transport_service = mock_service

        assert client.av_transport == mock_service

    @pytest.mark.asyncio
    async def test_rendering_control_property(self):
        """Test getting RenderingControl service."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        client._rendering_control_service = mock_service

        assert client.rendering_control == mock_service

    @pytest.mark.asyncio
    async def test_notify_server_property_not_started(self):
        """Test getting notify server when not started."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)

        with pytest.raises(RuntimeError, match="notify server not started"):
            _ = client.notify_server

    @pytest.mark.asyncio
    async def test_async_subscribe_service_not_available(self):
        """Test subscribing to service that's not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._av_transport_service = None

        with pytest.raises(UpnpError, match="Service.*not available"):
            await client.async_subscribe("unknown_service", timeout=1800)

    @pytest.mark.asyncio
    async def test_async_subscribe_notify_server_not_started(self):
        """Test subscribing when notify server not started."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._av_transport_service = MagicMock()
        client._notify_server = None

        with pytest.raises(UpnpError, match="Notify server not started"):
            await client.async_subscribe("avtransport", timeout=1800)

    @pytest.mark.asyncio
    async def test_unwind_notify_server(self):
        """Test unwinding notify server."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_server = MagicMock()
        mock_server.async_stop_server = AsyncMock()
        client._notify_server = mock_server

        await client.unwind_notify_server()

        assert client._notify_server is None
        mock_server.async_stop_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_unwind_notify_server_error(self):
        """Test unwinding notify server handles errors."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_server = MagicMock()
        mock_server.async_stop_server = AsyncMock(side_effect=Exception("Stop error"))
        client._notify_server = mock_server

        await client.unwind_notify_server()

        assert client._notify_server is None

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing UPnP client."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_server = MagicMock()
        mock_server.async_stop_server = AsyncMock()
        client._notify_server = mock_server
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        client._internal_session = mock_session

        await client.close()

        assert client._notify_server is None
        assert client._internal_session is None
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_internal_session(self):
        """Test closing when no internal session."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_server = MagicMock()
        mock_server.async_stop_server = AsyncMock()
        client._notify_server = mock_server
        client._internal_session = None

        await client.close()

        assert client._notify_server is None

    @pytest.mark.asyncio
    async def test_close_session_error(self):
        """Test closing handles session errors."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_server = MagicMock()
        mock_server.async_stop_server = AsyncMock()
        client._notify_server = mock_server
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock(side_effect=Exception("Close error"))
        client._internal_session = mock_session

        await client.close()

        assert client._internal_session is None

    @pytest.mark.asyncio
    async def test_async_subscribe_success(self):
        """Test successful subscription."""
        from datetime import timedelta

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.on_event = None
        client._av_transport_service = mock_service

        mock_notify_server = MagicMock()
        mock_notify_server.host = "192.168.1.100"
        mock_notify_server.port = 8000
        mock_event_handler = MagicMock()
        mock_event_handler.async_subscribe = AsyncMock(return_value=("sid-123", timedelta(seconds=1800)))
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        subscription = await client.async_subscribe("avtransport", timeout=1800)

        assert subscription.sid == "sid-123"
        assert subscription.timeout == 1800
        mock_event_handler.async_subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_subscribe_with_callback(self):
        """Test subscription with callback."""
        from datetime import timedelta

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        client._av_transport_service = mock_service

        mock_notify_server = MagicMock()
        mock_notify_server.host = "192.168.1.100"
        mock_notify_server.port = 8000
        mock_event_handler = MagicMock()
        mock_event_handler.async_subscribe = AsyncMock(return_value=("sid-123", timedelta(seconds=1800)))
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        def callback():
            pass

        await client.async_subscribe("avtransport", timeout=1800, sub_callback=callback)

        assert mock_service.on_event == callback

    @pytest.mark.asyncio
    async def test_async_subscribe_services_success(self):
        """Test subscribing to all services."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_dmr_device = MagicMock()
        mock_dmr_device.async_subscribe_services = AsyncMock()
        client._dmr_device = mock_dmr_device
        mock_notify_server = MagicMock()
        mock_notify_server.callback_url = "http://192.168.1.100:8000/notify"
        client._notify_server = mock_notify_server

        await client.async_subscribe_services()

        mock_dmr_device.async_subscribe_services.assert_called_once_with(auto_resubscribe=True)

    @pytest.mark.asyncio
    async def test_async_subscribe_services_no_dmr_device(self):
        """Test subscribing when DmrDevice not initialized."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._dmr_device = None

        with pytest.raises(UpnpError, match="DmrDevice not initialized"):
            await client.async_subscribe_services()

    @pytest.mark.asyncio
    async def test_async_subscribe_services_with_callback(self):
        """Test subscribing with event callback."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_dmr_device = MagicMock()
        mock_dmr_device.async_subscribe_services = AsyncMock()
        client._dmr_device = mock_dmr_device
        mock_notify_server = MagicMock()
        mock_notify_server.callback_url = "http://192.168.1.100:8000/notify"
        client._notify_server = mock_notify_server

        def callback():
            pass

        await client.async_subscribe_services(event_callback=callback)

        assert mock_dmr_device.on_event == callback

    @pytest.mark.asyncio
    async def test_async_subscribe_services_error(self):
        """Test subscribing handles errors."""
        from async_upnp_client.exceptions import UpnpResponseError

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_dmr_device = MagicMock()
        mock_dmr_device.async_subscribe_services = AsyncMock(side_effect=UpnpResponseError("Rejected", status=500))
        client._dmr_device = mock_dmr_device
        mock_notify_server = MagicMock()
        mock_notify_server.callback_url = "http://192.168.1.100:8000/notify"
        client._notify_server = mock_notify_server

        with pytest.raises(UpnpResponseError):
            await client.async_subscribe_services()

    @pytest.mark.asyncio
    async def test_async_renew_success(self):
        """Test renewing subscription."""
        from datetime import timedelta

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_notify_server = MagicMock()
        mock_event_handler = MagicMock()
        mock_event_handler.async_resubscribe = AsyncMock(return_value=("new-sid-456", timedelta(seconds=1800)))
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        result = await client.async_renew("avtransport", "old-sid-123", timeout=1800)

        assert result == ("new-sid-456", 1800)
        mock_event_handler.async_resubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_renew_no_notify_server(self):
        """Test renewing when notify server not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._notify_server = None

        result = await client.async_renew("avtransport", "sid-123", timeout=1800)

        assert result is None

    @pytest.mark.asyncio
    async def test_async_renew_error(self):
        """Test renewing handles errors."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_notify_server = MagicMock()
        mock_event_handler = MagicMock()
        mock_event_handler.async_resubscribe = AsyncMock(side_effect=Exception("Renew error"))
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        result = await client.async_renew("avtransport", "sid-123", timeout=1800)

        assert result is None

    @pytest.mark.asyncio
    async def test_async_unsubscribe_success(self):
        """Test unsubscribing."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_notify_server = MagicMock()
        mock_event_handler = MagicMock()
        mock_event_handler.async_unsubscribe = AsyncMock()
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        await client.async_unsubscribe("avtransport", "sid-123")

        mock_event_handler.async_unsubscribe.assert_called_once_with("sid-123")

    @pytest.mark.asyncio
    async def test_async_unsubscribe_no_notify_server(self):
        """Test unsubscribing when notify server not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._notify_server = None

        # Should not raise
        await client.async_unsubscribe("avtransport", "sid-123")

    @pytest.mark.asyncio
    async def test_async_unsubscribe_error(self):
        """Test unsubscribing handles errors."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_notify_server = MagicMock()
        mock_event_handler = MagicMock()
        mock_event_handler.async_unsubscribe = AsyncMock(side_effect=Exception("Unsubscribe error"))
        mock_notify_server.event_handler = mock_event_handler
        client._notify_server = mock_notify_server

        # Should not raise
        await client.async_unsubscribe("avtransport", "sid-123")

    @pytest.mark.asyncio
    async def test_async_call_action_success(self):
        """Test calling UPnP action."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"result": "ok"})
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.async_call_action("av_transport", "Play", {"InstanceID": 0})

        assert result == {"result": "ok"}
        mock_action.async_call.assert_called_once_with(InstanceID=0)

    @pytest.mark.asyncio
    async def test_async_call_action_accepts_avtransport_soap_name(self):
        """add_to_queue passes 'AVTransport'; that must resolve to _av_transport_service."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"result": "ok"})
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.async_call_action("AVTransport", "AddURIToQueue", {"InstanceID": 0})

        assert result == {"result": "ok"}
        mock_action.async_call.assert_called_once_with(InstanceID=0)

    @pytest.mark.asyncio
    async def test_async_call_action_service_not_available(self):
        """Test calling action when service not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._av_transport_service = None

        with pytest.raises(UpnpError, match="Service.*not available"):
            await client.async_call_action("av_transport", "Play", {})

    @pytest.mark.asyncio
    async def test_async_call_action_not_found(self):
        """Test calling action that doesn't exist."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.action = MagicMock(return_value=None)
        client._av_transport_service = mock_service

        with pytest.raises(UpnpError, match="Action.*not found"):
            await client.async_call_action("av_transport", "InvalidAction", {})

    @pytest.mark.asyncio
    async def test_async_call_action_missing_action_keyerror(self):
        """async_upnp_client raises KeyError when the action is absent from SCPD."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.action = MagicMock(side_effect=KeyError("AddURIToQueue"))
        client._av_transport_service = mock_service

        with pytest.raises(UpnpError, match="Action AddURIToQueue not found"):
            await client.async_call_action("AVTransport", "AddURIToQueue", {})

    @pytest.mark.asyncio
    async def test_get_media_info_success(self):
        """Test getting media info."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(
            return_value={
                "CurrentURI": "http://example.com/stream.mp3",
                "CurrentURIMetaData": "<didl>...</didl>",
                "TrackSource": "spotify",
            }
        )
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.get_media_info()

        assert "CurrentURI" in result
        assert result["TrackSource"] == "spotify"

    @pytest.mark.asyncio
    async def test_get_media_info_service_not_available(self):
        """Test getting media info when service not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._av_transport_service = None

        with pytest.raises(UpnpError, match="AVTransport service not available"):
            await client.get_media_info()

    @pytest.mark.asyncio
    async def test_get_transport_info_success(self):
        """Test getting transport info."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(
            return_value={
                "CurrentTransportState": "PLAYING",
                "CurrentTransportStatus": "OK",
                "CurrentSpeed": "1",
            }
        )
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.get_transport_info()

        assert result["CurrentTransportState"] == "PLAYING"
        assert result["CurrentTransportStatus"] == "OK"

    @pytest.mark.asyncio
    async def test_get_position_info_success(self):
        """Test getting position info."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(
            return_value={
                "Track": "1",
                "TrackDuration": "00:03:45",
                "RelTime": "00:01:30",
            }
        )
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.get_position_info()

        assert result["Track"] == "1"
        assert result["TrackDuration"] == "00:03:45"

    @pytest.mark.asyncio
    async def test_get_volume_success(self):
        """Test getting volume."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"CurrentVolume": 50})
        mock_service.action = MagicMock(return_value=mock_action)
        client._rendering_control_service = mock_service

        volume = await client.get_volume()

        assert volume == 50

    @pytest.mark.asyncio
    async def test_get_volume_service_not_available(self):
        """Test getting volume when service not available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._rendering_control_service = None

        with pytest.raises(UpnpError, match="RenderingControl service not available"):
            await client.get_volume()

    @pytest.mark.asyncio
    async def test_get_mute_success(self):
        """Test getting mute state."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"CurrentMute": True})
        mock_service.action = MagicMock(return_value=mock_action)
        client._rendering_control_service = mock_service

        muted = await client.get_mute()

        assert muted is True

    @pytest.mark.asyncio
    async def test_get_device_capabilities_success(self):
        """Test getting device capabilities."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(
            return_value={
                "PlayMedia": "NETWORK",
                "RecMedia": "NONE",
            }
        )
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        result = await client.get_device_capabilities()

        assert result["PlayMedia"] == "NETWORK"

    @pytest.mark.asyncio
    async def test_get_current_transport_actions_success(self):
        """Test getting current transport actions."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"Actions": "Play, Pause, Stop, Next, Previous"})
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        actions = await client.get_current_transport_actions()

        assert "Play" in actions
        assert "Pause" in actions
        assert "Stop" in actions

    @pytest.mark.asyncio
    async def test_get_current_transport_actions_empty(self):
        """Test getting transport actions when empty."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_action = MagicMock()
        mock_action.async_call = AsyncMock(return_value={"Actions": ""})
        mock_service.action = MagicMock(return_value=mock_action)
        client._av_transport_service = mock_service

        actions = await client.get_current_transport_actions()

        assert actions == []

    @pytest.mark.asyncio
    async def test_get_full_state_snapshot(self):
        """Test getting full state snapshot."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_av_service = MagicMock()
        mock_av_action = MagicMock()
        mock_av_action.async_call = AsyncMock(return_value={"CurrentTransportState": "PLAYING"})
        mock_av_service.action = MagicMock(return_value=mock_av_action)
        client._av_transport_service = mock_av_service

        mock_rc_service = MagicMock()
        mock_rc_volume_action = MagicMock()
        mock_rc_volume_action.async_call = AsyncMock(return_value={"CurrentVolume": 50})
        mock_rc_mute_action = MagicMock()
        mock_rc_mute_action.async_call = AsyncMock(return_value={"CurrentMute": False})
        mock_rc_service.action = MagicMock(
            side_effect=lambda x: mock_rc_volume_action if x == "GetVolume" else mock_rc_mute_action
        )
        client._rendering_control_service = mock_rc_service

        snapshot = await client.get_full_state_snapshot()

        assert "transport" in snapshot
        assert "media" in snapshot
        assert "position" in snapshot
        assert "volume" in snapshot
        assert "muted" in snapshot
        assert "available_actions" in snapshot


class TestGetInfoEx:
    """Tests for UpnpClient.get_info_ex (LinkPlay/Arylic extension)."""

    @pytest.mark.asyncio
    async def test_get_info_ex_via_action(self):
        """Uses async_upnp_client action when GetInfoEx is advertised."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.has_action = MagicMock(return_value=True)
        client._av_transport_service = mock_service
        client.async_call_action = AsyncMock(
            return_value={
                "TrackMetaData": (
                    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                    "<item><dc:title>Track</dc:title>"
                    "<upnp:albumArtURI>https://example.com/art.jpg</upnp:albumArtURI>"
                    "</item></DIDL-Lite>"
                )
            }
        )

        result = await client.get_info_ex()

        client.async_call_action.assert_called_once_with(
            "av_transport",
            "GetInfoEx",
            {"InstanceID": 0},
        )
        assert result["title"] == "Track"
        assert result["image_url"] == "https://example.com/art.jpg"

    @pytest.mark.asyncio
    async def test_get_info_ex_raw_soap_fallback(self):
        """Falls back to raw SOAP when GetInfoEx is not advertised."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.has_action = MagicMock(return_value=False)
        mock_service.control_url = "http://192.168.1.100:59152/upnp/control/rendertransport1"
        client._av_transport_service = mock_service

        soap_response = (
            '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><u:GetInfoExResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            '<TrackMetaData>&lt;DIDL-Lite xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;'
            "&lt;item&gt;&lt;upnp:albumArtURI&gt;https://example.com/raw.jpg&lt;/upnp:albumArtURI&gt;"
            "&lt;/item&gt;&lt;/DIDL-Lite&gt;</TrackMetaData>"
            "</u:GetInfoExResponse></s:Body></s:Envelope>"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=soap_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_response)
        client.session = mock_session

        result = await client.get_info_ex()

        assert result["image_url"] == "https://example.com/raw.jpg"

    @pytest.mark.asyncio
    async def test_get_info_ex_raw_soap_when_action_has_no_artwork(self):
        """Falls back to raw SOAP when advertised GetInfoEx omits usable artwork."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        mock_service = MagicMock()
        mock_service.has_action = MagicMock(return_value=True)
        mock_service.control_url = "http://192.168.1.100:59152/upnp/control/rendertransport1"
        client._av_transport_service = mock_service
        client.async_call_action = AsyncMock(return_value={"TrackMetaData": object()})

        soap_response = (
            '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            '<s:Body><u:GetInfoExResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            '<TrackMetaData>&lt;DIDL-Lite xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;'
            "&lt;item&gt;&lt;upnp:albumArtURI&gt;https://example.com/raw-action.jpg&lt;/upnp:albumArtURI&gt;"
            "&lt;/item&gt;&lt;/DIDL-Lite&gt;</TrackMetaData>"
            "</u:GetInfoExResponse></s:Body></s:Envelope>"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=soap_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_response)
        client.session = mock_session

        result = await client.get_info_ex()

        assert result["image_url"] == "https://example.com/raw-action.jpg"

    @pytest.mark.asyncio
    async def test_get_info_ex_no_service(self):
        """Raises UpnpError when AVTransport is unavailable."""
        from async_upnp_client.exceptions import UpnpError

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.100", "http://192.168.1.100/description.xml", None)
        client._av_transport_service = None

        with pytest.raises(UpnpError, match="AVTransport service not available"):
            await client.get_info_ex()


class TestGetControlDeviceInfo:
    """Tests for UpnpClient.get_control_device_info (Audio Pro-specific action)."""

    @pytest.mark.asyncio
    async def test_get_control_device_info_success(self):
        """Returns parsed result dict when RenderingControl service is available."""
        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.200", "https://192.168.1.200/description.xml", None)
        client._rendering_control_service = MagicMock()
        client.async_call_action = AsyncMock(return_value={"PlayMode": "44", "CurrentVolume": "50"})

        result = await client.get_control_device_info()

        client.async_call_action.assert_called_once_with(
            "rendering_control",
            "GetControlDeviceInfo",
            {"InstanceID": 0},
        )
        assert result["PlayMode"] == "44"
        assert result["CurrentVolume"] == "50"

    @pytest.mark.asyncio
    async def test_get_control_device_info_no_service(self):
        """Raises UpnpError when RenderingControl service is not available."""
        from async_upnp_client.exceptions import UpnpError

        from pywiim.upnp.client import UpnpClient

        client = UpnpClient("192.168.1.200", "https://192.168.1.200/description.xml", None)
        client._rendering_control_service = None

        with pytest.raises(UpnpError, match="RenderingControl service not available"):
            await client.get_control_device_info()

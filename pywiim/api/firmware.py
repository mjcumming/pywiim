"""Firmware detection and update checking helpers for WiiM HTTP client.

This mixin handles firmware version detection, parsing, and update availability checking.

Update Installation:
- Basic LinkPlay devices: Updates cannot be installed via API. If an update is available
  and already downloaded, rebooting the device will install it.
- WiiM devices only: Updates can be installed via API using getMvRemoteUpdateStart
  and related commands. See install_firmware_update() for details.

It assumes the base client provides the `_request` coroutine and device info access.
"""

from __future__ import annotations

import logging
import re
from typing import Any, cast

_LOGGER = logging.getLogger(__name__)


def parse_firmware_version(firmware_str: str | None) -> dict[str, Any] | None:
    """Parse firmware version string into components.

    Handles various firmware version formats:
    - WiiM: "5.0.123456" (major.minor.build)
    - Legacy: "1.56", "2.0.1", etc.
    - Audio Pro: Various formats

    Args:
        firmware_str: Firmware version string from device

    Returns:
        Dictionary with parsed components:
        - major: Major version number (int)
        - minor: Minor version number (int)
        - build: Build number (int, if available)
        - patch: Patch version (int, if available)
        - raw: Original firmware string
        - formatted: Formatted version string
        Or None if firmware_str is empty/invalid
    """
    if not firmware_str or not isinstance(firmware_str, str):
        return None

    firmware_str = firmware_str.strip()
    if not firmware_str or firmware_str in ("0", "-", "", "unknown"):
        return None

    # Try to parse common version formats
    # Format 1: "5.0.123456" (major.minor.build)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", firmware_str)
    if match:
        return {
            "major": int(match.group(1)),
            "minor": int(match.group(2)),
            "build": int(match.group(3)),
            "raw": firmware_str,
            "formatted": firmware_str,
        }

    # Format 2: "5.0" (major.minor)
    match = re.match(r"^(\d+)\.(\d+)$", firmware_str)
    if match:
        return {
            "major": int(match.group(1)),
            "minor": int(match.group(2)),
            "build": None,
            "raw": firmware_str,
            "formatted": firmware_str,
        }

    # Format 3: "1.56" (legacy format)
    match = re.match(r"^(\d+)\.(\d+)$", firmware_str)
    if match:
        return {
            "major": int(match.group(1)),
            "minor": int(match.group(2)),
            "build": None,
            "raw": firmware_str,
            "formatted": firmware_str,
        }

    # Format 4: "2.0.1" (major.minor.patch)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", firmware_str)
    if match:
        return {
            "major": int(match.group(1)),
            "minor": int(match.group(2)),
            "patch": int(match.group(3)),
            "raw": firmware_str,
            "formatted": firmware_str,
        }

    # Fallback: return raw string
    _LOGGER.debug("Could not parse firmware version format: %s", firmware_str)
    return {
        "major": None,
        "minor": None,
        "build": None,
        "raw": firmware_str,
        "formatted": firmware_str,
    }


def compare_firmware_versions(current: str, latest: str) -> int:
    """Compare two firmware version strings.

    Args:
        current: Current firmware version string
        latest: Latest firmware version string

    Returns:
        -1 if current < latest (update available)
        0 if current == latest (up to date)
        1 if current > latest (newer than reported latest, unusual)
    """
    current_parsed = parse_firmware_version(current)
    latest_parsed = parse_firmware_version(latest)

    if not current_parsed or not latest_parsed:
        # Can't parse, do string comparison
        if current == latest:
            return 0
        return -1 if current < latest else 1

    # Compare major version
    if current_parsed["major"] is not None and latest_parsed["major"] is not None:
        if current_parsed["major"] < latest_parsed["major"]:
            return -1
        if current_parsed["major"] > latest_parsed["major"]:
            return 1

    # Compare minor version
    if current_parsed["minor"] is not None and latest_parsed["minor"] is not None:
        if current_parsed["minor"] < latest_parsed["minor"]:
            return -1
        if current_parsed["minor"] > latest_parsed["minor"]:
            return 1

    # Compare build/patch if available
    current_build = current_parsed.get("build") or current_parsed.get("patch")
    latest_build = latest_parsed.get("build") or latest_parsed.get("patch")

    if current_build is not None and latest_build is not None:
        if current_build < latest_build:
            return -1
        if current_build > latest_build:
            return 1

    return 0


class FirmwareAPI:
    """Firmware detection and update checking helpers.

    This mixin provides methods for detecting firmware versions, checking for updates,
    and parsing version strings.

    Update Installation:
    - Basic LinkPlay devices: Updates cannot be installed via API. If an update is
      available and already downloaded, rebooting the device will install it.
      Use DiagnosticsAPI.reboot() to trigger installation.
    - WiiM devices only: Updates can be installed via API using install_firmware_update()
      and related methods. These methods check for updates, download them, and install
      them automatically. WARNING: Do not power off the device during installation!
    """

    async def get_firmware_info(self) -> dict[str, Any]:
        """Get comprehensive firmware information.

        Returns:
            Dictionary containing:
            - current_version: Current firmware version string
            - parsed_version: Parsed version components (major, minor, build, etc.)
            - latest_version: Latest available version (if known)
            - update_available: Boolean indicating if update is available
            - release_date: Firmware release date (if available)
            - mcu_version: MCU firmware version (if available)
            - dsp_version: DSP firmware version (if available)

        Raises:
            WiiMError: If the request fails.
        """
        try:
            device_info = await self.get_device_info_model()  # type: ignore[attr-defined]
        except Exception as err:
            _LOGGER.debug("Could not get device info for firmware info: %s", err)
            # Fallback to firmware endpoint only
            firmware_str = await self.get_firmware_version()  # type: ignore[attr-defined]
            return {
                "current_version": firmware_str,
                "parsed_version": parse_firmware_version(firmware_str),
                "latest_version": None,
                "update_available": False,
                "release_date": None,
                "mcu_version": None,
                "dsp_version": None,
            }

        firmware_str = device_info.firmware or ""
        latest_version = device_info.latest_version
        version_update = device_info.version_update

        # Determine if update is available
        # version_update="1" means update is available and downloaded
        # version_update="0" or None means no update
        update_available = False
        if version_update:
            update_available = str(version_update).strip() == "1"
        elif latest_version and firmware_str:
            # Fallback: compare versions if update flag not available
            comparison = compare_firmware_versions(firmware_str, latest_version)
            update_available = comparison < 0

        return {
            "current_version": firmware_str,
            "parsed_version": parse_firmware_version(firmware_str),
            "latest_version": (
                latest_version if latest_version and str(latest_version).strip() not in ("0", "-", "") else None
            ),
            "update_available": update_available,
            "release_date": device_info.release_date,
            "mcu_version": device_info.mcu_ver,
            "dsp_version": device_info.dsp_ver,
        }

    async def check_for_updates(self) -> bool:
        """Check if a firmware update is available.

        Returns:
            True if an update is available and ready to install, False otherwise.

        Raises:
            WiiMError: If the request fails.
        """
        firmware_info = await self.get_firmware_info()
        update_available = firmware_info.get("update_available", False)
        return bool(update_available)

    async def get_update_status(self) -> dict[str, Any]:
        """Get detailed firmware update status.

        Returns:
            Dictionary containing:
            - update_available: Boolean indicating if update is available
            - current_version: Current firmware version
            - latest_version: Latest available version
            - update_ready: True if update is downloaded and ready to install
            - can_install: True if update can be installed

        Note:
            - Basic LinkPlay devices: If an update is available and downloaded,
              rebooting the device will install it. Use the reboot() method from
              DiagnosticsAPI to trigger installation.
            - WiiM devices only: Use install_firmware_update() to install updates
              via API. This method checks for updates, downloads them, and installs
              them automatically.
        """
        firmware_info = await self.get_firmware_info()
        update_available = firmware_info.get("update_available", False)

        return {
            "update_available": update_available,
            "current_version": firmware_info.get("current_version"),
            "latest_version": firmware_info.get("latest_version"),
            "update_ready": update_available,  # If available, it's ready (downloaded)
            "can_install": update_available,  # Can install via reboot
        }

    async def is_firmware_version_at_least(self, required_version: str) -> bool:
        """Check if current firmware version meets minimum requirement.

        Args:
            required_version: Minimum required firmware version (e.g., "4.0", "5.0.123456")

        Returns:
            True if current firmware >= required version, False otherwise.
            Returns False if firmware version cannot be determined.

        Raises:
            WiiMError: If the request fails.
        """
        try:
            firmware_info = await self.get_firmware_info()
            current_version = firmware_info.get("current_version")
            if not current_version:
                _LOGGER.debug("Firmware version not available for comparison")
                return False

            comparison = compare_firmware_versions(current_version, required_version)
            # compare_firmware_versions returns:
            # -1 if current < required (needs update)
            # 0 if current == required (meets requirement)
            # 1 if current > required (exceeds requirement)
            # We want True if current >= required, so comparison >= 0
            return comparison >= 0

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not compare firmware versions: %s", err)
            return False

    # === WiiM-Specific Firmware Update Installation ===
    # These methods are only available on WiiM devices

    async def _ensure_wiim_device(self) -> None:
        """Ensure device supports firmware installation, raise error if not.

        Uses device capabilities to check if firmware installation is supported.
        This is only available on WiiM devices.

        Raises:
            WiiMError: If device does not support firmware installation.
        """
        # Check capabilities first (fast path, uses cached capabilities)
        if hasattr(self, "_capabilities") and self._capabilities:
            supports_install = self._capabilities.get("supports_firmware_install", False)
            if supports_install:
                return  # Device supports firmware installation

        # Fallback: check if device is WiiM (capabilities might not be set yet)
        # This should rarely happen as capabilities are set during client initialization
        try:
            device_info = await self.get_device_info_model()  # type: ignore[attr-defined]
            from ..capabilities import is_wiim_device

            if not is_wiim_device(device_info):
                from ..exceptions import WiiMError

                raise WiiMError(
                    "Firmware update installation is only available on WiiM devices. "
                    f"Detected device: {device_info.model or 'unknown'}. "
                    "For other devices, use reboot() after an update is downloaded."
                )
        except Exception as err:
            # If we can't check, assume it's not supported to be safe
            from ..exceptions import WiiMError

            raise WiiMError(
                f"Firmware update installation is not supported on this device. "
                f"Could not verify device capabilities: {err}"
            ) from err

    async def check_for_updates_wiim(self) -> dict[str, Any]:
        """Check for firmware updates (WiiM devices only).

        Uses the WiiM-specific getMvRemoteUpdateStartCheck command to search
        for available firmware updates.

        Returns:
            Dictionary containing update check results. Exact format depends on device response.

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        await self._ensure_wiim_device()
        result = await self._request("/httpapi.asp?command=getMvRemoteUpdateStartCheck")  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})

    async def install_firmware_update(self) -> None:
        """Install firmware update (WiiM devices only).

        This method:
        1. Checks for available updates
        2. Downloads the update if available
        3. Installs the update automatically

        WARNING: DO NOT POWER OFF THE DEVICE DURING THIS PROCESS!
        The device will reboot automatically after installation completes.

        The installation process can take several minutes. The device may become
        unresponsive during installation. This is normal behavior.

        Raises:
            WiiMError: If device is not a WiiM device, no update is available,
                or the installation process fails.
        """
        await self._ensure_wiim_device()

        _LOGGER.warning(
            "Starting firmware update installation on WiiM device. " "DO NOT POWER OFF THE DEVICE DURING THIS PROCESS!"
        )

        try:
            # Start the update process (downloads and installs)
            await self._request("/httpapi.asp?command=getMvRemoteUpdateStart")  # type: ignore[attr-defined]
            _LOGGER.info("Firmware update installation started. Device will reboot when complete.")
        except Exception as err:
            _LOGGER.error("Firmware update installation failed: %s", err)
            raise

    async def get_update_download_status(self) -> dict[str, Any]:
        """Get firmware update download status (WiiM devices only).

        Returns the download progress and status of the firmware update process.

        Status values (from OpenAPI docs):
        - 10: Under review
        - 20: (unknown)
        - 21: Verification of downloaded update file failed
        - 22: Downloading the update file failed
        - 23: Verification of downloaded update file failed
        - 25: Start downloading
        - 27: Download complete
        - 30: Downloading and verification completed

        Returns:
            Dictionary containing download status information.

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        await self._ensure_wiim_device()
        result = await self._request("/httpapi.asp?command=getMvRemoteUpdateStatus")  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})

    async def get_update_install_status(self) -> dict[str, Any]:
        """Get firmware update installation status (WiiM devices only).

        Returns the installation progress and status of the firmware update process.

        Response format (from OpenAPI docs):
        {
          "status": "0",  # State code
          "progress": "50"  # Progress percentage (0-100)
        }

        Returns:
            Dictionary containing:
            - status: Installation state code (string)
            - progress: Installation progress percentage 0-100 (string)

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        await self._ensure_wiim_device()
        result = await self._request("/httpapi.asp?command=getMvRomBurnPrecent")  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})

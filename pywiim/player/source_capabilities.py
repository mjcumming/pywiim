"""Centralized source capability definitions.

This module defines what playback capabilities are available for each source type.
Capabilities are dynamic and depend on the current playback source, unlike device
capabilities which are static (probed once at init).

Design rationale:
- Single source of truth for source-based capabilities
- Consistent behavior across all capability properties
- Easy to add/modify sources
- Self-documenting (the table shows exactly what each source supports)
"""

from __future__ import annotations

from enum import Flag, auto

__all__ = [
    "SourceCapability",
    "SOURCE_CAPABILITIES",
    "DEFAULT_CAPABILITIES",
    "NATIVE_NOTIFICATION_PROMPT_SOURCES",
    "get_source_capabilities",
    "source_supports_native_notification_prompt",
]


class SourceCapability(Flag):
    """Capabilities that depend on the current playback source.

    These are dynamic capabilities that change based on what's currently playing,
    unlike device capabilities (supports_eq, supports_presets) which are static.
    """

    NONE = 0

    # Individual capabilities
    SHUFFLE = auto()  # Device can control shuffle mode
    REPEAT = auto()  # Device can control repeat mode
    NEXT_TRACK = auto()  # Skip to next track makes sense
    PREVIOUS_TRACK = auto()  # Skip to previous track makes sense
    SEEK = auto()  # Seeking within track makes sense

    # Common capability combinations
    FULL_CONTROL = SHUFFLE | REPEAT | NEXT_TRACK | PREVIOUS_TRACK | SEEK
    """Full playback control - device manages the queue."""

    TRACK_CONTROL = NEXT_TRACK | PREVIOUS_TRACK | SEEK
    """Track control only - external app controls shuffle/repeat."""


# Define capabilities per source type
# This is the single source of truth for source-based capabilities
SOURCE_CAPABILITIES: dict[str, SourceCapability] = {
    # =========================================================================
    # STREAMING SERVICES - Full control (they manage their own queue)
    # Note: queue_count=0 is normal for these (they don't expose queue via API)
    # =========================================================================
    "spotify": SourceCapability.FULL_CONTROL,
    "amazon": SourceCapability.FULL_CONTROL,
    "tidal": SourceCapability.FULL_CONTROL,
    "qobuz": SourceCapability.FULL_CONTROL,
    "deezer": SourceCapability.FULL_CONTROL,
    "pandora": SourceCapability.FULL_CONTROL,
    # =========================================================================
    # LOCAL PLAYBACK - Full control (device manages local queue)
    # =========================================================================
    "usb": SourceCapability.FULL_CONTROL,
    "wifi": SourceCapability.FULL_CONTROL,
    "network": SourceCapability.FULL_CONTROL,
    "http": SourceCapability.FULL_CONTROL,
    "playlist": SourceCapability.FULL_CONTROL,
    "preset": SourceCapability.FULL_CONTROL,
    "udisk": SourceCapability.FULL_CONTROL,  # USB disk (alternative name)
    # =========================================================================
    # EXTERNAL CASTING - Track control only
    # Commands are forwarded to source app; shuffle/repeat controlled by app
    # =========================================================================
    "airplay": SourceCapability.TRACK_CONTROL,
    "bluetooth": SourceCapability.TRACK_CONTROL,
    "dlna": SourceCapability.TRACK_CONTROL,
    "lyrion": SourceCapability.FULL_CONTROL,  # Lyrion Music Server / LMS (Squeezelite)
    "cast": SourceCapability.TRACK_CONTROL,  # Chromecast
    "chromecast": SourceCapability.TRACK_CONTROL,
    # =========================================================================
    # MULTIROOM - Track control (commands route through Group to master)
    # Same as play/pause - we route the command, master handles it
    # =========================================================================
    "multiroom": SourceCapability.TRACK_CONTROL,
    # =========================================================================
    # LIVE RADIO - No track control (continuous stream, no "next" concept)
    # linkplay_radio: WiiM Home built-in radio (BBC, etc.); use play_url for TTS
    # =========================================================================
    "tunein": SourceCapability.NONE,
    "iheartradio": SourceCapability.NONE,
    "radio": SourceCapability.NONE,
    "internetradio": SourceCapability.NONE,
    "webradio": SourceCapability.NONE,
    "linkplay_radio": SourceCapability.NONE,
    # =========================================================================
    # PHYSICAL INPUTS - No control (passthrough audio, no tracks)
    # =========================================================================
    "line_in": SourceCapability.NONE,
    "linein": SourceCapability.NONE,  # Alternative spelling
    "line-in": SourceCapability.NONE,  # Alternative spelling
    "optical": SourceCapability.NONE,
    "coaxial": SourceCapability.NONE,
    "coax": SourceCapability.NONE,  # Alternative spelling
    "aux": SourceCapability.NONE,
    "hdmi": SourceCapability.NONE,
    "phono": SourceCapability.NONE,  # WiiM Ultra turntable input
    "rca": SourceCapability.NONE,  # Audio Pro RCA line input (mode 44)
    "line_in_2": SourceCapability.NONE,
    "linein_2": SourceCapability.NONE,
}

# Default capabilities for unknown sources (permissive approach)
# If we don't recognize the source, assume full control - commands will
# either work or fail gracefully on the device
DEFAULT_CAPABILITIES = SourceCapability.FULL_CONTROL

# Sources where firmware-native playPromptUrl notifications are expected to work.
# These sources are device-controlled playback contexts where LinkPlay can duck
# and restore audio around the prompt.
NATIVE_NOTIFICATION_PROMPT_SOURCES: set[str] = {
    "wifi",
    "network",
    "http",
    "usb",
    "udisk",
    "tunein",
    "iheartradio",
    "radio",
    "internetradio",
    "webradio",
    "custompushurl",
    "preset",
    "playlist",
}


def get_source_capabilities(source: str | None) -> SourceCapability:
    """Get capabilities for a given source.

    Args:
        source: Source name (e.g., "spotify", "line_in", "tunein").
                Case-insensitive. Returns NONE if source is None.

    Returns:
        SourceCapability flags indicating what's supported for this source.

    Example:
        >>> caps = get_source_capabilities("spotify")
        >>> SourceCapability.SHUFFLE in caps
        True
        >>> SourceCapability.NEXT_TRACK in caps
        True

        >>> caps = get_source_capabilities("tunein")
        >>> SourceCapability.NEXT_TRACK in caps
        False
    """
    if not source:
        return SourceCapability.NONE

    return SOURCE_CAPABILITIES.get(source.lower(), DEFAULT_CAPABILITIES)


def source_supports_native_notification_prompt(source: str | None) -> bool:
    """Return whether source supports native playPromptUrl behavior.

    Args:
        source: Current source name from player status.

    Returns:
        True when source is known to support firmware-native prompt playback.
    """
    if not source:
        return False

    return source.lower() in NATIVE_NOTIFICATION_PROMPT_SOURCES

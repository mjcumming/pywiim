#!/usr/bin/env python3
"""Real-device test for PlayQueue auto-advance (wiim #268).

Clears the queue, enqueues two short MP3s, starts at index 0, then watches
whether playback advances to track 2 instead of going idle after track 1.

Usage:
    python scripts/debug/test_playqueue_auto_advance.py <device_ip>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pywiim import Player, WiiMClient
from pywiim.discovery import discover_via_ssdp
from pywiim.upnp.client import UpnpClient

URL_1 = "https://samplelib.com/mp3/sample-3s.mp3"
URL_2 = "https://samplelib.com/mp3/sample-9s.mp3"
POLL_SECONDS = 45


def _looks_like_track2(player: Player) -> bool:
    """Return True when overlay/title/url indicate the second queued clip."""
    title = (player.media_title or "").lower()
    content_id = (player.media_content_id or "").lower()
    if player.queue_position == 1:
        return True
    return "sample-9s" in title or "sample-9s" in content_id or URL_2.lower() in content_id


async def test_playqueue_auto_advance(host: str) -> bool:
    """Enqueue two clips and verify PlayQueue advances past the first."""
    print(f"Testing PlayQueue auto-advance on {host}...")
    print()

    client = WiiMClient(host=host)
    upnp_client = None

    try:
        print("Getting device info...")
        device_info = await client.get_device_info_model()
        print(f"   Device: {device_info.name}")
        print(f"   Model: {device_info.model}")
        print(f"   Firmware: {device_info.firmware}")

        print()
        print("Discovering UPnP services...")
        devices = await discover_via_ssdp(timeout=3, target=host)
        if not devices:
            print(f"   No UPnP device found for {host}; trying default description URL")
            description_url = f"http://{host}:49152/description.xml"
        else:
            device = devices[0]
            description_url = device.location
            print(f"   Found UPnP device: {device.name}")
            print(f"   Description URL: {description_url}")

        print()
        print("Creating UPnP client...")
        upnp_client = await UpnpClient.create(host, description_url)
        print(f"   AVTransport: {upnp_client.av_transport is not None}")
        print(f"   PlayQueue: {upnp_client.play_queue is not None}")

        print()
        print("Creating Player...")
        player = Player(client, upnp_client=upnp_client)
        await player.refresh()
        print(f"   Player: {player.device_name} ({player.play_state})")
        print(f"   supports_queue_add: {player.supports_queue_add}")

        print()
        print("Clearing queue...")
        await player.clear_queue()

        print(f"Adding track 1: {URL_1}")
        try:
            await player.play_url(URL_1, enqueue="add")
        except Exception as err:
            print(f"FAIL: could not enqueue track 1: {err}")
            return False

        print(f"Adding track 2: {URL_2}")
        try:
            await player.play_url(URL_2, enqueue="add")
        except Exception as err:
            print(f"FAIL: could not enqueue track 2: {err}")
            return False

        print("Starting play_queue(0)...")
        await player.play_queue(0)
        print(f"   queue_count: {player.queue_count}")
        print(f"   queue_position: {player.queue_position}")

        saw_playing = False
        print()
        print(f"Polling refresh() every 1s for up to {POLL_SECONDS}s...")
        for elapsed in range(POLL_SECONDS):
            await player.refresh()
            state = player.play_state
            title = player.media_title
            content_id = player.media_content_id
            print(
                f"   t={elapsed:02d}s state={state} title={title!r} "
                f"pos={player.queue_position} count={player.queue_count} url={content_id}"
            )

            if player.is_playing or (state or "").lower() in {"play", "playing", "buffering", "loading"}:
                saw_playing = True

            if _looks_like_track2(player):
                print()
                print("PASS: playback auto-advanced to track 2")
                return True

            idle = player.is_idle or (state or "").lower() in {"idle", "stop", "stopped"}
            if saw_playing and idle:
                print()
                print("FAIL: went idle after track 1 without auto-advance")
                return False

            await asyncio.sleep(1)

        print()
        print("FAIL: timed out waiting for auto-advance to track 2")
        return False

    except Exception as err:
        print(f"FAIL: {err}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if upnp_client:
            await upnp_client.close()
        await client.close()


async def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug/test_playqueue_auto_advance.py <device_ip>")
        print("Example: python scripts/debug/test_playqueue_auto_advance.py 192.168.1.115")
        sys.exit(1)

    host = sys.argv[1]
    ok = await test_playqueue_auto_advance(host)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())

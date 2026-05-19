#!/usr/bin/env python3
"""Watch 12V trigger cache during player.refresh() — for manual app-side testing.

Usage (from repo root, venv active):
  python scripts/manual/watch_trigger_out.py 192.168.1.115
  python scripts/manual/watch_trigger_out.py 192.168.1.115 --interval 15 --count 12

Toggle trigger in the WiiM Home app while this runs; cached trigger_out_on should
update on the next refresh when supports_trigger_out is true (ADR 019).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pywiim.client import WiiMClient
from pywiim.player import Player


async def main() -> None:
    parser = argparse.ArgumentParser(description="Watch 12V trigger state via player.refresh()")
    parser.add_argument("host", help="Device IP")
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between refreshes (default 10 for manual testing)",
    )
    parser.add_argument("--count", type=int, default=12, help="Number of refresh cycles")
    args = parser.parse_args()

    client = WiiMClient(args.host, protocol="https", port=443)
    await client._detect_capabilities()
    info = await client.get_device_info_model()
    player = Player(client)

    print(f"Device: {info.name} model={info.model}")
    print(f"supports_trigger_out: {player.supports_trigger_out}")
    if not player.supports_trigger_out:
        print("This model is not in the 12V trigger hardware list; exiting.")
        await client.close()
        return

    print(f"Polling get_trigger_out_status every {args.interval}s ({args.count} cycles).")
    print("Change trigger in WiiM app now.\n")

    for i in range(args.count):
        await player.get_trigger_out_status()
        print(f"[{i + 1}/{args.count}] trigger_out_on={player.trigger_out_on!r}")
        if i + 1 < args.count:
            await asyncio.sleep(args.interval)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())

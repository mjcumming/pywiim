#!/usr/bin/env python3
"""Test HTTP volume response for specific device."""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pywiim import WiiMClient

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_LOGGER = logging.getLogger(__name__)


async def test_device(host: str) -> None:
    """Test HTTP volume response."""
    print(f"\n{'='*60}")
    print(f"Testing HTTP volume for: {host}")
    print(f"{'='*60}")

    try:
        client = WiiMClient(host=host)

        # Get raw status
        print(f"\n1. Raw getPlayerStatus response:")
        try:
            raw_status = await client.get_player_status()
            print(f"   Type: {type(raw_status)}")
            print(f"   Keys: {list(raw_status.keys()) if isinstance(raw_status, dict) else 'N/A'}")
            if isinstance(raw_status, dict):
                volume = raw_status.get("volume")
                print(f"   volume field: {volume} (type: {type(volume)})")
                print(f"   Full response (pretty):")
                print(json.dumps(raw_status, indent=2))
        except Exception as err:
            print(f"   Error: {err}")

        # Get status model
        print(f"\n2. Parsed PlayerStatus model:")
        try:
            status_model = await client.get_player_status_model()
            print(f"   status_model.volume: {status_model.volume}")
            print(f"   status_model.volume type: {type(status_model.volume)}")
            print(f"   status_model fields:")
            for field in ["volume", "mute", "play_state", "source"]:
                value = getattr(status_model, field, None)
                print(f"     {field}: {value}")
        except Exception as err:
            print(f"   Error: {err}")

        # Try getStatusEx directly
        print(f"\n3. Raw getStatusEx response:")
        try:
            raw_statusex = await client._request("/httpapi.asp?command=getStatusEx")
            data = raw_statusex.parsed
            print(f"   Type: {type(data)}")
            if isinstance(data, dict):
                volume = data.get("volume")
                print(f"   volume field: {volume} (type: {type(volume)})")
                # Check for volume in any field
                volume_fields = {k: v for k, v in data.items() if "vol" in k.lower()}
                if volume_fields:
                    print(f"   Volume-related fields: {volume_fields}")
            else:
                print(f"   Response: {data or raw_statusex.raw}")
        except Exception as err:
            print(f"   Error: {err}")

        # Try getPlayerStatusEx
        print(f"\n4. Raw getPlayerStatusEx response:")
        try:
            raw_player_status = await client._request("/httpapi.asp?command=getPlayerStatusEx")
            data = raw_player_status.parsed
            print(f"   Type: {type(data)}")
            if isinstance(data, dict):
                volume = data.get("volume")
                print(f"   volume field: {volume} (type: {type(volume)})")
                # Check for volume in any field
                volume_fields = {k: v for k, v in data.items() if "vol" in k.lower()}
                if volume_fields:
                    print(f"   Volume-related fields: {volume_fields}")
                print(f"   Keys: {list(data.keys())[:20]}...")  # First 20 keys
            else:
                print(f"   Response: {data or raw_player_status.raw}")
        except Exception as err:
            print(f"   Error: {err}")

        print(f"\n✅ Test completed for {host}")

    except Exception as err:
        print(f"\n❌ Error testing {host}: {err}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def main() -> None:
    """Test device."""
    await test_device("192.168.6.50")


if __name__ == "__main__":
    asyncio.run(main())

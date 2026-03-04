#!/usr/bin/env bash
# Characterize EQ API behavior: set EQ to known states (Off, Flat, another preset),
# then read back getPlayerStatusEx and EQGetStat. Records what the device actually
# returns so we can implement logic that matches the API.
#
# Usage:
#   ./scripts/eq-api-behavior.sh [device_ip]
#
# Requires: curl. Uses HTTPS port 443 and -k (insecure). Set WIIM_PORT=80
# and WIIM_PROTOCOL=http if your device uses HTTP.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVICES_YAML="$REPO_ROOT/tests/devices.yaml"

PORT="${WIIM_PORT:-443}"
PROTOCOL="${WIIM_PROTOCOL:-https}"
SLEEP="${WIIM_EQ_SLEEP:-2}"

usage() {
  echo "Usage: $0 [device_ip]"
  echo "  device_ip  Optional. Default: first device from $DEVICES_YAML"
  echo ""
  echo "Sets EQ to Off, then Flat, then another preset (e.g. Rock); after each"
  echo "state reads getPlayerStatusEx (eq field) and EQGetStat. Prints a summary"
  echo "table so we can see how the API behaves."
  exit 1
}

get_first_device() {
  if [[ -f "$DEVICES_YAML" ]]; then
    grep -E '^\s+ip:\s+' "$DEVICES_YAML" | head -1 | sed 's/.*ip:\s*//' | tr -d ' '
  fi
}

curl_cmd() {
  local ip="$1"
  local path="$2"
  curl -sk --connect-timeout 5 --max-time 10 "${PROTOCOL}://${ip}:${PORT}${path}" 2>/dev/null || echo '{"error":"request failed"}'
}

run_test() {
  local ip="${1:?need device IP}"
  echo "=============================================="
  echo "EQ API behavior test: $ip"
  echo "=============================================="
  echo ""

  # 1. Get preset list (what does device support?)
  echo "--- EQGetList (available presets) ---"
  local list_resp
  list_resp=$(curl_cmd "$ip" "/httpapi.asp?command=EQGetList")
  echo "$list_resp"
  echo ""

  # 2. Initial state (don't assume)
  echo "--- Initial state (before we change anything) ---"
  echo "getPlayerStatusEx eq:"
  curl_cmd "$ip" "/httpapi.asp?command=getPlayerStatusEx" | grep -o '"eq":[^,}]*' || true
  echo "EQGetStat:"
  curl_cmd "$ip" "/httpapi.asp?command=EQGetStat"
  echo ""
  echo ""

  # 3. Set EQ OFF
  echo "--- Setting EQ to OFF (command=EQOff) ---"
  curl_cmd "$ip" "/httpapi.asp?command=EQOff" >/dev/null
  sleep "$SLEEP"
  echo "getPlayerStatusEx eq:"
  curl_cmd "$ip" "/httpapi.asp?command=getPlayerStatusEx" | grep -o '"eq":[^,}]*' || true
  echo "EQGetStat:"
  curl_cmd "$ip" "/httpapi.asp?command=EQGetStat"
  echo ""
  echo ""

  # 4. Set EQ ON + Flat
  echo "--- Setting EQ ON then Flat (command=EQOn, then EQLoad:Flat) ---"
  curl_cmd "$ip" "/httpapi.asp?command=EQOn" >/dev/null
  sleep 1
  curl_cmd "$ip" "/httpapi.asp?command=EQLoad:Flat" >/dev/null
  sleep "$SLEEP"
  echo "getPlayerStatusEx eq:"
  curl_cmd "$ip" "/httpapi.asp?command=getPlayerStatusEx" | grep -o '"eq":[^,}]*' || true
  echo "EQGetStat:"
  curl_cmd "$ip" "/httpapi.asp?command=EQGetStat"
  echo ""
  echo ""

  # 5. Set EQ to Rock (common preset)
  echo "--- Setting EQ to Rock (command=EQLoad:Rock) ---"
  curl_cmd "$ip" "/httpapi.asp?command=EQLoad:Rock" >/dev/null
  sleep "$SLEEP"
  echo "getPlayerStatusEx eq:"
  curl_cmd "$ip" "/httpapi.asp?command=getPlayerStatusEx" | grep -o '"eq":[^,}]*' || true
  echo "EQGetStat:"
  curl_cmd "$ip" "/httpapi.asp?command=EQGetStat"
  echo ""
  echo ""

  # 6. Set back to OFF so we leave device in a known state
  echo "--- Restoring EQ to OFF ---"
  curl_cmd "$ip" "/httpapi.asp?command=EQOff" >/dev/null
  sleep 1
  echo "Done. Review the outputs above to see how eq and EQGetStat change per state."
}

ip="${1:-$(get_first_device)}"
if [[ -z "$ip" ]]; then
  echo "No device IP. Specify one or add devices to $DEVICES_YAML" >&2
  usage
fi

run_test "$ip"

#!/usr/bin/env bash
# Query EQ-related API responses from WiiM/LinkPlay devices using curl.
# Use this to see exactly what getPlayerStatusEx returns for "eq" and what
# EQGetStat returns (for wiim#165 and device-specific behavior).
#
# Usage:
#   ./scripts/eq-api-curl.sh [device_ip ...]
#   ./scripts/eq-api-curl.sh              # use devices from tests/devices.yaml
#
# Prerequisites: curl, optional jq for pretty extraction
# Devices typically use HTTPS on port 443; -k skips cert verification.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVICES_YAML="$REPO_ROOT/tests/devices.yaml"

# Default port and protocol (WiiM typically HTTPS 443)
PORT="${WIIM_PORT:-443}"
PROTOCOL="${WIIM_PROTOCOL:-https}"

get_devices() {
  if [[ $# -gt 0 ]]; then
    echo "$@"
    return
  fi
  if [[ -f "$DEVICES_YAML" ]]; then
    grep -E '^\s+ip:\s+' "$DEVICES_YAML" | sed 's/.*ip:\s*//' | tr -d ' '
  else
    echo "No IPs given and $DEVICES_YAML not found." >&2
    return 1
  fi
}

# Curl one endpoint and print body (no -s to keep errors visible, or -s for script)
curl_get() {
  local ip="$1"
  local path="$2"
  local url="${PROTOCOL}://${ip}:${PORT}${path}"
  curl -sk --connect-timeout 5 --max-time 10 "$url" 2>/dev/null || echo "{\"error\": \"request failed\"}"
}

# Pretty-print JSON if jq available
maybe_jq() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  else
    cat
  fi
}

# Extract one key (e.g. eq) from JSON
maybe_jq_key() {
  local key="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -r --arg k "$key" '.[$k] // " (key missing)"'
  else
    cat
  fi
}

main() {
  local devices
  devices=($(get_devices "$@")) || exit 1

  for ip in "${devices[@]}"; do
    echo "=============================================="
    echo "Device: $ip"
    echo "=============================================="

    echo ""
    echo "--- getPlayerStatusEx (full) ---"
    curl_get "$ip" "/httpapi.asp?command=getPlayerStatusEx" | maybe_jq

    echo ""
    echo "--- getPlayerStatusEx → eq field only ---"
    curl_get "$ip" "/httpapi.asp?command=getPlayerStatusEx" | maybe_jq_key "eq"

    echo ""
    echo "--- EQGetStat (full) ---"
    curl_get "$ip" "/httpapi.asp?command=EQGetStat" | maybe_jq

    echo ""
  done
}

main "$@"

#!/bin/bash

# ------------------ Configuration ------------------
ZAP_PATH="/usr/share/zaproxy/zap.sh"
ZAP_PORT=9090
ZAP_API="http://localhost:$ZAP_PORT"
TARGET="$1"
ZAP_SESSION_DIR="/home/$USER/zap-session"
MAX_CHILDREN=10
AUTO_UPDATE=false
USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)"
CONTEXT_NAME="default"

# Directories
OUTPUT_DIR="$(pwd)/outputs"
LOG_DIR="$(pwd)/logs"
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$OUTPUT_DIR/vul.txt"
LOG_FILE="$LOG_DIR/zap_debug_${TIMESTAMP}.log"
[ -f "$REPORT_FILE" ] && rm "$REPORT_FILE"

# ------------------ Input Check --------------------
if [ -z "$TARGET" ]; then
    echo "[!] Usage: $0 http://target.com"
    exit 1
fi
[[ "$TARGET" != http* ]] && TARGET="http://$TARGET"

# ------------------ Kill Port If Occupied ------------------
echo "[*] Ensuring port $ZAP_PORT is free..."
ZAP_PID=$(lsof -ti:$ZAP_PORT)
if [ -n "$ZAP_PID" ]; then
    echo "[!] Port $ZAP_PORT is occupied by PID $ZAP_PID. Killing it..."
    kill -9 "$ZAP_PID"
    sleep 3
fi

# ------------------ Launch ZAP ---------------------
echo "[*] Launching ZAP..."
bash "$ZAP_PATH" -daemon \
    -port "$ZAP_PORT" \
    -config api.disablekey=true \
    -config update.addonAutoUpdate=$AUTO_UPDATE \
    -config "network.connection.default.useragent=$USER_AGENT" \
    -dir "$ZAP_SESSION_DIR" >> "$LOG_FILE" 2>&1 &
sleep 10

# ------------------ Wait for API -------------------
echo "[*] Waiting for ZAP API..."
until curl -s "$ZAP_API" > /dev/null; do sleep 1; done

# ------------------ ZAP Setup ----------------------
curl -s "$ZAP_API/JSON/context/action/includeInContext/?contextName=$CONTEXT_NAME&regex=$TARGET.*" >> "$LOG_FILE"
curl -s "$ZAP_API/JSON/ascan/action/enableAllPolicies/" >> "$LOG_FILE"
curl -s "$ZAP_API/JSON/httpSessions/action/addDefaultSessionToken/?sessionToken=X-Forwarded-For" >> "$LOG_FILE"

# ------------------ Spider -------------------------
echo "[*] Starting spider..."
curl -s "$ZAP_API/JSON/spider/action/scan/?url=$TARGET&maxChildren=$MAX_CHILDREN" >> "$LOG_FILE"
sleep 5

# ------------------ Active Scan --------------------
curl -s "$ZAP_API/JSON/ascan/action/scan/?url=$TARGET" >> "$LOG_FILE" &
echo "[*] Waiting for spider & active scan..."

# Wait for spider
while true; do
    SPIDER_STATUS=$(curl -s "$ZAP_API/JSON/spider/view/status/" | jq -r '.status')
    echo "Spider progress: $SPIDER_STATUS%"
    [[ "$SPIDER_STATUS" == "100" ]] && break
    sleep 2
done

# Wait for scan
while true; do
    SCAN_STATUS=$(curl -s "$ZAP_API/JSON/ascan/view/status/" | jq -r '.status')
    echo "Active scan progress: $SCAN_STATUS%"
    [[ "$SCAN_STATUS" == "100" ]] && break
    sleep 2
done

# ------------------ Fetch Alerts -------------------
echo "[*] Fetching alerts..."
ALERTS=$(curl -s "$ZAP_API/JSON/core/view/alerts/?baseurl=$TARGET")

if echo "$ALERTS" | jq -e '.alerts' > /dev/null 2>&1; then
    echo "$ALERTS" | jq -r '.alerts[] | select(.risk != "Informational") | "[\(.risk)] \(.alert): \(.url)"' > "$REPORT_FILE"
    if [ ! -s "$REPORT_FILE" ]; then
        echo "No vulnerabilities found for $TARGET" > "$REPORT_FILE"
    fi
else
    echo "[!] Invalid or empty alert data." >> "$LOG_FILE"
    echo "No vulnerabilities found or scan failed for $TARGET" > "$REPORT_FILE"
fi

echo "[✓] Scan complete. Report saved to $REPORT_FILE"
echo "[✓] Debug log saved to $LOG_FILE"

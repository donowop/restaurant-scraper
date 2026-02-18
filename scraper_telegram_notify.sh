#!/bin/bash
# Scraper Status - Sends update to Telegram topic every hour
# Uses the takopi plugin backend as single source of truth

BOT_TOKEN="8569314350:AAFSNpyCVWAVPCEHqg3tyo5q_8J2WDjO2NM"
CHAT_ID="-1003515856760"
TOPIC_ID="18"
TAKOPI_PYTHON="/Users/donosclawdbot/.local/share/uv/tools/takopi/bin/python"
PLUGIN_DIR="/Users/donosclawdbot/repos/restaurant-scraper/takopi_plugins/scraper_status"

MESSAGE=$($TAKOPI_PYTHON -c "
import sys; sys.path.insert(0, '$PLUGIN_DIR')
from backend import _get_status
print(_get_status())
")

curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    -d "message_thread_id=${TOPIC_ID}" \
    -d "parse_mode=Markdown" \
    -d "text=${MESSAGE}" > /dev/null

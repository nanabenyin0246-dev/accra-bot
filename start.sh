#!/bin/bash
cd ~/accra-bot
# Load environment variables
set -a
source .env
set +a
termux-wake-lock 2>/dev/null || true
echo "🚀 Starting Accra Bot..."
python3 bot.py

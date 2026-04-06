#!/bin/bash
cd ~/accra-bot
export $(grep -v '^#' .env | xargs)
termux-wake-lock 2>/dev/null || true
echo "🚀 Starting Accra Bot..."
python3 bot.py

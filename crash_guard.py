import sys, os, requests, traceback, time

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT", "")

def send_telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT, "text": msg},
                timeout=10
            )
        except:
            pass

while True:
    try:
        import bot
        bot.main()
    except SystemExit:
        break
    except Exception as e:
        err = traceback.format_exc()
        send_telegram(f"ACCRA BOT CRASHED:\n{err[-1000:]}")
        time.sleep(30)

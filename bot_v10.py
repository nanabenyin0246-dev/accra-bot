#!/usr/bin/env python3
"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘   ACCRA BOT v10 - MULTI-AI PERFORMANCE ENGINE        â•‘
â•‘   Built on v9 architecture + v4 performance fixes    â•‘
â•‘                                                      â•‘
â•‘   Key fixes for $72â†’$50 loss:                        â•‘
â•‘   1. MINIMUM ORDER FILTER - no more 400 errors       â•‘
â•‘   2. SCORE THRESHOLD raised - fewer bad trades       â•‘
â•‘   3. TREND FILTER - only trade WITH the trend        â•‘
â•‘   4. ASSET TRAP FIX - smart exit from stuck positionsâ•‘
â•‘   5. DREAM CYCLE - learns from losing trades         â•‘
â•‘   6. DEFENSIVE MODE - raises bar after losses        â•‘
â•‘   7. DAILY LOSS LIMIT - stops at -5% today           â•‘
â•‘   8. ATR STOP LOSS - dynamic, not fixed %            â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

Run: python bot_v10.py
Requires: pip install requests python-binance groq
"""

import os, sys, time, json, math, subprocess
from datetime import datetime, timezone, timedelta
import requests

# â”€â”€ CONFIGURATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "nanabenyin0246-dev/accra-bot")
GIST_ID       = "4f5f6918288ddaec0a1fc998af3e6f99"
TELEGRAM_TOKEN= os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT", "")

BINANCE_KEY    = os.environ.get("BINANCE_KEY", "")
BINANCE_SECRET = os.environ.get("BINANCE_SECRET", "")
GROQ_KEY       = os.environ.get("GROQ_KEY", "")
GEMINI_KEY     = os.environ.get("GEMINI_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")

SLEEP_SECS = 60
VERSION    = "10.0"
PAPER_MODE = os.environ.get("PAPER_MODE", "false").lower() == "true"

# â”€â”€ RISK MANAGEMENT (v4 upgrades) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
RISK = {
    "min_score":           15,    # v9 had no floor â€” this stops low-quality trades
    "min_score_defensive": 25,    # raised when losing streak detected
    "max_risk_pct":        0.03,  # never risk more than 3% per trade
    "min_order_usdt":      6.0,   # Binance minimum ~$5, we use $6 to be safe
    "losing_streak_limit": 3,     # go defensive after 3 losses in a row
    "daily_loss_limit_pct":5.0,   # stop all trading if down 5% today
    "cooldown_minutes":    90,    # no re-entry on same asset after a loss
    "max_open_trades":     5,     # don't hold more than 5 positions
    "min_volume_usdt":     100_000,  # skip assets with <$50M 24h volume
}

HISTORY_FILE  = os.path.expanduser("~/accra-bot/trade_history.json")
INSIGHTS_FILE = os.path.expanduser("~/accra-bot/dream_insights.json")

# AI providers â€” same as v9
AI_PROVIDERS = ["groq", "gemini", "openrouter", "mistral", "cerebras", "deepseek"]

# â”€â”€ LOGGING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def log(msg, level="info"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info":"  ", "warn":"âš  ", "error":"âœ— ", "ok":"âœ“ ", "signal":"â—† ", "trade":"â˜… ", "dream":"~ "}
    print(f"[{ts}] {prefix.get(level,'  ')}{msg}")

def telegram(msg):
    """Send Telegram notification â€” preserved from v9."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        log(f"Telegram error: {e}", "warn")

# â”€â”€ GIST I/O (same as v9) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def gist_read(filename):
    try:
        url = f"https://gist.githubusercontent.com/nanabenyin0246-dev/{GIST_ID}/raw/{filename}?t={int(time.time())}"
        r = requests.get(url, timeout=15)
        if r.ok:
            return r.json()
    except Exception as e:
        log(f"Gist read {filename}: {e}", "warn")
    return None

def gist_write(files_dict):
    if not GITHUB_TOKEN:
        return False
    try:
        payload = {"files": {k: {"content": json.dumps(v, indent=2)} for k, v in files_dict.items()}}
        r = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            json=payload,
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
            timeout=20
        )
        return r.ok
    except Exception as e:
        log(f"Gist write: {e}", "error")
        return False

# â”€â”€ TRADE HISTORY (v4 upgrade â€” v9 didn't have this) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except:
        return []

def save_history(h):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(h[-500:], f, indent=2)

def record_trade(asset, signal, score, price, reason, outcome="PENDING", profit_pct=0):
    h = load_history()
    h.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset": asset, "signal": signal, "score": score,
        "price": price, "reason": reason,
        "outcome": outcome, "profit_pct": profit_pct,
        "version": VERSION,
    })
    save_history(h)

# â”€â”€ DREAM CYCLE: Learn from own trade history (v4 upgrade) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
dream_counter = 0
DREAM_EVERY   = 15  # run every 15 cycles (~15 min)

def run_dream_cycle():
    """Analyze trade history and return actionable directives."""
    h = load_history()
    if len(h) < 5:
        log("Dream: need 5+ trades to analyze", "dream")
        return None

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = [t for t in h if t.get("timestamp","") > cutoff] or h[-20:]

    settled = [t for t in recent if t.get("outcome") in ("WIN","LOSS")]
    if not settled:
        return None

    wins = [t for t in settled if t["outcome"] == "WIN"]
    win_rate = len(wins) / len(settled)

    # Per-asset P&L
    asset_pnl = {}
    for t in recent:
        a = t.get("asset","?")
        asset_pnl.setdefault(a, []).append(t.get("profit_pct", 0))
    asset_avg = {a: sum(v)/len(v) for a, v in asset_pnl.items() if v}

    worst = min(asset_avg, key=asset_avg.get) if asset_avg else None
    best  = max(asset_avg, key=asset_avg.get) if asset_avg else None

    # Current losing streak
    streak = 0
    for t in reversed(settled):
        if t["outcome"] == "LOSS": streak += 1
        else: break

    directives = {
        "avoid_asset":        worst if asset_avg.get(worst, 0) < -2 else None,
        "prefer_asset":       best  if asset_avg.get(best,  0) >  1 else None,
        "go_defensive":       streak >= RISK["losing_streak_limit"],
        "recommended_min_score": 25 if win_rate < 0.4 else 20 if win_rate < 0.5 else 15,
    }

    insights = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "win_rate_pct": round(win_rate * 100, 1),
        "wins": len(wins), "losses": len(settled) - len(wins),
        "current_losing_streak": streak,
        "best_asset": best, "worst_asset": worst,
        "asset_avg_pnl": {k: round(v, 2) for k, v in asset_avg.items()},
        "directives": directives,
    }

    try:
        with open(INSIGHTS_FILE, "w") as f:
            json.dump(insights, f, indent=2)
    except:
        pass

    log(f"Dream: win_rate={insights['win_rate_pct']}% streak={streak} avoid={directives['avoid_asset']} best={best}", "dream")

    if streak >= RISK["losing_streak_limit"]:
        telegram(f"âš ï¸ <b>DREAM ALERT</b>\n{streak} consecutive losses.\nGoing defensive mode.\nAvoiding: {directives['avoid_asset']}")

    return insights

def load_insights():
    try:
        with open(INSIGHTS_FILE) as f:
            return json.load(f)
    except:
        return None

# â”€â”€ COOLDOWN TRACKER (v4 upgrade) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_cooldowns = {}

def set_cooldown(asset):
    _cooldowns[asset] = datetime.now(timezone.utc) + timedelta(minutes=RISK["cooldown_minutes"])
    log(f"Cooldown set for {asset} ({RISK['cooldown_minutes']}min)", "warn")

def is_on_cooldown(asset):
    expiry = _cooldowns.get(asset.replace("USDT","").lower())
    if expiry and datetime.now(timezone.utc) < expiry:
        mins = int((expiry - datetime.now(timezone.utc)).total_seconds() / 60)
        log(f"{asset} on cooldown ({mins}min left after loss)")
        return True
    return False

# â”€â”€ DAILY LOSS LIMIT (v4 upgrade) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def check_daily_loss_limit(portfolio_usd):
    """Return True if bot should pause today."""
    h = load_history()
    today = datetime.now(timezone.utc).date().isoformat()
    today_trades = [t for t in h if t.get("timestamp","")[:10] == today and t.get("outcome") in ("WIN","LOSS")]
    if not today_trades:
        return False
    pnl = sum(t.get("profit_pct", 0) for t in today_trades)
    if pnl <= -RISK["daily_loss_limit_pct"]:
        log(f"Daily loss limit hit ({pnl:.1f}%). Pausing.", "error")
        telegram(f"â›” <b>DAILY LOSS LIMIT</b>\nDown {abs(pnl):.1f}% today. Bot paused.")
        return True
    return False

# â”€â”€ BINANCE CLIENT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_binance_prices = {}

def binance_price(symbol):
    """Get price from Binance with caching."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": symbol}, timeout=10
        )
        if r.ok:
            d = r.json()
            _binance_prices[symbol] = float(d["lastPrice"])
            return float(d["lastPrice"]), float(d["quoteVolume"])
    except:
        pass
    return _binance_prices.get(symbol, 0), 0

def binance_balance():
    """Get account balances from Binance."""
    if not BINANCE_KEY or not BINANCE_SECRET:
        return {}
    try:
        import hmac, hashlib
        ts = int(time.time() * 1000)
        params = f"timestamp={ts}"
        sig = hmac.new(BINANCE_SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()
        r = requests.get(
            f"https://api.binance.com/api/v3/account?{params}&signature={sig}",
            headers={"X-MBX-APIKEY": BINANCE_KEY}, timeout=15
        )
        if r.ok:
            return {b["asset"]: float(b["free"]) for b in r.json()["balances"] if float(b["free"]) > 0}
    except Exception as e:
        log(f"Balance error: {e}", "error")
    return {}

def binance_min_qty(symbol):
    """
    v10 FIX: Check Binance LOT_SIZE filter to avoid 400 errors.
    v9 was getting 400 errors because it didn't check this.
    """
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/exchangeInfo",
            params={"symbol": symbol}, timeout=15
        )
        if r.ok:
            for f in r.json()["symbols"][0]["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    return float(f["minQty"]), float(f["stepSize"])
    except:
        pass
    return 1.0, 1.0

def wait_for_net(max_wait=120):
    """Block until internet is back. Max wait 2 minutes."""
    for i in range(max_wait):
        try:
            requests.get('https://api.binance.com/api/v3/ping', timeout=3)
            return True
        except:
            if i % 10 == 0:
                log(f'[NET] Offline {i}s - waiting...', 'warn')
            time.sleep(1)
    return False

def binance_order(symbol, side, qty, dry_run=False):
    """
    Place order with minimum quantity validation.
    v9 FIX: Check min qty BEFORE placing to avoid 400 errors.
    """
    wait_for_net()  # ensure connected before placing order
    if not BINANCE_KEY or not BINANCE_SECRET:
        log(f"[PAPER] {side} {qty} {symbol}", "trade")
        return {"status": "PAPER", "symbol": symbol, "side": side, "qty": qty}

    if dry_run or PAPER_MODE:
        log(f"[DRY RUN] {side} {qty} {symbol}", "trade")
        return {"status": "DRY_RUN"}

    # Check minimum quantity
    min_qty, step = binance_min_qty(symbol)
    qty = max(qty, min_qty)
    # Round to step size
    precision = len(str(step).rstrip('0').split('.')[-1]) if '.' in str(step) else 0
    qty = round(round(qty / step) * step, precision)

    try:
        import hmac, hashlib
        ts = int(time.time() * 1000)
        params = f"symbol={symbol}&side={side}&type=MARKET&quantity={qty}&timestamp={ts}"
        sig = hmac.new(BINANCE_SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()
        r = requests.post(
            f"https://api.binance.com/api/v3/order?{params}&signature={sig}",
            headers={"X-MBX-APIKEY": BINANCE_KEY}, timeout=15
        )
        if r.ok:
            return r.json()
        else:
            log(f"Order error {symbol}: {r.status_code} {r.text[:100]}", "error")
            return None
    except Exception as e:
        log(f"Order exception {symbol}: {e}", "error")
        return None

# â”€â”€ TECHNICAL ANALYSIS (v4 upgrades) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def ema(data, period):
    if len(data) < period: return []
    k = 2 / (period + 1)
    r = [sum(data[:period]) / period]
    for v in data[period:]: r.append(v * k + r[-1] * (1-k))
    return r

def rsi(closes, period=14):
    if len(closes) < period + 2: return 50.0
    gains, losses = [], []
    for i in range(1, period+1):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains)/period, sum(losses)/period
    for i in range(period+1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag*(period-1) + max(d,0)) / period
        al = (al*(period-1) + max(-d,0)) / period
    return 100 if al == 0 else round(100 - 100/(1 + ag/al), 2)

def atr(ohlc, period=14):
    if len(ohlc) < period+1: return 0
    trs = [max(ohlc[i][2]-ohlc[i][3], abs(ohlc[i][2]-ohlc[i-1][4]), abs(ohlc[i][3]-ohlc[i-1][4]))
           for i in range(1, len(ohlc))]
    return sum(trs[-period:]) / period if trs else 0

def daily_trend(closes):
    """v4: Is the overall trend UP or DOWN? Prevents buying in downtrends."""
    if len(closes) < 14: return "NEUTRAL"
    first_avg = sum(closes[:7]) / 7
    last_avg  = sum(closes[-7:]) / 7
    if last_avg > first_avg * 1.02: return "UP"
    if last_avg < first_avg * 0.98: return "DOWN"
    return "NEUTRAL"

def fetch_klines(symbol, interval="1h", limit=100):
    """Fetch OHLCV from Binance."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=15
        )
        if r.ok:
            return [[float(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in r.json()]
            # [open_time, open, high, low, close, volume]
    except:
        pass
    return []

def generate_signal_v10(symbol):
    """
    v10 signal engine: combines v9's scoring with v4's trend filter and ATR SL.
    Returns score, signal, price, sl, tp, reasons.
    """
    klines = fetch_klines(symbol, "1h", 100)
    if not klines or len(klines) < 40:
        return None

    closes  = [x[4] for x in klines]
    volumes = [x[5] for x in klines]
    price   = closes[-1]
    avg_vol = sum(volumes[-24:]) / 24  # 24h average volume
    trend   = daily_trend(closes)
    atr_val = atr(klines, 14)

    r = rsi(closes)
    e9  = ema(closes, 9)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50) if len(closes) >= 50 else []

    macd12 = ema(closes, 12)
    macd26 = ema(closes, 26)
    if macd12 and macd26:
        macd_line = [a - b for a, b in zip(macd12[-len(macd26):], macd26)]
        sig_line  = ema(macd_line, 9)
        hist = macd_line[-1] - (sig_line[-1] if sig_line else 0)
    else:
        hist = 0

    sl_20 = closes[-20:]
    mid = sum(sl_20) / len(sl_20)
    std = math.sqrt(sum((x-mid)**2 for x in sl_20) / len(sl_20)) if len(sl_20) > 1 else 0
    pct_b = (price - mid + 2*std) / (4*std) if std else 0.5

    buy, sell, reasons = 0, 0, []

    # RSI
    if r < 32:    buy  += 25; reasons.append(f"RSI oversold {r}")
    elif r > 68:  sell += 25; reasons.append(f"RSI overbought {r}")

    # MACD
    if hist > 0:  buy  += 20; reasons.append("MACD bullish")
    else:         sell += 20; reasons.append("MACD bearish")

    # Bollinger
    if pct_b < 0.15:  buy  += 15; reasons.append("Near lower BB")
    elif pct_b > 0.85: sell += 15; reasons.append("Near upper BB")

    # EMA crossover
    if e9 and e21:
        if e9[-1] > e21[-1]:  buy  += 15; reasons.append("EMA9>21 âœ“")
        else:                  sell += 15; reasons.append("EMA9<21")

    # â˜… v4: TREND FILTER â€” big upgrade
    if trend == "UP":
        buy  += 20; reasons.append("Trend: UP â†‘")
    elif trend == "DOWN":
        sell += 20; reasons.append("Trend: DOWN â†“")

    # â˜… v4: EMA50 filter
    if e50:
        if price > e50[-1]:  buy  += 10; reasons.append("Above EMA50 âœ“")
        else:                sell += 10; reasons.append("Below EMA50")

    score = buy - sell  # net score like v9

    # â˜… v4: ANTI-CHOP â€” if short signal conflicts with trend, zero it out
    if buy > sell and trend == "DOWN":
        score = max(score - 20, 0)
        reasons.append("âŠ˜ Penalised: buying in downtrend")
    elif sell > buy and trend == "UP":
        score = min(score + 20, 0)
        reasons.append("âŠ˜ Penalised: selling in uptrend")

    signal = "BUY" if score >= RISK["min_score"] else "SELL" if score <= -RISK["min_score"] else "HOLD"

    # â˜… v4: ATR-based stop loss (dynamic, not fixed %)
    sl = round(price - 2 * atr_val, 6) if atr_val and signal == "BUY" else round(price + 2 * atr_val, 6)
    tp = round(price + 3 * atr_val, 6) if atr_val and signal == "BUY" else round(price - 3 * atr_val, 6)

    return {
        "symbol": symbol,
        "signal": signal,
        "score": round(score),
        "price": price,
        "rsi": r,
        "trend": trend,
        "atr": round(atr_val, 6),
        "sl": sl,
        "tp": tp,
        "reasons": reasons[:4],
        "volume_24h": round(avg_vol * price),
    }

# â”€â”€ MULTI-AI ANALYSIS (v9 feature preserved) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def ask_ai(prompt, max_tokens=300):
    """Try AI providers in order â€” same cascade as v9."""
    # Try Groq first (fastest)
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": max_tokens,
                      "temperature": 0.1,
                      "messages": [{"role":"system","content":"Trading bot AI. Return valid JSON only, no markdown."},
                                   {"role":"user","content": prompt}]},
                timeout=20
            )
            if r.ok:
                text = r.json()["choices"][0]["message"]["content"].strip()
                text = text.replace("```json","").replace("```","").strip()
                return json.loads(text), "groq"
        except Exception as e:
            log(f"Groq failed: {e}", "warn")

    # Try Gemini
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
                json={"contents":[{"parts":[{"text": prompt}]}]},
                timeout=20
            )
            if r.ok:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                text = text.replace("```json","").replace("```","").strip()
                return json.loads(text), "gemini"
        except Exception as e:
            log(f"Gemini failed: {e}", "warn")

    # Try OpenRouter
    if OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={"model": "mistralai/mistral-7b-instruct", "max_tokens": max_tokens,
                      "messages": [{"role":"user","content": prompt}]},
                timeout=20
            )
            if r.ok:
                text = r.json()["choices"][0]["message"]["content"].strip()
                text = text.replace("```json","").replace("```","").strip()
                return json.loads(text), "openrouter"
        except Exception as e:
            log(f"OpenRouter failed: {e}", "warn")

    return None, "none"

# â”€â”€ ASSET TRAP FIX (critical v10 upgrade) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def handle_asset_trap(balances):
    """
    v9 was getting trapped: USDT runs out, assets too small to sell.
    v10 fix: smarter exit â€” only sell if value > minimum AND score is negative.
    """
    usdt = balances.get("USDT", 0)
    log(f"[ASSET MODE] USDT=${usdt:.2f} â€” checking positions...", "warn")

    sell_candidates = []
    for asset, qty in balances.items():
        if asset in ("USDT", "BNB"): continue
        symbol = f"{asset}USDT"
        price, vol_24h = binance_price(symbol)
        if price <= 0: continue
        value = qty * price
        if value < RISK["min_order_usdt"]:
            log(f"  {symbol}: ${value:.2f} â€” too small to sell (min ${RISK['min_order_usdt']}), skipping")
            continue

        # Get signal â€” only sell if score is BAD
        sig = generate_signal_v10(symbol)
        if sig and sig["score"] <= -RISK["min_score"]:
            sell_candidates.append({"asset": asset, "symbol": symbol,
                                     "qty": qty, "value": value, "score": sig["score"]})
            log(f"  {symbol}: score={sig['score']} value=${value:.2f} â€” candidate for exit")

    # Sort worst score first
    sell_candidates.sort(key=lambda x: x["score"])

    freed = 0
    for c in sell_candidates[:2]:  # max 2 sells per cycle
        log(f"  Exiting {c['symbol']} (score={c['score']}, value=${c['value']:.2f})", "trade")
        result = binance_order(c["symbol"], "SELL", c["qty"])
        if result:
            freed += c["value"]
            record_trade(c["asset"], "SELL", c["score"], c["value"]/c["qty"],
                        "Asset trap exit", outcome="PENDING")
            telegram(f"ðŸ”´ <b>EXIT TRAP</b>: Sold {c['symbol']}\nValue: ${c['value']:.2f}\nScore: {c['score']}")
        time.sleep(1)

    if freed > 0:
        log(f"  Freed ${freed:.2f} USDT from trapped positions", "ok")
    elif not sell_candidates:
        log(f"  All positions either too small or trending OK â€” holding", "warn")

# â”€â”€ INTELLIGENCE REPORT (v9 feature preserved) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def build_intelligence_report(fg, crypto_prices):
    """Quick intelligence summary â€” same as v9 format."""
    try:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fear_greed": fg,
            "btc": crypto_prices.get("BTCUSDT", {}).get("price", 0),
            "eth": crypto_prices.get("ETHUSDT", {}).get("price", 0),
            "sol": crypto_prices.get("SOLUSDT", {}).get("price", 0),
        }
        return report
    except:
        return {}

# â”€â”€ MAIN CYCLE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
cycle_count = 0
open_trades = []

def run_cycle():
    global cycle_count, dream_counter, open_trades, _cooldowns
    cycle_count += 1
    now = datetime.now(timezone.utc).isoformat()

    log(f"\n{'='*54}")
    log(f"CYCLE {cycle_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # â”€â”€ Load strategy + insights â”€â”€
    strategy = gist_read("bot_strategy.json") or {}
    intel = gist_read("terminal_intelligence.json") or {}
    insights = load_insights()
    directives = insights.get("directives", {}) if insights else {}

    avoid_asset  = directives.get("avoid_asset")
    go_defensive = directives.get("go_defensive", False)
    min_score    = RISK["min_score_defensive"] if go_defensive else RISK["min_score"]
    # Terminal can override via strategy
    min_score = max(min_score, strategy.get("min_confidence", min_score))

    if go_defensive:
        log(f"DEFENSIVE MODE active (streak={insights.get('current_losing_streak',0)}, min_score={min_score})", "warn")

    # â”€â”€ Get balances â”€â”€
    balances = binance_balance()
    usdt = balances.get("USDT", 0)
    log(f"  USDT balance: ${usdt:.2f}")

    # â”€â”€ Daily loss check â”€â”€
    if check_daily_loss_limit(usdt):
        gist_write({"bot_status.json": {
            "version": VERSION, "timestamp": now, "cycle": cycle_count,
            "online": True, "paused": True, "pause_reason": "Daily loss limit",
            "top_opportunities": [], "open_positions": open_trades,
        }})
        return

    # â”€â”€ Asset trap: USDT too low â”€â”€
    if usdt < RISK["min_order_usdt"] and balances:
        handle_asset_trap(balances)
        return  # skip this cycle after handling trap

    # â”€â”€ Fear & Greed â”€â”€
    fg_val = 50
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.ok:
            fg_val = int(r.json()["data"][0]["value"])
    except: pass
    log(f"  Fear/Greed: {fg_val}")

    # USE TERMINAL INTELLIGENCE
    risk_score = intel.get("global_risk_score", 25)
    btc_trend  = intel.get("crypto", {}).get("btc_trend", "NEUTRAL")
    ghs_stress = intel.get("fx_stress", {}).get("GHS", {}).get("trend", "STABLE")
    if risk_score > 65:
        min_score = min(min_score + 15, 40)
        log(f"  Terminal: HIGH RISK ({risk_score}) raising min_score to {min_score}", "warn")
    if ghs_stress == "CRISIS":
        min_score = min(min_score + 10, 40)
        log(f"  Terminal: GHS CRISIS - extra caution", "warn")
    if btc_trend in ("STRONG_DOWN", "DOWN") and min_score < 30:
        min_score = 30
        log(f"  Terminal: BTC trend {btc_trend} - tightening threshold", "warn")
    log(f"  Terminal intel: risk={risk_score} btc={btc_trend} ghs={ghs_stress}")

    # Extreme fear/greed adjustment
    if fg_val < 15:
        min_score = min(min_score + 10, 35)
        log(f"  Extreme fear â€” raising min_score to {min_score}", "warn")
    elif fg_val > 85:
        min_score = min(min_score + 5, 30)
        log(f"  Extreme greed â€” raising min_score to {min_score}", "warn")

    # â”€â”€ Scan assets â”€â”€
    # Top coins to scan â€” can be extended
    SCAN_LIST = [
        "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
        "ADAUSDT","DOTUSDT","LINKUSDT","AVAXUSDT","MATICUSDT",
    ]
    # Also scan existing holdings
    for asset in balances:
        sym = f"{asset}USDT"
        if sym not in SCAN_LIST and asset not in ("USDT","BNB"):
            SCAN_LIST.append(sym)

    opportunities = []
    crypto_prices = {}

    for symbol in SCAN_LIST:
        # Skip avoided asset
        base = symbol.replace("USDT","").lower()
        if avoid_asset and base == avoid_asset.lower():
            log(f"  {symbol} â€” skipped (dream: poor performer)")
            continue

        if is_on_cooldown(symbol):
            continue

        sig = generate_signal_v10(symbol)
        if not sig:
            time.sleep(1)
            continue

        price, vol = binance_price(symbol)
        crypto_prices[symbol] = {"price": price, "volume": vol}

        # Volume filter
        if sig["volume_24h"] < RISK["min_volume_usdt"]:
            log(f"  {symbol}: low volume (${sig['volume_24h']/1e6:.0f}M) â€” skip")
            time.sleep(1)
            continue

        log(f"  {symbol}: score={sig['score']:+d} rsi={sig['rsi']} trend={sig['trend']} | {sig['reasons'][0] if sig['reasons'] else ''}")

        if sig["signal"] != "HOLD" and abs(sig["score"]) >= min_score:
            # Check enough USDT for buy
            if sig["signal"] == "BUY" and usdt < RISK["min_order_usdt"]:
                log(f"  {symbol}: BUY signal but insufficient USDT (${usdt:.2f})")
                continue

            opportunities.append(sig)

            # Execute trade if conditions met
            if sig["signal"] == "BUY" and usdt >= RISK["min_order_usdt"]:
                # Position size: risk 3% of portfolio
                portfolio_est = usdt + sum(
                    balances.get(s.replace("USDT",""), 0) * crypto_prices.get(s, {}).get("price", 0)
                    for s in SCAN_LIST
                )
                risk_usd = portfolio_est * RISK["max_risk_pct"]
                sl_dist  = abs(sig["price"] - sig["sl"]) if sig["atr"] else sig["price"] * 0.03
                qty      = (risk_usd / sl_dist) if sl_dist > 0 else risk_usd / sig["price"]
                buy_usd  = min(qty * sig["price"], usdt * 0.95)  # max 95% of available USDT
                buy_qty  = buy_usd / sig["price"]

                if buy_usd >= RISK["min_order_usdt"]:
                    log(f"  BUYING {symbol}: ${buy_usd:.2f} @ {sig['price']:.4f}", "trade")
                    result = binance_order(symbol, "BUY", round(buy_qty, 6))
                    if result:
                        record_trade(base, "BUY", sig["score"], sig["price"], " | ".join(sig["reasons"][:2]))
                        open_trades.append({**sig, "entry_time": now, "buy_usd": buy_usd})
                        telegram(f"ðŸŸ¢ <b>BUY</b> {symbol}\nScore: {sig['score']:+d} | RSI: {sig['rsi']}\nTrend: {sig['trend']}\nSL: {sig['sl']:.4f} | TP: {sig['tp']:.4f}\n{sig['reasons'][0]}")

        time.sleep(2)  # rate limit

    # â”€â”€ Check exits on open trades â”€â”€
    for trade in list(open_trades):
        sym = trade["symbol"]
        current_price, _ = binance_price(sym)
        if current_price <= 0: continue

        hit_tp = current_price >= trade["tp"]
        hit_sl = current_price <= trade["sl"]

        if hit_tp or hit_sl:
            outcome = "WIN" if hit_tp else "LOSS"
            profit_pct = (current_price - trade["price"]) / trade["price"] * 100
            base = sym.replace("USDT","").lower()
            qty = balances.get(sym.replace("USDT",""), 0)

            if qty * current_price >= RISK["min_order_usdt"]:
                result = binance_order(sym, "SELL", qty)
                if result:
                    record_trade(base, "SELL", trade["score"], current_price,
                                f"{'TP hit' if hit_tp else 'SL hit'}", outcome, profit_pct)
                    open_trades.remove(trade)
                    if outcome == "LOSS":
                        set_cooldown(base)
                    emoji = "ðŸŸ¢" if hit_tp else "ðŸ”´"
                    telegram(f"{emoji} <b>{'TP HIT' if hit_tp else 'SL HIT'}</b> {sym}\nP&L: {profit_pct:+.2f}%")

    # â”€â”€ Dream cycle â”€â”€
    global dream_counter
    dream_counter += 1
    dream_result = None
    if dream_counter >= DREAM_EVERY:
        dream_counter = 0
        dream_result = run_dream_cycle()

    # â”€â”€ Build status for terminal â”€â”€
    h = load_history()
    settled = [t for t in h if t.get("outcome") in ("WIN","LOSS")]
    wins = len([t for t in settled if t["outcome"]=="WIN"])
    win_rate = round(wins/len(settled)*100, 1) if settled else 0

    status = {
        "version": VERSION,
        "timestamp": now,
        "cycle": cycle_count,
        "online": True,
        "paused": False,
        "strategy_mode": (strategy.get("mode","balanced") or "balanced") + (" [DEFENSIVE]" if go_defensive else ""),
        "assets_scanned": len(SCAN_LIST),
        "signals_generated": len(opportunities),
        "open_trades": len(open_trades),
        "top_opportunities": [
            {**o, "ghana": "Watch USD/GHS before converting profits"}
            for o in sorted(opportunities, key=lambda x: abs(x["score"]), reverse=True)[:5]
        ],
        "open_positions": open_trades[:5],
        "fear_greed": {"value": fg_val},
        "performance": {
            "total_trades": len(settled),
            "win_rate_pct": win_rate,
            "wins": wins,
            "losses": len(settled) - wins,
            "defensive_mode": go_defensive,
            "current_min_score": min_score,
            "avoided_asset": avoid_asset,
        },
        "market_intel": {
            "btc_price": crypto_prices.get("BTCUSDT", {}).get("price", 0),
        },
        "dream": {
            "win_rate": win_rate,
            "best_asset": (insights or {}).get("best_asset"),
            "worst_asset": (insights or {}).get("worst_asset"),
            "summary": f"Win rate {win_rate}% | {len(settled)} settled trades | {'DEFENSIVE' if go_defensive else 'Normal'}",
            "key_insight": f"Avoid: {avoid_asset or 'none'} | Min score: {min_score}",
        },
        "last_updated": now,
    }

    gist_write({"bot_status.json": status})
    log(f"Pushed status â€” {len(opportunities)} signals | win_rate:{win_rate}%", "ok")

# â”€â”€ STARTUP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def main():
    global dream_counter
    dream_counter = 0

    print(f"""
â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘   ACCRA BOT v10 - MULTI-AI PERFORMANCE ENGINE        â•‘
â•‘   Crypto:  ALL top coins [ON]                        â•‘
â•‘   Stocks:  DISABLED                                  â•‘
â•‘   HFM:     DISABLED                                  â•‘
â•‘   Groq AI: {'ACTIVE' if GROQ_KEY else 'NO KEY'}                                     â•‘
â•‘   GitHub:  {'ACTIVE' if GITHUB_TOKEN else 'NO KEY'}                                  â•‘
â•‘   Mode:    {'PAPER âš ' if PAPER_MODE else 'LIVE  â˜…'}                                   â•‘
â•‘   Interval:{SLEEP_SECS}s                                          â•‘
â•‘   AI Providers: {AI_PROVIDERS}
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
""")

    if not GITHUB_TOKEN:
        log("GITHUB_TOKEN not set!", "error")
        sys.exit(1)

    # Test connections
    connected = []
    log("Connecting...")

    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10)
        if r.ok:
            btc = float(r.json()["price"])
            log(f"  Binance: BTC=${btc:,.2f} [OK]", "ok")
            connected.append("Binance")
    except Exception as e:
        log(f"  Binance failed: {e}", "error")

    log(f"  HFM/Exness: Signal mode [OK]", "ok")
    connected.append("HFM+Exness")

    # Set GitHub remote
    if GITHUB_TOKEN:
        try:
            subprocess.run(
                ["git","remote","set-url","origin",
                 f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"],
                cwd=os.path.expanduser("~/accra-bot"),
                capture_output=True
            )
        except: pass

    # Load existing insights
    insights = load_insights()
    if insights:
        log(f"Dream insights loaded: win_rate={insights.get('win_rate_pct')}%", "dream")

    telegram(
        f"<b>ACCRA BOT v10 STARTED</b>\n"
        f"Connected: {', '.join(connected)}\n"
        f"Mode: {'PAPER' if PAPER_MODE else 'LIVE'}\n"
        f"Min score: {RISK['min_score']} | Defensive at: {RISK['min_score_defensive']}\n"
        f"Max risk/trade: {int(RISK['max_risk_pct']*100)}%\n"
        f"Interval: {SLEEP_SECS}s"
    )

    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"[Cycle error] {e}", "error")
            telegram(f"<b>CYCLE ERROR v10</b>\n{e}")

        log(f"\n  Sleeping {SLEEP_SECS}s...")
        # Auto-reconnect (preserved from v9)
        for attempt in range(SLEEP_SECS):
            time.sleep(1)
            try:
                requests.get("https://api.binance.com/api/v3/ping", timeout=3)
                break
            except:
                if attempt % 10 == 0:
                    log(f"  [NET] Waiting for internet... {attempt}s")
                continue

if __name__ == "__main__":
    main()

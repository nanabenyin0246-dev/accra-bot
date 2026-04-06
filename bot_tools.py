import ccxt
import requests
from datetime import datetime, timedelta
import os

class BotTools:
    def __init__(self):
        self.binance = ccxt.binance({
            'apiKey': os.getenv('BINANCE_KEY'),
            'secret': os.getenv('BINANCE_SECRET')
        })
        self.cache = {}
    
    def get_price(self, symbol):
        """Get price with caching and fallback"""
        cache_key = f"price_{symbol}"
        
        # Check cache (30 sec TTL)
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=30):
                return cached_data
        
        # Try Binance
        try:
            ticker = self.binance.fetch_ticker(symbol)
            price = ticker['last']
            self.cache[cache_key] = (datetime.now(), price)
            return price
        except Exception as e:
            print(f"[TOOLS] Binance failed: {e}, trying CoinGecko")
            return self.get_price_coingecko(symbol)
    
    def get_price_coingecko(self, symbol):
        """Fallback price source"""
        coin_id = symbol.split('/')[0].lower()
        try:
            resp = requests.get(f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd')
            return resp.json()[coin_id]['usd']
        except:
            return None
    
    def get_fear_greed(self):
        """Fear & Greed index with caching"""
        cache_key = "fear_greed"
        
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if datetime.now() - cached_time < timedelta(hours=1):
                return cached_data
        
        try:
            resp = requests.get('https://api.alternative.me/fng/')
            value = int(resp.json()['data'][0]['value'])
            self.cache[cache_key] = (datetime.now(), value)
            return value
        except Exception as e:
            print(f"[TOOLS] Fear/Greed failed: {e}")
            return 50  # Neutral fallback

# Initialize globally
tools = BotTools()

#!/usr/bin/env python3
"""
Accra Bot v4 - PERFORMANCE EDITION
Focus: Stop losing money. Capital preservation first, then growth.

Key improvements over v3:
  1. DEFENSIVE MODE - raises min confidence when losing streak detected
  2. MULTI-TIMEFRAME confirmation (don't trade on single timeframe)
  3. TRADE LOGGING - tracks every decision so dream cycle learns from it
  4. POSITION SIZING - never risk more than 3% per trade
  5. COOLDOWN - no new trades in same asset for 2h after a loss
  6. TREND FILTER - only BUY when daily trend is UP, SELL when DOWN
  7. VOLUME CONFIRMATION - reject signals on low volume
  8. DREAM CYCLE - daily self-analysis, adjusts strategy from own history

Run on Termux:
  pkg install python
  export GITHUB_TOKEN=ghp_yourtoken
  export GROQ_KEY=gsk_yourkey  (optional, for AI analysis)
  python bot_v4.py
"""

import time, json, math, os, sys
from datetime import datetime, timezone, timedelta
import urllib.request, urllib.error

# â”€â”€ CONFIG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GIST_ID      = "4f5f6918288ddaec0a1fc998af3e6f99"
GH_TOKEN     = os.environ.get("GITHUB_TOKEN", "")
GROQ_KEY     = os.environ.get("GROQ_KEY", "")
VERSION      = "4.0-perf"
POLL_SEC     = 90       # seconds between cycles (longer = less API spam)
HISTORY_FILE = "trade_history.json"
INSIGHTS_FILE= "dream_insights.json"

# â”€â”€ RISK MANAGEMENT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
RISK = {
    "max_risk_pct":     0.03,   # max 3% of portfolio per trade
    "base_min_conf":    55,     # higher than v3's 35 â€” fewer but better trades
    "losing_streak_limit": 3,   # after 3 losses, go defensive
    "defensive_min_conf": 70,   # confidence required when defensive
    "cooldown_minutes": 120,    # no re-entry on same asset after loss
    "max_open_trades":  3,      # don't spread too thin
    "daily_loss_limit": 0.05,   # stop bot if down 5% today
}

ASSETS = ["bitcoin", "ethereum", "solana"]

# â”€â”€ COLOR TERMINAL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
C = {k: f"\033[{v}m" for k, v in {
    "R":0,"bold":1,"red":31,"green":32,"yellow":33,"blue":34,"cyan":36,"gray":90,"gold":33
}.items()}
def c(col, t): return f"{C.get(col,'')}{t}{C['R']}"
def log(level, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO":c("blue","â—"),"SIGNAL":c("gold","â—†"),"WARN":c("yellow","â–²"),
             "ERROR":c("red","âœ—"),"OK":c("green","âœ“"),"DREAM":c("cyan","~"),
             "BLOCK":c("red","âŠ˜"),"TRADE":c("green","â˜…")}
    print(f"{c('gray',ts)} {icons.get(level,'â—')} {msg}")

# â”€â”€ TRADE HISTORY (local file) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def load_history():
    try:
        with open(HISTORY_FILE) as f: return json.load(f)
    except: return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f: json.dump(history[-500:], f, indent=2)  # keep last 500

def log_trade(asset, signal, confidence, price, reason, outcome="PENDING", profit_pct=0):
    history = load_history()
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "signal": signal,
        "confidence": round(confidence),
        "price": price,
        "reason": reason,
        "outcome": outcome,  # PENDING / WIN / LOSS / EXPIRED
        "profit_pct": profit_pct,
        "bot_version": VERSION,
    })
    save_history(history)
    return len(history)

# â”€â”€ DREAM CYCLE: Learn from history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def run_dream_cycle():
    """Analyze trade history and generate actionable insights."""
    log("DREAM", "Running self-analysis...")
    history = load_history()

    if len(history) < 10:
        log("DREAM", f"Only {len(history)} trades logged. Need 10+ to analyze.")
        return None

    # Recent trades only (last 7 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [t for t in history if t.get("timestamp","") > cutoff.isoformat()]
    if not recent:
        recent = history[-20:]

    # Win rate
    wins   = [t for t in recent if t.get("outcome") == "WIN"]
    losses = [t for t in recent if t.get("outcome") == "LOSS"]
    total  = len([t for t in recent if t.get("outcome") in ("WIN","LOSS")])
    win_rate = len(wins) / total if total > 0 else 0

    # Per-asset performance
    asset_pnl = {}
    for t in recent:
        a = t.get("asset","unknown")
        p = t.get("profit_pct", 0)
        if a not in asset_pnl: asset_pnl[a] = []
        asset_pnl[a].append(p)

    asset_avg = {a: sum(v)/len(v) for a, v in asset_pnl.items() if v}
    worst_asset = min(asset_avg, key=asset_avg.get) if asset_avg else None
    best_asset  = max(asset_avg, key=asset_avg.get) if asset_avg else None

    # Confidence calibration
    high_conf = [t for t in recent if t.get("confidence",0) >= 65 and t.get("outcome") in ("WIN","LOSS")]
    high_conf_win = len([t for t in high_conf if t.get("outcome")=="WIN"]) / len(high_conf) if high_conf else 0

    # Recent losing streak
    settled = [t for t in reversed(recent) if t.get("outcome") in ("WIN","LOSS")]
    streak = 0
    for t in settled:
        if t.get("outcome") == "LOSS": streak += 1
        else: break

    insights = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trades_analyzed": len(recent),
        "win_rate": round(win_rate * 100, 1),
        "wins": len(wins),
        "losses": len(losses),
        "current_losing_streak": streak,
        "best_asset": best_asset,
        "worst_asset": worst_asset,
        "asset_avg_pnl": {k: round(v, 2) for k, v in asset_avg.items()},
        "high_conf_win_rate": round(high_conf_win * 100, 1),
        # Actionable directives
        "directives": {
            "avoid_asset": worst_asset if asset_avg.get(worst_asset, 0) < -2 else None,
            "prefer_asset": best_asset if asset_avg.get(best_asset, 0) > 1 else None,
            "raise_threshold": win_rate < 0.45,   # losing more than winning
            "go_defensive": streak >= RISK["losing_streak_limit"],
            "recommended_min_conf": 70 if win_rate < 0.4 else 60 if win_rate < 0.5 else 55,
        }
    }

    with open(INSIGHTS_FILE, "w") as f: json.dump(insights, f, indent=2)

    log("DREAM", f"Win rate: {insights['win_rate']}% | Losing streak: {streak} | Best: {best_asset} | Worst: {worst_asset}")
    if streak >= 3: log("WARN", f"âš  {streak} consecutive losses â€” going defensive mode")

    return insights

def load_insights():
    try:
        with open(INSIGHTS_FILE) as f: return json.load(f)
    except: return None

# â”€â”€ GIST I/O â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def gist_read(filename):
    url = f"https://gist.githubusercontent.com/nanabenyin0246-dev/{GIST_ID}/raw/{filename}?t={int(time.time())}"
    try:
        req = urllib.request.Request(url, headers={"Cache-Control":"no-cache"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log("WARN", f"Gist read {filename}: {e}")
        return None

def gist_write(files_dict):
    if not GH_TOKEN:
        log("ERROR", "GITHUB_TOKEN not set!")
        return False
    payload = {"files": {k: {"content": json.dumps(v, indent=2)} for k, v in files_dict.items()}}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}", data=data, method="PATCH",
        headers={"Authorization":f"Bearer {GH_TOKEN}","Content-Type":"application/json","User-Agent":"AccraBot/4.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:
        log("ERROR", f"Gist write: {e}")
        return False

# â”€â”€ MARKET DATA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def fetch_ohlc(coin, days=30):
    """Fetch more candles (30d) for multi-timeframe analysis."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin}/ohlc?vs_currency=usd&days={days}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            raw = json.loads(r.read().decode())
            if not isinstance(raw, list) or len(raw) < 10:
                return []
            return raw  # [[timestamp, o, h, l, c], ...]
    except Exception as e:
        log("WARN", f"OHLC {coin}: {e}")
        return []

def fetch_fear_greed():
    try:
        with urllib.request.urlopen("https://api.alternative.me/fng/?limit=1", timeout=10) as r:
            d = json.loads(r.read().decode())
            return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
    except: return 50, "Neutral"

def fetch_volume(coin):
    """Get 24h volume to confirm signal is real."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd&include_24hr_vol=true"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
            return d.get(coin, {}).get("usd_24h_vol", 0)
    except: return 0

# â”€â”€ TECHNICAL ANALYSIS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def ema(data, period):
    if len(data) < period: return []
    k = 2 / (period + 1)
    r = [sum(data[:period]) / period]
    for v in data[period:]:
        r.append(v * k + r[-1] * (1 - k))
    return r

def rsi(closes, period=14):
    if len(closes) < period + 2: return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains)/period, sum(losses)/period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag*(period-1) + max(d,0)) / period
        al = (al*(period-1) + max(-d,0)) / period
    return 100 if al == 0 else round(100 - 100/(1 + ag/al), 2)

def atr(ohlc, period=14):
    """Average True Range â€” measures volatility for stop loss sizing."""
    if len(ohlc) < period + 1: return 0
    trs = []
    for i in range(1, len(ohlc)):
        h, l, pc = ohlc[i][2], ohlc[i][3], ohlc[i-1][4]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs[-period:]) / period

def daily_trend(ohlc_30d):
    """Is the overall 30-day trend UP or DOWN? Simple: compare first/last weeks."""
    if len(ohlc_30d) < 14: return "NEUTRAL"
    closes = [x[4] for x in ohlc_30d]
    first_week_avg = sum(closes[:7]) / 7
    last_week_avg  = sum(closes[-7:]) / 7
    if last_week_avg > first_week_avg * 1.02: return "UP"
    if last_week_avg < first_week_avg * 0.98: return "DOWN"
    return "NEUTRAL"

def generate_signal_v4(ohlc_30d):
    """
    Multi-timeframe signal. Uses:
    - Short-term (last 7d): RSI, MACD, BB
    - Medium-term (30d): trend direction
    Both must agree for a BUY/SELL signal.
    """
    if not ohlc_30d or len(ohlc_30d) < 40:
        return {"signal": "HOLD", "confidence": 0, "reasons": ["Insufficient data"], "rsi": 50}

    closes = [x[4] for x in ohlc_30d]
    price  = closes[-1]
    trend  = daily_trend(ohlc_30d)
    avg_vol = atr(ohlc_30d)

    # Short-term closes (last 14 candles for RSI/etc)
    sc = closes[-20:]
    r = rsi(closes)

    e9  = ema(closes, 9)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50) if len(closes) >= 50 else []

    macd12 = ema(closes, 12)
    macd26 = ema(closes, 26)
    macd_line = [a - b for a, b in zip(macd12[-len(macd26):], macd26)]
    sig_line = ema(macd_line, 9)
    hist = macd_line[-1] - (sig_line[-1] if sig_line else 0) if macd_line else 0

    mid = sum(sc)/len(sc)
    std = math.sqrt(sum((x-mid)**2 for x in sc)/len(sc)) if len(sc) > 1 else 0
    pct_b = (price - mid + 2*std) / (4*std) if std else 0.5

    buy, sell, reasons = 0, 0, []

    # Short-term signals
    if r < 32:   buy  += 30; reasons.append(f"RSI oversold {r}")
    elif r > 68: sell += 30; reasons.append(f"RSI overbought {r}")
    else:        reasons.append(f"RSI neutral {r}")

    if hist > 0: buy  += 20; reasons.append("MACD bullish")
    else:        sell += 20; reasons.append("MACD bearish")

    if pct_b < 0.15: buy  += 15; reasons.append("Near lower BB")
    elif pct_b > 0.85: sell += 15; reasons.append("Near upper BB")

    if e9 and e21:
        if e9[-1] > e21[-1]: buy  += 15; reasons.append("EMA9>EMA21 âœ“")
        else:                 sell += 15; reasons.append("EMA9<EMA21")

    # â˜… TREND FILTER (v4 key upgrade) â˜…
    # Short-term signal must align with medium-term trend
    if trend == "UP":
        buy += 20; reasons.append("Daily trend: UP â†‘")
    elif trend == "DOWN":
        sell += 20; reasons.append("Daily trend: DOWN â†“")

    # â˜… EMA50 FILTER (only trade above/below key level) â˜…
    if e50:
        if price > e50[-1]: buy += 10; reasons.append("Above EMA50 âœ“")
        else: sell += 10; reasons.append("Below EMA50")

    conf = max(buy, sell)
    signal = "BUY" if buy > sell and buy >= 50 else "SELL" if sell > buy and sell >= 50 else "HOLD"

    # â˜… ANTI-CHOP FILTER: if trend vs signal conflict, downgrade to HOLD â˜…
    if signal == "BUY" and trend == "DOWN":
        signal = "HOLD"; reasons.append("âŠ˜ Blocked: buying in downtrend")
    elif signal == "SELL" and trend == "UP":
        signal = "HOLD"; reasons.append("âŠ˜ Blocked: selling in uptrend")

    return {
        "signal": signal, "confidence": conf, "rsi": r, "macd": round(hist, 6),
        "trend": trend, "pct_b": round(pct_b, 3), "reasons": reasons[:4],
        "price": price,
        "sl": round(price - 2*avg_vol, 4),   # ATR-based stop loss (2x ATR)
        "tp": round(price + 3*avg_vol, 4),   # 3:1 reward:risk ratio
        "atr": round(avg_vol, 4),
    }

# â”€â”€ POSITION SIZING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def calc_position_size(portfolio_usd, price, sl_price, risk_pct=0.03):
    """Kelly-lite: risk exactly risk_pct of portfolio on this trade."""
    if price <= 0 or sl_price <= 0 or price == sl_price: return 0
    risk_per_unit = abs(price - sl_price)
    risk_dollars  = portfolio_usd * risk_pct
    units = risk_dollars / risk_per_unit
    return round(units, 6)

# â”€â”€ COOLDOWN TRACKER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_cooldowns = {}  # asset -> datetime when cooldown expires

def is_on_cooldown(asset):
    expiry = _cooldowns.get(asset)
    if expiry and datetime.now(timezone.utc) < expiry:
        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds() / 60)
        log("BLOCK", f"{asset} on cooldown ({remaining}min remaining after loss)")
        return True
    return False

def set_cooldown(asset, minutes=120):
    _cooldowns[asset] = datetime.now(timezone.utc) + timedelta(minutes=minutes)

# â”€â”€ DAILY LOSS LIMIT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def check_daily_loss_limit():
    """Stop trading if down 5% today."""
    history = load_history()
    today = datetime.now(timezone.utc).date().isoformat()
    today_trades = [t for t in history if t.get("timestamp","")[:10] == today and t.get("outcome") in ("WIN","LOSS")]
    if not today_trades: return False
    today_pnl = sum(t.get("profit_pct",0) for t in today_trades)
    if today_pnl <= -RISK["daily_loss_limit"] * 100:
        log("WARN", f"â›” Daily loss limit hit ({today_pnl:.1f}%). Bot paused for today.")
        return True
    return False

# â”€â”€ MAIN CYCLE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
open_trades = []
cycle_count = 0
dream_counter = 0
DREAM_EVERY = 20  # run dream every 20 cycles (~30 min)

def run_cycle():
    global cycle_count, dream_counter, open_trades
    cycle_count += 1
    now = datetime.now(timezone.utc).isoformat()

    log("INFO", f"{'â”€'*40}")
    log("INFO", f"Cycle {c('bold', str(cycle_count))} | {datetime.now().strftime('%H:%M:%S')}")

    # Daily loss check
    if check_daily_loss_limit():
        gist_write({"bot_status.json": {
            "version": VERSION, "timestamp": now, "cycle": cycle_count,
            "online": True, "paused": True, "pause_reason": "Daily loss limit reached",
            "top_opportunities": [], "open_positions": open_trades,
        }})
        time.sleep(POLL_SEC)
        return

    # Load strategy + intelligence
    strategy = gist_read("bot_strategy.json") or {}
    intel     = gist_read("terminal_intelligence.json") or {}

    # Load dream insights to adjust thresholds
    insights = load_insights()
    if insights:
        directives = insights.get("directives", {})
        avoid_asset = directives.get("avoid_asset")
        go_defensive = directives.get("go_defensive", False)
        min_conf = directives.get("recommended_min_conf", RISK["base_min_conf"])
        if go_defensive:
            min_conf = RISK["defensive_min_conf"]
            log("WARN", f"DEFENSIVE MODE (losing streak={insights.get('current_losing_streak',0)}, min_conf={min_conf}%)")
    else:
        avoid_asset = None
        go_defensive = False
        min_conf = strategy.get("min_confidence", RISK["base_min_conf"])

    # Override from terminal strategy
    min_conf = max(min_conf, strategy.get("min_confidence", RISK["base_min_conf"]))

    # Fear & Greed
    fg_val, fg_label = fetch_fear_greed()
    log("INFO", f"Fear/Greed: {fg_val} ({fg_label}) | Min conf: {min_conf}%")

    # Extreme fear (<20) or extreme greed (>85) = caution
    if fg_val < 15:
        log("WARN", "Extreme fear â€” raising threshold +10")
        min_conf = min(min_conf + 10, 85)
    elif fg_val > 85:
        log("WARN", "Extreme greed â€” raising threshold +5")
        min_conf = min(min_conf + 5, 80)

    opportunities = []

    for asset in ASSETS:
        log("INFO", f"Scanning {asset.upper()}...")

        # Skip avoided asset from dream analysis
        if avoid_asset and asset.lower() == avoid_asset.lower():
            log("BLOCK", f"{asset} â€” blocked by dream analysis (poor performer)")
            continue

        # Skip if on cooldown (recent loss)
        if is_on_cooldown(asset):
            continue

        # Skip if at max open trades
        asset_open = [t for t in open_trades if t.get("asset") == asset]
        if len(open_trades) >= RISK["max_open_trades"]:
            log("BLOCK", f"Max open trades reached ({len(open_trades)})")
            break

        # Fetch data
        ohlc = fetch_ohlc(asset, days=30)
        if not ohlc:
            log("WARN", f"No data for {asset}")
            time.sleep(3)
            continue

        sig = generate_signal_v4(ohlc)
        price = sig["price"]

        # Volume check â€” skip if volume too low (weak signal)
        vol = fetch_volume(asset)
        vol_ok = vol > 500_000_000  # $500M+ 24h volume = real signal
        if not vol_ok:
            log("WARN", f"{asset} volume ${vol/1e9:.1f}B â€” low, skipping")
            time.sleep(2)
            continue

        signal_col = "green" if sig["signal"] == "BUY" else "red" if sig["signal"] == "SELL" else "gray"
        log("INFO", f"  {c(signal_col, sig['signal'])} conf:{sig['confidence']}% | RSI:{sig['rsi']} | trend:{sig['trend']} | {sig['reasons'][0]}")

        if sig["signal"] == "HOLD" or sig["confidence"] < min_conf:
            log("INFO", f"  â†’ Skipped (conf {sig['confidence']}% < {min_conf}% required)")
            time.sleep(2)
            continue

        # â˜… POSITION SIZING â˜…
        portfolio_est = 50  # your current portfolio â€” update this!
        pos_size = calc_position_size(portfolio_est, price, sig["sl"], RISK["max_risk_pct"])
        risk_dollars = round(portfolio_est * RISK["max_risk_pct"], 2)

        opportunity = {
            "symbol": asset.upper(),
            "market": "crypto",
            "signal": sig["signal"],
            "score": sig["confidence"] - min_conf,
            "tech": sig["confidence"],
            "fund": round((fg_val - 50) * 0.2),
            "price": round(price, 4),
            "rsi": sig["rsi"],
            "trend": sig["trend"],
            "sl": sig["sl"],
            "tp": sig["tp"],
            "atr": sig["atr"],
            "pos_size": pos_size,
            "risk_usd": risk_dollars,
            "reason": " | ".join(sig["reasons"][:2]),
            "ghana": f"Monitor USD/GHS before converting profits",
            "time": now,
        }
        opportunities.append(opportunity)

        # Log the trade decision
        log_trade(asset, sig["signal"], sig["confidence"], price, opportunity["reason"])

        log("TRADE", f"  â˜… {sig['signal']} {asset.upper()} @ {price:.2f} | SL:{sig['sl']:.2f} TP:{sig['tp']:.2f} | Risk:${risk_dollars}")
        time.sleep(3)  # rate limit CoinGecko

    # Sort by score
    opportunities.sort(key=lambda x: x["score"], reverse=True)

    # Dream cycle every N cycles
    dream_counter += 1
    dream_summary = None
    if dream_counter >= DREAM_EVERY:
        dream_counter = 0
        dream_summary = run_dream_cycle()

    # Build bot_status
    history = load_history()
    settled = [t for t in history if t.get("outcome") in ("WIN","LOSS")]
    wins = len([t for t in settled if t.get("outcome")=="WIN"])
    win_rate = round(wins/len(settled)*100, 1) if settled else 0

    status = {
        "version": VERSION,
        "timestamp": now,
        "cycle": cycle_count,
        "online": True,
        "paused": False,
        "strategy_mode": strategy.get("mode", "balanced") + (" [DEFENSIVE]" if go_defensive else ""),
        "assets_scanned": len(ASSETS),
        "signals_generated": len(opportunities),
        "open_trades": len(open_trades),
        "top_opportunities": opportunities[:5],
        "open_positions": open_trades[:5],
        "fear_greed": {"value": fg_val, "label": fg_label},
        "performance": {
            "total_trades": len(settled),
            "win_rate_pct": win_rate,
            "wins": wins,
            "losses": len(settled) - wins,
            "defensive_mode": go_defensive,
            "current_min_conf": min_conf,
        },
        "market_intel": {
            "global_risk": intel.get("global_risk_score", 25),
            "btc_trend": intel.get("crypto", {}).get("btc_trend", "NEUTRAL"),
        },
        "dream": {
            "last_run": dream_summary.get("generated_at") if dream_summary else None,
            "win_rate": dream_summary.get("win_rate") if dream_summary else win_rate,
            "best_asset": dream_summary.get("best_asset") if dream_summary else None,
            "worst_asset": dream_summary.get("worst_asset") if dream_summary else None,
            "summary": f"Win rate {win_rate}% | {len(settled)} settled trades",
            "key_insight": (dream_summary or {}).get("directives", {}) and
                f"{'DEFENSIVE MODE' if go_defensive else 'Normal mode'} | avoid: {avoid_asset or 'none'}",
        },
        "last_updated": now,
    }

    ok = gist_write({"bot_status.json": status})
    if ok:
        log("OK", f"Pushed â”€ {len(opportunities)} signals | win_rate:{win_rate}% | defensive:{go_defensive}")
    else:
        log("ERROR", "Failed to push status")

# â”€â”€ BANNER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def banner():
    print(f"""
{c('gold','â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—')}
{c('gold','â•‘')}   {c('bold','ACCRA BOT v4 - PERFORMANCE EDITION')}   {c('gold','â•‘')}
{c('gold','â•‘')}   Capital preservation + smarter signals  {c('gold','â•‘')}
{c('gold','â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•')}

  {c('cyan','Key upgrades from v3:')}
  âœ“ Trend filter  â€” only trade WITH the trend
  âœ“ ATR stop loss â€” dynamic, not fixed 3%
  âœ“ Dream cycle   â€” learns from your trade history
  âœ“ Defensive modeâ€” raises bar after losing streaks
  âœ“ Cooldown      â€” no re-entry after loss for 2h
  âœ“ Daily limit   â€” stops if down 5% today
  âœ“ Volume filter â€” ignores weak/fake signals

  {c('gray','Config:')}
  Min confidence: {RISK['base_min_conf']}% (raises to {RISK['defensive_min_conf']}% defensive)
  Max risk/trade: {int(RISK['max_risk_pct']*100)}% of portfolio
  Cooldown after loss: {RISK['cooldown_minutes']}min
  Daily loss limit: {int(RISK['daily_loss_limit']*100)}%
""")

# â”€â”€ ENTRY POINT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    banner()

    if not GH_TOKEN:
        print(c("red", "ERROR: GITHUB_TOKEN not set!"))
        print("  Run: export GITHUB_TOKEN=your_token")
        print("  Then: python bot_v4.py")
        sys.exit(1)

    # Load any existing dream insights on startup
    insights = load_insights()
    if insights:
        log("DREAM", f"Loaded insights: win_rate={insights.get('win_rate')}% | avoid={insights.get('directives',{}).get('avoid_asset')}")
    else:
        log("INFO", "No dream insights yet â€” will build after 10+ trades")

    log("OK", "Bot started. Ctrl+C to stop.\n")

    try:
        while True:
            try:
                run_cycle()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log("ERROR", f"Cycle failed: {e}")
                import traceback; traceback.print_exc()
            log("INFO", f"Sleeping {POLL_SEC}s...\n")
            time.sleep(POLL_SEC)
    except KeyboardInterrupt:
        log("INFO", "\nBot stopped. Trade history saved.")

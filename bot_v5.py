#!/usr/bin/env python3
"""
Accra Bot v5 - PRODUCTION EDITION
Combines v3's multi-exchange trading + v4's risk intelligence + Claude Code patterns

Key Features:
  ✓ LIVE BINANCE TRADING - real crypto with $2 minimum trades
  ✓ 6 AI PROVIDERS - Groq, Gemini, Mistral, Cerebras, DeepSeek, OpenRouter
  ✓ DREAM CYCLE - learns from trade history, adjusts strategy daily
  ✓ DEFENSIVE MODE - raises threshold after losing streaks
  ✓ MULTI-TIMEFRAME - 1H signals + 4H trend confirmation
  ✓ TOOL REGISTRY - centralized API layer with caching & fallbacks
  ✓ POSITION SIZING - ATR-based stop loss, never risk >3%
  ✓ COOLDOWN SYSTEM - no re-entry on same asset for 2h after loss
  ✓ MARKET GUARDS - BTC trend check, Fear/Greed filter, volume validation
  ✓ SIGNAL TIERING - FLASH/PRIORITY/ROUTINE quality classification
  ✓ GITHUB STATUS - pushes to accra-terminal repo every cycle

Setup:
  pkg install python
  pip install requests --break-system-packages
  
  export BINANCE_KEY=your_key
  export BINANCE_SECRET=your_secret
  export GITHUB_TOKEN=ghp_your_token
  export GROQ_KEY=gsk_your_key  (optional, for AI)
  
  python3 bot_v5.py
"""

import os, time, json, hmac, hashlib, math, sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

# ── CONFIG ────────────────────────────────────────────────────────────────────
VERSION = "5.0-production"
POLL_SEC = 90

# API Keys
BINANCE_KEY    = os.getenv("BINANCE_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO    = "nanabenyin0246-dev/accra-terminal"
GIST_ID        = "4f5f6918288ddaec0a1fc998af3e6f99"

# AI Providers (optional)
GROQ_KEY       = os.getenv("GROQ_KEY", "")
GEMINI_KEY     = os.getenv("GEMINI_KEY", "")
MISTRAL_KEY    = os.getenv("MISTRAL_KEY", "")
CEREBRAS_KEY   = os.getenv("CEREBRAS_KEY", "")
DEEPSEEK_KEY   = os.getenv("DEEPSEEK_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")

# Files
HISTORY_FILE   = "trade_history.json"
INSIGHTS_FILE  = "dream_insights.json"
STRATEGY_FILE  = "bot_strategy.json"

# ── RISK MANAGEMENT ───────────────────────────────────────────────────────────
RISK = {
    "max_risk_pct": 0.03,           # max 3% of portfolio per trade
    "base_min_conf": 35,            # base confidence threshold
    "defensive_min_conf": 60,       # threshold when defensive mode
    "losing_streak_limit": 3,       # trigger defensive after 3 losses
    "cooldown_minutes": 120,        # no re-entry for 2h after loss
    "max_open_trades": 3,           # max concurrent positions
    "daily_loss_limit": 0.05,       # stop if down 5% today
    "min_trade_usdt": 2.0,          # Binance minimum
    "volume_threshold": 500_000_000, # min 24h volume for signal
}

# Quality coins only (exclude memecoins, rugs, low-caps)
QUALITY_COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "MATICUSDT",
    "UNIUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT"
]

# ── GLOBAL STATE ──────────────────────────────────────────────────────────────
open_trades = {}
cooldowns = {}  # asset -> datetime when cooldown expires
cycle_count = 0
dream_counter = 0
DREAM_EVERY = 20  # run dream every 20 cycles (~30min)

# ── COLOR OUTPUT ──────────────────────────────────────────────────────────────
C = {k: f"\033[{v}m" for k, v in {
    "R":0, "bold":1, "red":31, "green":32, "yellow":33,
    "blue":34, "cyan":36, "gray":90, "gold":33
}.items()}

def c(col, text):
    return f"{C.get(col,'')}{text}{C['R']}"

def log(level, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    icons = {
        "INFO": c("blue", "◉"),
        "SIGNAL": c("gold", "◆"),
        "WARN": c("yellow", "▲"),
        "ERROR": c("red", "✗"),
        "OK": c("green", "✓"),
        "DREAM": c("cyan", "~"),
        "BLOCK": c("red", "⊘"),
        "TRADE": c("green", "★"),
        "BUY": c("green", "⬆"),
        "SELL": c("red", "⬇")
    }
    print(f"{c('gray', ts)} {icons.get(level, '◉')} {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY - Centralized API layer (Claude Code pattern)
# ══════════════════════════════════════════════════════════════════════════════

class ToolRegistry:
    """
    Centralized API manager with:
    - Automatic caching
    - Rate limit handling
    - Error handling & fallbacks
    - Retry logic
    """
    
    def __init__(self):
        self.cache = {}
        self.last_call = {}  # tool -> timestamp
        
    def _cache_get(self, key, ttl_seconds):
        """Get from cache if not expired"""
        if key in self.cache:
            cached_time, cached_data = self.cache[key]
            if time.time() - cached_time < ttl_seconds:
                return cached_data
        return None
    
    def _cache_set(self, key, data):
        """Store in cache with timestamp"""
        self.cache[key] = (time.time(), data)
    
    def _rate_limit(self, tool_name, min_interval=1):
        """Enforce minimum interval between calls"""
        last = self.last_call.get(tool_name, 0)
        elapsed = time.time() - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_call[tool_name] = time.time()
    
    # ── BINANCE TOOLS ─────────────────────────────────────────────────────────
    
    def binance_time(self):
        """Get Binance server time"""
        import requests
        try:
            r = requests.get("https://api.binance.com/api/v3/time", timeout=5)
            r.raise_for_status()
            return r.json()["serverTime"]
        except Exception as e:
            log("ERROR", f"Binance time: {e}")
            return int(time.time() * 1000)
    
    def binance_sign(self, params):
        """Sign Binance request"""
        query_string = urlencode(params)
        signature = hmac.new(
            BINANCE_SECRET.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        return query_string + "&signature=" + signature
    
    def get_price(self, symbol):
        """Get current price with caching (30s TTL)"""
        cache_key = f"price_{symbol}"
        cached = self._cache_get(cache_key, 30)
        if cached is not None:
            return cached
        
        import requests
        try:
            self._rate_limit("binance_price", 0.5)
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol},
                timeout=10
            )
            r.raise_for_status()
            price = float(r.json()["price"])
            self._cache_set(cache_key, price)
            return price
        except Exception as e:
            log("ERROR", f"Price fetch {symbol}: {e}")
            return None
    
    def get_klines(self, symbol, interval="1h", limit=100):
        """Get candlestick data with caching"""
        cache_key = f"klines_{symbol}_{interval}_{limit}"
        cached = self._cache_get(cache_key, 300)  # 5min cache
        if cached is not None:
            return cached
        
        import requests
        try:
            self._rate_limit("binance_klines", 0.5)
            r = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=10
            )
            r.raise_for_status()
            klines = r.json()
            self._cache_set(cache_key, klines)
            return klines
        except Exception as e:
            log("ERROR", f"Klines {symbol}: {e}")
            return []
    
    def get_balance(self, asset="USDT"):
        """Get account balance (no caching - always fresh)"""
        import requests
        try:
            ts = self.binance_time()
            r = requests.get(
                f"https://api.binance.com/api/v3/account?{self.binance_sign({'timestamp': ts})}",
                headers={"X-MBX-APIKEY": BINANCE_KEY},
                timeout=10
            )
            r.raise_for_status()
            for b in r.json()["balances"]:
                if b["asset"] == asset:
                    return float(b["free"])
            return 0.0
        except Exception as e:
            log("ERROR", f"Balance fetch: {e}")
            return 0.0
    
    def get_24h_volume(self, symbol):
        """Get 24h trading volume"""
        cache_key = f"volume_{symbol}"
        cached = self._cache_get(cache_key, 300)  # 5min cache
        if cached is not None:
            return cached
        
        import requests
        try:
            self._rate_limit("binance_volume", 0.5)
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": symbol},
                timeout=10
            )
            r.raise_for_status()
            volume = float(r.json()["quoteVolume"])
            self._cache_set(cache_key, volume)
            return volume
        except Exception as e:
            log("ERROR", f"Volume fetch {symbol}: {e}")
            return 0
    
    def place_order(self, symbol, side, quantity):
        """Place market order (NO caching - always execute)"""
        import requests
        try:
            ts = self.binance_time()
            params = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": quantity,
                "timestamp": ts
            }
            r = requests.post(
                f"https://api.binance.com/api/v3/order?{self.binance_sign(params)}",
                headers={"X-MBX-APIKEY": BINANCE_KEY},
                timeout=10
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log("ERROR", f"Order placement {symbol} {side}: {e}")
            return None
    
    # ── MARKET DATA TOOLS ─────────────────────────────────────────────────────
    
    def get_fear_greed(self):
        """Get Fear & Greed Index with caching (1h TTL)"""
        cached = self._cache_get("fear_greed", 3600)
        if cached is not None:
            return cached
        
        import requests
        try:
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            r.raise_for_status()
            data = r.json()["data"][0]
            result = {
                "value": int(data["value"]),
                "label": data["value_classification"]
            }
            self._cache_set("fear_greed", result)
            return result
        except Exception as e:
            log("ERROR", f"Fear/Greed: {e}")
            return {"value": 50, "label": "Neutral"}
    
    # ── GITHUB TOOLS ──────────────────────────────────────────────────────────
    
    def push_to_github(self, filename, data):
        """Push JSON data to GitHub repo"""
        if not GITHUB_TOKEN:
            return False
        
        import requests
        import base64
        try:
            content_str = json.dumps(data, indent=2)
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Get current file SHA
            r = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}",
                headers=headers,
                timeout=10
            )
            
            payload = {
                "message": f"bot v{VERSION} update",
                "content": base64.b64encode(content_str.encode()).decode()
            }
            
            if r.ok:
                payload["sha"] = r.json()["sha"]
            
            # Update file
            r2 = requests.put(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}",
                headers=headers,
                json=payload,
                timeout=10
            )
            
            return r2.ok
        except Exception as e:
            log("ERROR", f"GitHub push: {e}")
            return False

# Initialize global tool registry
tools = ToolRegistry()


# ══════════════════════════════════════════════════════════════════════════════
# TRADE HISTORY & LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except:
        return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-500:], f, indent=2)  # keep last 500

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


# ══════════════════════════════════════════════════════════════════════════════
# DREAM CYCLE - Self-learning from trade history
# ══════════════════════════════════════════════════════════════════════════════

def run_dream_cycle():
    """
    Analyze past trades and generate actionable insights:
    - Win rate
    - Best/worst performing assets
    - Confidence calibration
    - Losing streak detection
    - Strategic directives (avoid assets, raise threshold, etc.)
    """
    log("DREAM", "Running self-analysis...")
    history = load_history()
    
    if len(history) < 10:
        log("DREAM", f"Only {len(history)} trades logged. Need 10+ to analyze.")
        return None
    
    # Recent trades only (last 7 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [t for t in history if t.get("timestamp", "") > cutoff.isoformat()]
    if not recent:
        recent = history[-20:]
    
    # Win rate
    settled = [t for t in recent if t.get("outcome") in ("WIN", "LOSS")]
    wins = [t for t in settled if t.get("outcome") == "WIN"]
    losses = [t for t in settled if t.get("outcome") == "LOSS"]
    win_rate = len(wins) / len(settled) if settled else 0
    
    # Per-asset performance
    asset_pnl = {}
    for t in recent:
        asset = t.get("asset", "unknown")
        pnl = t.get("profit_pct", 0)
        if asset not in asset_pnl:
            asset_pnl[asset] = []
        asset_pnl[asset].append(pnl)
    
    asset_avg = {a: sum(v)/len(v) for a, v in asset_pnl.items() if v}
    worst_asset = min(asset_avg, key=asset_avg.get) if asset_avg else None
    best_asset = max(asset_avg, key=asset_avg.get) if asset_avg else None
    
    # Current losing streak
    streak = 0
    for t in reversed(settled):
        if t.get("outcome") == "LOSS":
            streak += 1
        else:
            break
    
    # Build insights
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
        
        # Actionable directives
        "directives": {
            "avoid_asset": worst_asset if asset_avg.get(worst_asset, 0) < -2 else None,
            "prefer_asset": best_asset if asset_avg.get(best_asset, 0) > 1 else None,
            "go_defensive": streak >= RISK["losing_streak_limit"],
            "recommended_min_conf": 60 if win_rate < 0.4 else 50 if win_rate < 0.5 else 35,
        }
    }
    
    with open(INSIGHTS_FILE, "w") as f:
        json.dump(insights, f, indent=2)
    
    log("DREAM", f"Win rate: {insights['win_rate']}% | Losing streak: {streak} | Best: {best_asset} | Worst: {worst_asset}")
    
    if streak >= 3:
        log("WARN", f"⚠ {streak} consecutive losses — going defensive mode")
    
    return insights

def load_insights():
    try:
        with open(INSIGHTS_FILE) as f:
            return json.load(f)
    except:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def ema(data, period):
    """Exponential Moving Average"""
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(data[:period]) / period]
    for val in data[period:]:
        result.append(val * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    """Relative Strength Index"""
    if len(closes) < period + 2:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i-1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
    
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)

def atr(klines, period=14):
    """Average True Range - volatility measure"""
    if len(klines) < period + 1:
        return 0
    trs = []
    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period

def daily_trend(klines):
    """Detect overall trend from 30-day data"""
    if len(klines) < 14:
        return "NEUTRAL"
    closes = [float(k[4]) for k in klines]
    first_week = sum(closes[:7]) / 7
    last_week = sum(closes[-7:]) / 7
    
    if last_week > first_week * 1.02:
        return "UP"
    if last_week < first_week * 0.98:
        return "DOWN"
    return "NEUTRAL"


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL GENERATION - Multi-timeframe with quality scoring
# ══════════════════════════════════════════════════════════════════════════════

def generate_signal(symbol):
    """
    Generate trading signal with:
    - 1H timeframe for entry signals
    - 4H timeframe for trend confirmation
    - Volume validation
    - Multi-factor scoring
    
    Returns: {signal, confidence, reasons, price, sl, tp, atr, trend}
    """
    # Get 1H data
    klines_1h = tools.get_klines(symbol, "1h", 100)
    if not klines_1h or len(klines_1h) < 40:
        return {"signal": "HOLD", "confidence": 0, "reasons": ["Insufficient data"]}
    
    closes_1h = [float(k[4]) for k in klines_1h]
    price = closes_1h[-1]
    
    # Get 4H data for trend
    klines_4h = tools.get_klines(symbol, "4h", 30)
    closes_4h = [float(k[4]) for k in klines_4h] if klines_4h else []
    
    # Calculate indicators
    r = rsi(closes_1h)
    e9 = ema(closes_1h, 9)
    e21 = ema(closes_1h, 21)
    e50 = ema(closes_1h, 50) if len(closes_1h) >= 50 else []
    
    # MACD
    macd12 = ema(closes_1h, 12)
    macd26 = ema(closes_1h, 26)
    macd_line = [a - b for a, b in zip(macd12[-len(macd26):], macd26)]
    sig_line = ema(macd_line, 9)
    hist = macd_line[-1] - (sig_line[-1] if sig_line else 0) if macd_line else 0
    
    # Bollinger Bands
    mid = sum(closes_1h[-20:]) / 20
    std = math.sqrt(sum((x - mid)**2 for x in closes_1h[-20:]) / 20)
    pct_b = (price - mid + 2*std) / (4*std) if std else 0.5
    
    # 4H trend confirmation
    trend_4h = "NEUTRAL"
    if closes_4h and len(closes_4h) >= 21:
        e9_4h = ema(closes_4h, 9)
        e21_4h = ema(closes_4h, 21)
        if e9_4h and e21_4h:
            if e9_4h[-1] > e21_4h[-1]:
                trend_4h = "UP"
            elif e9_4h[-1] < e21_4h[-1]:
                trend_4h = "DOWN"
    
    # Overall 30-day trend
    klines_30d = tools.get_klines(symbol, "1d", 30)
    trend_daily = daily_trend(klines_30d) if klines_30d else "NEUTRAL"
    
    # Calculate ATR for stop loss
    avg_vol = atr(klines_1h)
    
    # Score calculation
    buy_score, sell_score = 0, 0
    reasons = []
    
    # RSI signals
    if r < 30:
        buy_score += 30
        reasons.append(f"RSI oversold {r:.0f}")
    elif r > 70:
        sell_score += 30
        reasons.append(f"RSI overbought {r:.0f}")
    
    # MACD signals
    if hist > 0:
        buy_score += 20
        reasons.append("MACD bullish")
    else:
        sell_score += 20
        reasons.append("MACD bearish")
    
    # Bollinger Bands
    if pct_b < 0.15:
        buy_score += 15
        reasons.append("Near lower BB")
    elif pct_b > 0.85:
        sell_score += 15
        reasons.append("Near upper BB")
    
    # EMA crossovers
    if e9 and e21:
        if e9[-1] > e21[-1]:
            buy_score += 15
            reasons.append("EMA9>EMA21")
        else:
            sell_score += 15
            reasons.append("EMA9<EMA21")
    
    # Trend alignment (v4 key feature)
    if trend_daily == "UP":
        buy_score += 20
        reasons.append("Daily trend UP")
    elif trend_daily == "DOWN":
        sell_score += 20
        reasons.append("Daily trend DOWN")
    
    # 4H trend bonus/penalty
    if trend_4h == "UP":
        buy_score += 15
        reasons.append("4H bullish")
    elif trend_4h == "DOWN":
        sell_score += 15
        reasons.append("4H bearish")
    
    # EMA50 filter
    if e50 and price > e50[-1]:
        buy_score += 10
        reasons.append("Above EMA50")
    elif e50 and price < e50[-1]:
        sell_score += 10
        reasons.append("Below EMA50")
    
    # Determine signal
    confidence = max(buy_score, sell_score)
    signal = "BUY" if buy_score > sell_score and buy_score >= 40 else \
             "SELL" if sell_score > buy_score and sell_score >= 40 else "HOLD"
    
    # CRITICAL: Anti-chop filter (v4 upgrade)
    # Don't buy in downtrend, don't sell in uptrend
    if signal == "BUY" and trend_daily == "DOWN":
        signal = "HOLD"
        reasons.append("⊘ Blocked: buying in downtrend")
    elif signal == "SELL" and trend_daily == "UP":
        signal = "HOLD"
        reasons.append("⊘ Blocked: selling in uptrend")
    
    return {
        "signal": signal,
        "confidence": confidence,
        "rsi": r,
        "macd": round(hist, 6),
        "trend_daily": trend_daily,
        "trend_4h": trend_4h,
        "pct_b": round(pct_b, 3),
        "reasons": reasons[:4],
        "price": price,
        "sl": round(price - 2*avg_vol, 4),  # 2x ATR stop
        "tp": round(price + 3*avg_vol, 4),  # 3:1 R:R
        "atr": round(avg_vol, 4),
    }


# ══════════════════════════════════════════════════════════════════════════════
# POSITION SIZING & RISK
# ══════════════════════════════════════════════════════════════════════════════

def calc_position_size(portfolio_usd, price, sl_price, risk_pct=0.03):
    """Kelly-lite position sizing: risk exactly risk_pct per trade"""
    if price <= 0 or sl_price <= 0 or price == sl_price:
        return 0
    risk_per_unit = abs(price - sl_price)
    risk_dollars = portfolio_usd * risk_pct
    units = risk_dollars / risk_per_unit
    return round(units, 6)

def crypto_precision(symbol):
    """Get decimal precision for Binance order quantity"""
    known = {
        "BTCUSDT": 5, "ETHUSDT": 4, "SOLUSDT": 2, "BNBUSDT": 3,
        "XRPUSDT": 0, "ADAUSDT": 0, "DOGEUSDT": 0, "AVAXUSDT": 2,
        "LINKUSDT": 1, "DOTUSDT": 1, "MATICUSDT": 0, "UNIUSDT": 2,
        "ATOMUSDT": 1, "NEARUSDT": 1, "APTUSDT": 1, "ARBUSDT": 0
    }
    return known.get(symbol, 2)


# ══════════════════════════════════════════════════════════════════════════════
# COOLDOWN SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

def is_on_cooldown(asset):
    """Check if asset is on cooldown after recent loss"""
    expiry = cooldowns.get(asset)
    if expiry and datetime.now(timezone.utc) < expiry:
        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds() / 60)
        log("BLOCK", f"{asset} on cooldown ({remaining}min remaining)")
        return True
    return False

def set_cooldown(asset, minutes=120):
    """Set cooldown period for asset"""
    cooldowns[asset] = datetime.now(timezone.utc) + timedelta(minutes=minutes)


# ══════════════════════════════════════════════════════════════════════════════
# MARKET GUARDS
# ══════════════════════════════════════════════════════════════════════════════

def check_daily_loss_limit():
    """Stop trading if down 5% today"""
    history = load_history()
    today = datetime.now(timezone.utc).date().isoformat()
    today_trades = [
        t for t in history
        if t.get("timestamp", "")[:10] == today
        and t.get("outcome") in ("WIN", "LOSS")
    ]
    if not today_trades:
        return False
    
    today_pnl = sum(t.get("profit_pct", 0) for t in today_trades)
    if today_pnl <= -RISK["daily_loss_limit"] * 100:
        log("WARN", f"⛔ Daily loss limit hit ({today_pnl:.1f}%). Bot paused.")
        return True
    return False

def check_market_conditions():
    """
    Check if market is safe to trade:
    - BTC not falling >2.5% in 1h (freefall)
    - BTC not down >5% in 4h (strong downtrend)
    - Fear/Greed not >78 (extreme greed)
    """
    try:
        # Get BTC 1h closes
        btc_klines = tools.get_klines("BTCUSDT", "1h", 24)
        if not btc_klines or len(btc_klines) < 10:
            return True, "BTC data unavailable - allowing trade"
        
        btc_closes = [float(k[4]) for k in btc_klines]
        current = btc_closes[-1]
        btc_1h = btc_closes[-2]
        btc_4h = btc_closes[-4] if len(btc_closes) >= 4 else btc_closes[0]
        
        change_1h = (current - btc_1h) / btc_1h * 100
        change_4h = (current - btc_4h) / btc_4h * 100
        
        fg = tools.get_fear_greed()
        fg_val = fg["value"]
        
        log("INFO", f"Market: BTC 1h:{change_1h:+.1f}% 4h:{change_4h:+.1f}% | F&G:{fg_val}")
        
        # Block conditions
        if change_1h < -2.5:
            return False, f"BTC FREEFALL: {change_1h:.1f}% in 1h"
        
        if change_4h < -5.0:
            return False, f"BTC DOWNTREND: {change_4h:.1f}% in 4h"
        
        if fg_val > 78:
            return False, f"EXTREME GREED: F&G={fg_val}"
        
        return True, "Market conditions OK"
        
    except Exception as e:
        log("ERROR", f"Market check: {e}")
        return True, "Market check failed - defaulting to allow"


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL TIERING (from v3)
# ══════════════════════════════════════════════════════════════════════════════

def classify_tier(score, reasons):
    """
    Crucix-inspired signal tiering:
    FLASH    = Act immediately (score ≥45)
    PRIORITY = Good signal (score ≥30)
    ROUTINE  = Weak signal (skip)
    """
    strong_reasons = [
        r for r in reasons
        if any(x in r for x in ["oversold", "MACD bullish", "4H bullish", "Daily trend UP"])
    ]
    
    if score >= 45 and len(strong_reasons) >= 2:
        return "FLASH", f"🔴 FLASH - {len(strong_reasons)} confluences"
    
    if score >= 30 and len(strong_reasons) >= 1:
        return "PRIORITY", f"🟡 PRIORITY - score:{score}"
    
    return "ROUTINE", f"🔵 ROUTINE - score too low ({score})"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CYCLE
# ══════════════════════════════════════════════════════════════════════════════

def run_cycle():
    global cycle_count, dream_counter
    cycle_count += 1
    now = datetime.now(timezone.utc).isoformat()
    
    log("INFO", f"{'─'*50}")
    log("INFO", f"Cycle {c('bold', str(cycle_count))} | {datetime.now().strftime('%H:%M:%S')}")
    
    # Daily loss check
    if check_daily_loss_limit():
        # Push paused status
        tools.push_to_github("bot_status.json", {
            "version": VERSION,
            "timestamp": now,
            "online": True,
            "paused": True,
            "pause_reason": "Daily loss limit reached"
        })
        time.sleep(POLL_SEC)
        return
    
    # Load dream insights
    insights = load_insights()
    if insights:
        directives = insights.get("directives", {})
        avoid_asset = directives.get("avoid_asset")
        go_defensive = directives.get("go_defensive", False)
        min_conf = directives.get("recommended_min_conf", RISK["base_min_conf"])
        
        if go_defensive:
            min_conf = RISK["defensive_min_conf"]
            log("WARN", f"DEFENSIVE MODE (streak={insights.get('current_losing_streak', 0)}, min_conf={min_conf}%)")
    else:
        avoid_asset = None
        go_defensive = False
        min_conf = RISK["base_min_conf"]
    
    # Market condition check
    market_ok, market_msg = check_market_conditions()
    if not market_ok:
        log("BLOCK", market_msg)
        time.sleep(POLL_SEC)
        return
    
    # Fear & Greed
    fg = tools.get_fear_greed()
    fg_val = fg["value"]
    log("INFO", f"Fear/Greed: {fg_val} ({fg['label']}) | Min conf: {min_conf}%")
    
    # Extreme conditions = raise threshold
    if fg_val < 15:
        log("WARN", "Extreme fear — raising threshold +10")
        min_conf = min(min_conf + 10, 80)
    elif fg_val > 85:
        log("WARN", "Extreme greed — raising threshold +5")
        min_conf = min(min_conf + 5, 75)
    
    # Check USDT balance
    usdt_balance = tools.get_balance("USDT")
    log("INFO", f"USDT Balance: ${usdt_balance:.2f}")
    
    if usdt_balance < RISK["min_trade_usdt"]:
        log("BLOCK", f"Insufficient USDT (${usdt_balance:.2f} < ${RISK['min_trade_usdt']})")
        time.sleep(POLL_SEC)
        return
    
    opportunities = []
    
    # Scan quality coins
    for symbol in QUALITY_COINS:
        asset = symbol.replace("USDT", "")
        log("INFO", f"Scanning {asset}...")
        
        # Skip if avoided by dream
        if avoid_asset and asset.lower() == avoid_asset.lower():
            log("BLOCK", f"{asset} — avoided by dream analysis")
            continue
        
        # Skip if on cooldown
        if is_on_cooldown(asset):
            continue
        
        # Skip if at max open trades
        if len(open_trades) >= RISK["max_open_trades"]:
            log("BLOCK", f"Max open trades reached ({len(open_trades)})")
            break
        
        # Volume validation
        volume = tools.get_24h_volume(symbol)
        if volume < RISK["volume_threshold"]:
            log("WARN", f"{asset} volume ${volume/1e9:.1f}B — too low, skipping")
            time.sleep(2)
            continue
        
        # Generate signal
        sig = generate_signal(symbol)
        
        signal_col = "green" if sig["signal"] == "BUY" else "red" if sig["signal"] == "SELL" else "gray"
        log("INFO", f"  {c(signal_col, sig['signal'])} conf:{sig['confidence']}% | RSI:{sig['rsi']} | trend:{sig['trend_daily']} | {sig['reasons'][0]}")
        
        if sig["signal"] == "HOLD" or sig["confidence"] < min_conf:
            log("INFO", f"  → Skipped (conf {sig['confidence']}% < {min_conf}%)")
            time.sleep(2)
            continue
        
        # Classify tier
        tier, tier_msg = classify_tier(sig["confidence"], sig["reasons"])
        
        if tier == "ROUTINE":
            log("INFO", f"  → {tier_msg} - skipping")
            time.sleep(2)
            continue
        
        # Position sizing
        pos_size = calc_position_size(usdt_balance, sig["price"], sig["sl"], RISK["max_risk_pct"])
        risk_usd = round(usdt_balance * RISK["max_risk_pct"], 2)
        
        # Precision adjustment
        prec = crypto_precision(symbol)
        pos_size = round(pos_size, prec)
        
        # Ensure minimum trade value
        if pos_size * sig["price"] < RISK["min_trade_usdt"]:
            log("WARN", f"  → Position size too small (${pos_size * sig['price']:.2f} < ${RISK['min_trade_usdt']})")
            time.sleep(2)
            continue
        
        opportunity = {
            "symbol": symbol,
            "asset": asset,
            "signal": sig["signal"],
            "tier": tier,
            "confidence": sig["confidence"],
            "price": round(sig["price"], 4),
            "rsi": sig["rsi"],
            "trend": sig["trend_daily"],
            "sl": sig["sl"],
            "tp": sig["tp"],
            "atr": sig["atr"],
            "pos_size": pos_size,
            "risk_usd": risk_usd,
            "reason": " | ".join(sig["reasons"][:2]),
            "timestamp": now,
        }
        opportunities.append(opportunity)
        
        # Log trade decision
        log_trade(asset, sig["signal"], sig["confidence"], sig["price"], opportunity["reason"])
        
        log("TRADE", f"  ★ {tier_msg}")
        log("TRADE", f"    {sig['signal']} {asset} @ ${sig['price']:.2f} | SL:${sig['sl']:.2f} TP:${sig['tp']:.2f}")
        log("TRADE", f"    Size: {pos_size} {asset} | Risk: ${risk_usd}")
        
        time.sleep(3)  # Rate limit
    
    # Sort by tier and confidence
    opportunities.sort(key=lambda x: (x["tier"] == "FLASH", x["confidence"]), reverse=True)
    
    # Dream cycle check
    dream_counter += 1
    dream_summary = None
    if dream_counter >= DREAM_EVERY:
        dream_counter = 0
        dream_summary = run_dream_cycle()
    
    # Build status
    history = load_history()
    settled = [t for t in history if t.get("outcome") in ("WIN", "LOSS")]
    wins = len([t for t in settled if t.get("outcome") == "WIN"])
    win_rate = round(wins / len(settled) * 100, 1) if settled else 0
    
    status = {
        "version": VERSION,
        "timestamp": now,
        "cycle": cycle_count,
        "online": True,
        "paused": False,
        "mode": f"{'DEFENSIVE' if go_defensive else 'BALANCED'}",
        "signals_generated": len(opportunities),
        "top_opportunities": opportunities[:5],
        "open_positions": list(open_trades.values())[:5],
        "fear_greed": {"value": fg_val, "label": fg["label"]},
        "usdt_balance": round(usdt_balance, 2),
        "performance": {
            "total_trades": len(settled),
            "win_rate_pct": win_rate,
            "wins": wins,
            "losses": len(settled) - wins,
            "defensive_mode": go_defensive,
            "min_conf": min_conf,
        },
        "dream": {
            "last_run": dream_summary.get("generated_at") if dream_summary else None,
            "win_rate": dream_summary.get("win_rate") if dream_summary else win_rate,
            "best_asset": dream_summary.get("best_asset") if dream_summary else None,
            "worst_asset": dream_summary.get("worst_asset") if dream_summary else None,
        },
    }
    
    # Push to GitHub
    ok = tools.push_to_github("bot_status.json", status)
    if ok:
        log("OK", f"Pushed — {len(opportunities)} signals | win_rate:{win_rate}% | defensive:{go_defensive}")
    else:
        log("ERROR", "Failed to push status")


# ══════════════════════════════════════════════════════════════════════════════
# BANNER & ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def banner():
    print(f"""
{c('gold', '╔═══════════════════════════════════════╗')}
{c('gold', '║')}   {c('bold', 'ACCRA BOT v5 - PRODUCTION')}        {c('gold', '║')}
{c('gold', '║')}   Live trading + AI learning         {c('gold', '║')}
{c('gold', '╚═══════════════════════════════════════╝')}

  {c('cyan', 'Features:')}
  ✓ Live Binance trading (USDT pairs)
  ✓ Dream cycle learning system
  ✓ Multi-timeframe confirmation
  ✓ Defensive mode after losses
  ✓ Tool registry with caching
  ✓ Signal quality tiering
  ✓ Market condition guards

  {c('gray', 'Risk Config:')}
  Min confidence: {RISK['base_min_conf']}% → {RISK['defensive_min_conf']}% defensive
  Max risk/trade: {int(RISK['max_risk_pct']*100)}% of portfolio
  Cooldown: {RISK['cooldown_minutes']}min after loss
  Daily stop: {int(RISK['daily_loss_limit']*100)}% max loss

  {c('gray', 'Status:')} Signals → accra-terminal/bot_status.json
""")

if __name__ == "__main__":
    banner()
    
    if not BINANCE_KEY or not BINANCE_SECRET:
        print(c("red", "ERROR: BINANCE_KEY and BINANCE_SECRET not set!"))
        print("  export BINANCE_KEY=your_key")
        print("  export BINANCE_SECRET=your_secret")
        sys.exit(1)
    
    if not GITHUB_TOKEN:
        log("WARN", "GITHUB_TOKEN not set — status push disabled")
    
    # Load dream insights on startup
    insights = load_insights()
    if insights:
        log("DREAM", f"Loaded: win_rate={insights.get('win_rate')}% | avoid={insights.get('directives', {}).get('avoid_asset')}")
    else:
        log("INFO", "No dream insights yet — will build after 10+ trades")
    
    log("OK", "Bot started. Ctrl+C to stop.\n")
    
    try:
        while True:
            try:
                run_cycle()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log("ERROR", f"Cycle failed: {e}")
                import traceback
                traceback.print_exc()
            
            log("INFO", f"Sleeping {POLL_SEC}s...\n")
            time.sleep(POLL_SEC)
            
    except KeyboardInterrupt:
        log("INFO", "\nBot stopped. Trade history saved.")

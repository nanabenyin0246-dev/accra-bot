import os, time, json, hmac, hashlib, requests, logging, re, subprocess
from datetime import datetime, timezone
from urllib.parse import urlencode

logging.basicConfig(filename="bot.log", level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")

def log(msg, level="info"):
    print(msg)
    getattr(logging, level)(msg)

# ── HYPERLIQUID ───────────────────────────────────────────
try:
    from hyperliquid_trader import hl_place_order, hl_get_balance, hl_get_positions, hl_close_position
    HL_ENABLED = True
except Exception as _hl_err:
    HL_ENABLED = False

def hl_trade(signal, coin="SOL", pct=0.2):
    if not HL_ENABLED:
        return
    try:
        bal = hl_get_balance()
        if bal < 5:
            log("[HL] Balance too low: $%.2f" % bal)
            return
        amount = round(bal * pct, 2)
        is_buy = signal.upper() == "BUY"
        result = hl_place_order(coin, is_buy, amount, leverage=2)
        log("[HL] %s %s $%.2f status=%s" % (signal, coin, amount, result.get("status")))
    except Exception as e:
        log("[HL] Trade error: %s" % e)

# ── TRADE.XYZ ────────────────────────────────────────────
# STUB / UNIMPLEMENTED: tradexyz_trader.py's functions are all placeholders
# (xyz_get_balance always returns 0.0, xyz_close_position is a no-op, and
# xyz_place_order doesn't exist there at all). The XYZ trade paths below
# call xyz_place_order/xyz_close_position directly, which would raise
# NameError if ever reached. This was previously only disabled by accident
# (eth_account isn't in requirements.txt, so the import failed and set
# XYZ_ENABLED = False) rather than by design. Disabling explicitly instead
# of relying on that accident. Re-enable only once tradexyz_trader.py has
# a real implementation and xyz_place_order/xyz_close_position are
# actually imported below.
XYZ_ENABLED = False


# Stub xyz functions - always defined, overridden if import succeeds
def xyz_get_positions(): return []
def xyz_get_balance(): return 0.0
def xyz_free_margin(): return 0.0
def xyz_get_price(s): return 0.0
def xyz_leverage_for(s): return 1
def xyz_min_margin(s): return 999
def _get_xyz_meta(s): return None
STOCKS = []; COMMODITIES = []; FOREX = []; INDICES = []
def xyz_score_asset(ticker, prices, closes_cache):
    """Score a trade.xyz asset using technicals. Returns (score, signal)."""
    import statistics
    try:
        price = prices.get(ticker, 0)
        if price <= 0:
            return 0, "HOLD"
        # Get closes from cache or skip
        closes = closes_cache.get(ticker, [])
        if len(closes) < 20:
            return 0, "HOLD"
        score = 0
        signal = "HOLD"
        # RSI
        try:
            rsi = calc_rsi(closes)
            if rsi < 30:
                score += 30
            elif rsi < 40:
                score += 15
            elif rsi > 70:
                score -= 30
            elif rsi > 60:
                score -= 15
        except:
            pass
        # EMA trend
        try:
            ema20 = calc_ema(closes, 20)
            ema50 = calc_ema(closes, 50)
            if ema20[-1] > ema50[-1]:
                score += 10
            else:
                score -= 10
        except:
            pass
        # MACD
        try:
            macd, signal_line, _ = calc_macd(closes)
            if macd[-1] > signal_line[-1]:
                score += 15
            else:
                score -= 10
        except:
            pass
        # BB position
        try:
            upper, mid, lower = calc_bb(closes)
            if price < lower[-1]:
                score += 20
            elif price > upper[-1]:
                score -= 20
        except:
            pass
        if score >= 25:
            signal = "BUY"
        elif score <= -20:
            signal = "SELL"
        return score, signal
    except Exception as e:
        return 0, "HOLD"

def xyz_get_closes(ticker, limit=60):
    """Fetch OHLCV closes for a trade.xyz asset via Hyperliquid candles."""
    try:
        import time
        now_ms  = int(time.time() * 1000)
        start   = now_ms - limit * 60 * 60 * 1000  # hourly candles
        r = requests.post("https://api.hyperliquid.xyz/info", json={
            "type":       "candleSnapshot",
            "req": {
                "coin":       "xyz:" + ticker,
                "interval":   "1h",
                "startTime":  start,
                "endTime":    now_ms
            }
        }, timeout=10)
        candles = r.json()
        if isinstance(candles, list) and len(candles) > 0:
            return [float(c["c"]) for c in candles]
    except:
        pass
    return []


def xyz_active_asset_classes():
    """
    Return which asset classes are actively trading right now.
    Avoids scanning stocks when NYSE is closed.
    """
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    now_ny  = now_utc - timedelta(hours=4)   # EDT
    now_tok = now_utc + timedelta(hours=9)   # JST
    now_lon = now_utc + timedelta(hours=1)   # BST

    active = ["COMMODITIES", "CRYPTO"]  # always active

    # Forex: Mon-Fri 24h
    if now_utc.weekday() < 5:
        active.append("FOREX")

    # US Stocks: NYSE 9:30-16:00 NY time weekdays
    if now_ny.weekday() < 5 and (
        (now_ny.hour == 9 and now_ny.minute >= 30) or
        (10 <= now_ny.hour < 16)):
        active.append("US_STOCKS")

    # Asian stocks: Tokyo 9-15 JST weekdays
    if now_tok.weekday() < 5 and 9 <= now_tok.hour < 15:
        active.append("ASIA_STOCKS")

    # European stocks: London 8-16 BST weekdays  
    if now_lon.weekday() < 5 and 8 <= now_lon.hour < 16:
        active.append("EU_STOCKS")

    return active


def xyz_ai_consensus(ticker, price, is_buy_candidate):
    """
    Ask AI providers to vote on a trade.
    Returns (agrees, confidence, reason)
    Only trades when AI agrees with confidence >= 65.
    """
    try:
        # Ensure AI providers are initialized
        build_ai_providers()
        direction = "BUY/LONG" if is_buy_candidate else "SELL/SHORT"
        prompt = """You are a professional trader. Should we %s %s at $%.2f right now?
Fear & Greed Index: 14 (Extreme Fear)
Consider: technicals, macro conditions, risk/reward.
Respond ONLY in JSON: {"vote": "BUY" or "SELL" or "HOLD", "confidence": 0-100, "reason": "one line"}
Be decisive. If uncertain vote HOLD.""" % (direction, ticker, price)

        result = call_multi_ai(prompt, "Return valid JSON only. No markdown.")
        if not result:
            return False, 0, "No AI response"

        import json as _j
        data     = _j.loads(result)
        vote     = data.get("vote", "HOLD").upper()
        conf     = int(data.get("confidence", 0))
        reason   = data.get("reason", "")
        expected = "BUY" if is_buy_candidate else "SELL"
        agrees   = (vote == expected) and (conf >= 65)
        log("[XYZ AI] %s vote=%s conf=%d%% | %s" % (ticker, vote, conf, reason[:50]))
        return agrees, conf, reason
    except Exception as e:
        log("[XYZ AI] error: %s" % e)
        return False, 0, str(e)

def xyz_multi_ai_vote(ticker, price, is_buy_candidate):
    agrees, conf, reason = xyz_ai_consensus(ticker, price, is_buy_candidate)
    if not agrees:
        log("[XYZ] AI BLOCKED %s conf=%d%%" % (ticker, conf))
        return False, reason
    log("[XYZ] AI APPROVED %s conf=%d%%" % (ticker, conf))
    return True, reason

def xyz_scan_and_trade():
    """
    Safe autonomous trade.xyz engine.
    - Max 1 open position at a time
    - Min balance $15 to trade
    - Stop loss built into position sizing
    - Only trades when score >= 30 (strong signal)
    - Scans every 5 cycles not every cycle
    """
    if not XYZ_ENABLED:
        return

    # Only scan every 5 cycles to reduce overtrading
    global _xyz_scan_counter
    try: _xyz_scan_counter
    except: _xyz_scan_counter = 0
    _xyz_scan_counter += 1
    if _xyz_scan_counter < 5:
        return
    _xyz_scan_counter = 0

    try:
        from tradexyz_trader import (
            _get_xyz_meta, xyz_leverage_for, xyz_min_margin,
            xyz_free_margin, xyz_get_price, xyz_get_balance,
            STOCKS, COMMODITIES, FOREX, INDICES
        )

        # Check free margin - need at least $5
        free = xyz_free_margin()
        total = xyz_get_balance()
        log("[XYZ] Balance: $%.2f total, $%.2f free" % (total, free))

        if total < 5:
            log("[XYZ] Balance too low: $%.2f - not trading" % total)
            return

        if free < 5:
            log("[XYZ] No free margin: $%.2f - positions full" % free)
            # Check if open positions need stop loss
            _xyz_check_stops()
            return

        # Max 1 position at a time
        open_pos = set()
        try:
            for p in xyz_get_positions():
                coin = p.get("position", {}).get("coin", "")
                open_pos.add(coin.replace("xyz:", ""))
        except:
            pass

        if len(open_pos) >= 1:
            log("[XYZ] Max positions reached (%d open) - waiting" % len(open_pos))
            _xyz_check_stops()
            return

        # Active market filter
        active = xyz_active_asset_classes()
        log("[XYZ] Active markets: %s" % ", ".join(active))

        def _is_active(ticker):
            if ticker in COMMODITIES: return True
            if ticker in FOREX:       return "FOREX" in active
            if ticker in INDICES:     return "US_STOCKS" in active
            if ticker in STOCKS:      return "US_STOCKS" in active
            return True

        # Scan assets
        meta        = _get_xyz_meta(fresh=True)
        all_tickers = [u["name"].replace("xyz:", "") for u in meta["universe"]]

        log("[XYZ] Scanning %d assets..." % len(all_tickers))

        prices       = {}
        closes_cache = {}

        for t in all_tickers:
            if t in open_pos or not _is_active(t):
                continue
            try:
                price = xyz_get_price(t)
                if price <= 0:
                    continue
                prices[t] = price
                closes = xyz_get_closes(t)
                if closes:
                    closes_cache[t] = closes
            except:
                continue

        # Find best signal - require score >= 30 (strong only)
        best_score  = 0
        best_ticker = None
        best_signal = "HOLD"

        for t, price in prices.items():
            score, sig = xyz_score_asset(t, prices, closes_cache)
            if sig != "HOLD" and abs(score) >= 30 and abs(score) > abs(best_score):
                best_score  = score
                best_ticker = t
                best_signal = sig

        # Geopolitical override
        try:
            global _hz_val, _nk_val
            try: hz = _hz_val
            except: hz = "UNKNOWN"
            try: nk = _nk_val
            except: nk = False

            if hz == "CLOSED" and "CL" not in open_pos:
                log("[XYZ] HORMUZ CLOSED - forcing CL long!")
                best_ticker = "CL"
                best_signal = "BUY"
                best_score  = 55
            elif hz == "DISRUPTED" and best_ticker not in ["CL","BRENTOIL","GOLD","SILVER"]:
                best_ticker = "GOLD"
                best_signal = "BUY"
                best_score  = max(best_score, 30)
            if nk and "GOLD" not in open_pos:
                log("[XYZ] DPRK - forcing GOLD long!")
                best_ticker = "GOLD"
                best_signal = "BUY"
                best_score  = 40
        except Exception as geo_e:
            log("[XYZ] Geo error: %s" % geo_e)

        if best_ticker and best_signal != "HOLD":
            lev    = xyz_leverage_for(best_ticker)
            min_m  = xyz_min_margin(best_ticker)
            # Use 30% of free margin, respect minimum
            amount = max(min_m, round(free * 0.30, 2))
            # Never use more than 50% of total balance in one trade
            amount = min(amount, round(total * 0.50, 2))
            is_buy = best_signal == "BUY"
            direction = "LONG" if is_buy else "SHORT"

            log("[XYZ] %s %s score=%d lev=%dx margin=$%.2f" % (
                direction, best_ticker, best_score, lev, amount))

            # AI GATE - must pass before executing
            ai_ok, ai_reason = xyz_multi_ai_vote(
                best_ticker, prices.get(best_ticker, 0), is_buy)
            if not ai_ok:
                log("[XYZ] Trade blocked by AI: %s" % ai_reason)
                return

            result = xyz_place_order(best_ticker, is_buy, amount, leverage=lev)
            status = result.get("status")
            log("[XYZ] %s %s $%.2f → %s" % (
                direction, best_ticker, amount, status))

            if status == "ok":
                telegram("<b>XYZ %s</b>\n%s @ $%.2f\nScore:%d Lev:%dx $%.2f\nAI:%s" % (
                    direction, best_ticker,
                    prices.get(best_ticker, 0),
                    best_score, lev, amount, ai_reason[:40]))
        else:
            log("[XYZ] No strong opportunity (need score>=30)")

    except Exception as e:
        log("[XYZ] Scan error: %s" % e)

def _xyz_check_stops():
    """Check open xyz positions for stop loss / take profit."""
    try:
        import requests as _rq
        from dotenv import load_dotenv as _lde
        import os as _os
        _lde()
        HL_WALLET = _os.getenv("HYPERLIQUID_WALLET","")
        r = _rq.post("https://api.hyperliquid.xyz/info",
                     json={"type": "clearinghouseState",
                           "user": HL_WALLET, "dex": "xyz"},
                     timeout=10)
        positions = r.json().get("assetPositions", [])
        for p in positions:
            pos    = p.get("position", {})
            szi    = float(pos.get("szi", 0))
            if szi == 0:
                continue
            ticker  = pos.get("coin","").replace("xyz:","")
            pnl     = float(pos.get("unrealizedPnl", 0))
            margin  = float(pos.get("marginUsed", 1))
            pnl_pct = (pnl / margin * 100) if margin > 0 else 0

            # Stop loss: -8% of margin
            # Take profit: +15% of margin
            if pnl_pct <= -8:
                log("[XYZ] STOP LOSS %s pnl=%.1f%% - closing" % (ticker, pnl_pct))
                xyz_close_position(ticker)
                telegram("<b>XYZ STOP LOSS</b>\n%s\nPnL: %.1f%%" % (ticker, pnl_pct))
            elif pnl_pct >= 15:
                log("[XYZ] TAKE PROFIT %s pnl=%.1f%% - closing" % (ticker, pnl_pct))
                xyz_close_position(ticker)
                telegram("<b>XYZ TAKE PROFIT</b>\n%s\nPnL: %.1f%%" % (ticker, pnl_pct))
    except Exception as e:
        log("[XYZ] Stop check error: %s" % e)


def xyz_trade(signal, ticker=None, pct=0.4, _cycle=[0]):
    """Called after crypto signal - mirrors on best xyz asset."""
    if not XYZ_ENABLED:
        return
    try:
        bal = xyz_get_balance()
        if bal < 10:
            log("[XYZ] Balance too low: $%.2f" % bal)
            return
        amount = round(bal * pct, 2)
        is_buy = signal.upper() == "BUY"
        # If no ticker specified, find best opportunity
        if ticker is None:
            from tradexyz_trader import _get_xyz_meta
            meta    = _get_xyz_meta()
            tickers = [u["name"].replace("xyz:", "") for u in meta["universe"]]
            closes_cache = {}
            prices_map   = {}
            for t in tickers[:20]:  # quick scan top 20
                try:
                    p = xyz_get_price(t)
                    if p > 0:
                        prices_map[t] = p
                        c = xyz_get_closes(t, limit=30)
                        if c:
                            closes_cache[t] = c
                except:
                    pass
            best_t, best_s = None, 0
            for t in prices_map:
                sc, sig = xyz_score_asset(t, prices_map, closes_cache)
                if sig == signal and sc > best_s:
                    best_s = sc
                    best_t = t
            ticker = best_t or "GOLD"
        result = xyz_place_order(ticker, is_buy, amount, leverage=3)
        log("[XYZ] %s %s $%.2f status=%s" % (signal, ticker, amount, result.get("status")))
    except Exception as e:
        log("[XYZ] Trade error: %s" % e)

BINANCE_KEY    = os.getenv("BINANCE_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
ALPACA_KEY     = os.getenv("ALPACA_KEY", "")
ALPACA_SECRET  = os.getenv("ALPACA_SECRET", "")
ALPACA_BASE    = os.getenv("ALPACA_BASE", "https://paper-api.alpaca.markets")
HFM_ACCOUNT    = os.getenv("HFM_ACCOUNT", "")
EXNESS_LOGIN   = os.getenv("EXNESS_LOGIN", "")
GROQ_KEY       = os.getenv("GROQ_KEY", "")
MISTRAL_KEY    = os.getenv("MISTRAL_KEY", "")
CEREBRAS_KEY   = os.getenv("CEREBRAS_KEY", "")
DEEPSEEK_KEY   = os.getenv("DEEPSEEK_KEY", "")
GEMINI_KEY     = os.getenv("GEMINI_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT", "")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO    = os.getenv("GITHUB_REPO", "nanabenyin0246-dev/accra-terminal")
SLEEP_SECS     = int(os.getenv("SLEEP_SECS", "60"))
PAPER_MODE     = os.getenv("PAPER_MODE", "true").lower() not in ("false", "0", "no")
log(f"  [DIAG] PAPER_MODE env={repr(os.getenv('PAPER_MODE', '<unset>'))} resolved={PAPER_MODE}")
_raw_mdl       = os.getenv("MAX_DAILY_LOSS_USD", "")
MAX_DAILY_LOSS_USD     = float(_raw_mdl) if _raw_mdl else None
log(f"  [DIAG] MAX_DAILY_LOSS_USD raw={repr(_raw_mdl)} resolved={MAX_DAILY_LOSS_USD!r}")
MAX_OPEN_POSITIONS     = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
POLY_ENABLED           = os.getenv("POLY_ENABLED", "false").lower() in ("true", "1", "yes")
_VOLUME_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")  # e.g. "/data" on Railway
LOG_FILE       = os.path.join(_VOLUME_PATH, "trade_log.json")
DAILY_LOSS_FILE = os.path.join(_VOLUME_PATH, "daily_loss_state.json")
STARTING_BALANCE_FILE = os.path.join(_VOLUME_PATH, "starting_balance_state.json")
OPEN_TRADES_FILE = os.path.join(_VOLUME_PATH, "open_trades_state.json")
INSIGHTS_FILE  = os.path.join(_VOLUME_PATH, "dream_insights.json")
DREAM_EVERY    = 20
dream_counter  = 0
STATUS_FILE    = "bot_status.json"
STRATEGY_FILE  = "bot_strategy.json"

DEFAULT_STRATEGY = {
    "mode": "balanced",
    "min_confidence": 22,
    "max_open_trades": 1,
    "crypto_enabled": True,
    "stocks_enabled": True,
    "hfm_enabled": False,
    "top_n_crypto": 30,
    "top_n_stocks": 30,
    "sl_multiplier": 1.0,
    "tp_multiplier": 1.0,
    "avoid_assets": ["STOUSDT","SOLVUSDT","BIFIUSDT","NIGHTUSDT","DUSDT","UUSDT","币安人生USDT"],
    "prefer_assets": [],
    "market_condition": "neutral",
    "updated_by": "default",
}

RISK_PROFILES = {
    "aggressive":   {"sl": 0.10, "tp": 0.15, "trail": 0.05},
    "balanced":     {"sl": 0.10, "tp": 0.10, "trail": 0.03},
    "conservative": {"sl": 0.10, "tp": 0.07, "trail": 0.03},
}

HFM_INSTRUMENTS = {
    "XAUUSD": "Metal",  "XAGUSD": "Metal",  "XPTUSD": "Metal",
    "EURUSD": "Forex",  "GBPUSD": "Forex",  "USDJPY": "Forex",
    "USDGHS": "Forex",  "AUDUSD": "Forex",  "USDCAD": "Forex",
    "USDCHF": "Forex",  "NZDUSD": "Forex",  "EURGBP": "Forex",
    "EURJPY": "Forex",  "GBPJPY": "Forex",
    "USOIL":  "Commodity", "UKOIL": "Commodity",
    "NATGAS": "Commodity", "COPPER": "Commodity",
    "SP500":  "Index",  "US30": "Index", "NAS100": "Index",
}

trade_log = []
open_trades = {}
_reentry_block = {}  # symbol -> {sl_price, timestamp}
_fg_cache = {"value": 50, "label": "Neutral", "ts": 0}
_news_cache = {}
_fund_cache = {}
_top_crypto_cache = {"coins": [], "ts": 0}
_top_stock_cache = {"stocks": [], "ts": 0}
cycle_count = 0
_lot_size_cache = {}   # symbol -> {"step": float, "decimals": int, "min_notional": float}
_paper_fills = []      # paper-mode simulated fills
_daily_realized_pnl_usd = 0.0
_daily_pnl_date = None          # UTC calendar date (datetime.date) for current window
_daily_loss_blocked = False

# ============================================================
# TRUMP ANALYSIS MODULE - Remove by setting to False
# When Trump leaves presidency: TRUMP_ANALYSIS_ENABLED = False
# ============================================================
TRUMP_ANALYSIS_ENABLED = True
AI_PROVIDERS = []
_ai_usage = {"groq":0,"gemini":0,"openrouter":0,"current":0}
AI_ROTATE_EVERY = 3

def build_ai_providers():
    global AI_PROVIDERS
    AI_PROVIDERS = []
    if GROQ_KEY and False:  # disabled - account restricted
        AI_PROVIDERS.append({"name":"groq","url":"https://api.groq.com/openai/v1/chat/completions",
            "model":"llama-3.3-70b-versatile","headers":{"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},"max_tokens":300})
    if GEMINI_KEY and False:  # disabled - quota exceeded on this key/plan (HTTP 429)
        AI_PROVIDERS.append({"name":"gemini",
            "url":f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_KEY}",
            "model":"gemini-3.6-flash","headers":{"Content-Type":"application/json"},"max_tokens":300,"gemini":True})
    if OPENROUTER_KEY and False:  # disabled - key invalid/revoked (HTTP "User not found")
        AI_PROVIDERS.append({"name":"openrouter","url":"https://openrouter.ai/api/v1/chat/completions",
            "model":"meta-llama/llama-3.3-70b-instruct:free","headers":{"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},"max_tokens":300})
    if MISTRAL_KEY:
        AI_PROVIDERS.append({"name":"mistral","url":"https://api.mistral.ai/v1/chat/completions",
            "model":"mistral-small-latest","headers":{"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"},"max_tokens":300})
    if CEREBRAS_KEY:
        AI_PROVIDERS.append({"name":"cerebras","url":"https://api.cerebras.ai/v1/chat/completions",
            "model":"llama-4-scout-17b-16e-instruct","headers":{"Authorization":f"Bearer {CEREBRAS_KEY}","Content-Type":"application/json"},"max_tokens":300})
    SAMBANOVA_KEY = os.getenv("SAMBANOVA_KEY", "")
    if SAMBANOVA_KEY:
        AI_PROVIDERS.append({"name":"sambanova","url":"https://api.sambanova.ai/v1/chat/completions",
            "model":"Meta-Llama-3.3-70B-Instruct","headers":{"Authorization":f"Bearer {SAMBANOVA_KEY}","Content-Type":"application/json"},"max_tokens":300})
    if DEEPSEEK_KEY and False:  # disabled - insufficient balance
        AI_PROVIDERS.append({"name":"deepseek","url":"https://api.deepseek.com/chat/completions",
            "model":"deepseek-chat","headers":{"Authorization":f"Bearer {DEEPSEEK_KEY}","Content-Type":"application/json"},"max_tokens":300})
    log(f"  AI Providers: {[p['name'] for p in AI_PROVIDERS]}")

def call_multi_ai(prompt, system="Return valid JSON only.", max_tokens=None):
    global _ai_usage
    if not AI_PROVIDERS:
        return None
    idx = (_ai_usage["current"] // AI_ROTATE_EVERY) % len(AI_PROVIDERS)
    _ai_usage["current"] += 1
    for attempt in range(len(AI_PROVIDERS)):
        p = AI_PROVIDERS[(idx+attempt) % len(AI_PROVIDERS)]
        name = p["name"]
        _mt = max_tokens if max_tokens is not None else p["max_tokens"]
        try:
            if p.get("gemini"):
                body = {"contents":[{"parts":[{"text":f"{system}\n\n{prompt}"}]}],
                        "generationConfig":{"maxOutputTokens":_mt,"temperature":0.1}}
                r = requests.post(p["url"],headers=p["headers"],json=body,timeout=20)
                if r.ok:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    text = re.sub(r"```json|```","",text).strip()
                    # Fix unterminated JSON strings
                    try:
                        import json as _j
                        _j.loads(text)
                    except:
                        text = text[:text.rfind('}')+1] if '}' in text else None
                    _ai_usage[name] = _ai_usage.get(name,0)+1
                    log(f"  [AI:{name}] OK")
                    return text
                raise Exception(f"HTTP {r.status_code}: {r.text[:300]}")
            else:
                body = {"model":p["model"],"max_tokens":_mt,"temperature":0.1,
                        "messages":[{"role":"system","content":system},{"role":"user","content":prompt}]}
                r = requests.post(p["url"],headers=p["headers"],json=body,timeout=20)
                rj = r.json()
                if "choices" not in rj:
                    raise Exception(rj.get("error",{}).get("message","no choices")[:60])
                text = rj["choices"][0]["message"]["content"].strip()
                text = re.sub(r"```json|```","",text).strip()
                _ai_usage[name] = _ai_usage.get(name,0)+1
                log(f"  [AI:{name}] OK G:{_ai_usage.get('groq',0)} Gem:{_ai_usage.get('gemini',0)} OR:{_ai_usage.get('openrouter',0)}")
                return text
        except Exception as e:
            log(f"  [AI:{name}] Failed:{str(e)[:300]} trying next...","warning")
    log("  [AI] All providers failed - using rule-based fallback","warning")
    # Crucix-inspired: rule-based engine takes over when LLM unavailable
    # This ensures AI failures never crash the trading cycle
    return None  # Caller handles None gracefully
ai_strategy_cycle = 0
AI_STRATEGY_INTERVAL = 5  # Run AI strategy every 5 cycles
ai_mode_enabled = True     # Can be toggled from terminal
failsafe_active = False
failsafe_reason = ""
ai_consecutive_failures = 0
MAX_AI_FAILURES = 3  # Activate failsafe after 3 consecutive AI failures

# FAILSAFE STRATEGY - protects capital when AI is down
FAILSAFE_STRATEGY = {
    "mode": "conservative",
    "min_confidence": 60,    # Very high threshold
    "max_open_trades": 1,    # Limit exposure
    "crypto_enabled": True,
    "stocks_enabled": True, # Disable stocks in failsafe
    "hfm_enabled": False,
    "top_n_crypto": 5,       # Only top 5 safest coins
    "top_n_stocks": 0,
    "prefer_assets": ["BTCUSDT", "XAUUSD"],  # Safe havens
    "avoid_assets": [],
    "sl_multiplier": 0.7,    # Tighten stops by 30%
    "tp_multiplier": 0.8,
    "market_condition": "bear",  # Assume worst case
    "updated_by": "failsafe",
}


def load_strategy():
    try:
        if os.path.exists(STRATEGY_FILE):
            with open(STRATEGY_FILE) as f:
                saved = json.load(f)
                merged = {**DEFAULT_STRATEGY, **saved}
                if saved.get("updated_by") != "default":
                    log(f"  Strategy: {saved.get('mode')} by {saved.get('updated_by')}")
                return merged
    except Exception as e:
        log(f"  [Strategy] {e}", "warning")
    return DEFAULT_STRATEGY.copy()


def get_risk(strategy):
    mode = strategy.get("mode", "balanced")
    p = RISK_PROFILES.get(mode, RISK_PROFILES["balanced"])
    return {
        "sl":    round(p["sl"] * strategy.get("sl_multiplier", 1.0), 4),
        "tp":    round(p["tp"] * strategy.get("tp_multiplier", 1.0), 4),
        "trail": p["trail"],
    }


GIST_ID = "4f5f6918288ddaec0a1fc998af3e6f99"

def push_status(data):
    try:
        import base64
        content_str = json.dumps(data, indent=2)
        headers = {"Authorization": f"token {GITHUB_TOKEN}",
                   "Accept": "application/vnd.github.v3+json"}
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/bot_status.json",
            headers=headers, timeout=10)
        payload = {
            "message": "bot status update",
            "content": base64.b64encode(content_str.encode()).decode()
        }
        if r.ok:
            payload["sha"] = r.json()["sha"]
        r2 = requests.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/bot_status.json",
            headers=headers, json=payload, timeout=10)
        if r2.ok:
            log("  Status pushed to GitHub")
        else:
            log(f"  [Status push] {r2.status_code}", "warning")
    except Exception as e:
        log(f"  [Push] {e}", "warning")


def binance_time():
    r = requests.get("https://api.binance.com/api/v3/time", timeout=5)
    r.raise_for_status()
    return r.json()["serverTime"]


def sign_binance(params):
    params.setdefault("recvWindow", 10000)  # 10s window for clock drift
    q = urlencode(params)
    sig = hmac.new(BINANCE_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    return q + "&signature=" + sig


def binance_headers():
    return {"X-MBX-APIKEY": BINANCE_KEY}


def get_top_crypto(n=20):
    global _top_crypto_cache
    if time.time() - _top_crypto_cache["ts"] < 3600:
        return _top_crypto_cache["coins"]
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        r.raise_for_status()
        skip = {"USDTUSDT", "BUSDUSDT", "TUSDUSDT", "USDCUSDT", "FDUSDUSDT", "USD1USDT", "RLUSDUSDT", "UUSDT", "USDPUSDT", "DAIUSDT", "FRAXUSDT", "PAXGUSDT", "DUSDT", "ZECUSDT", "NIGHTUSDT", "ESPUSDT", "NOMUSDT", "KITEUSDT", "REDUSDT", "GIGGLEUSDT", "JOEUSDT", "DASHUSDT", "0GUSDT", "ENJUSDT", "MMTUSDT", "KATUSDT", "TRUMPUSDT", "PEPEUSDT", "BARDUSDT", "ROBOUSDT", "DEGOUSDT"}
        pairs = [t for t in r.json()
                 if t["symbol"].endswith("USDT")
                 and t["symbol"] not in skip
                 and t["symbol"].isascii()
                 and float(t["quoteVolume"]) > 1000000]
        pairs.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
        coins = [t["symbol"] for t in pairs[:n]]
        _top_crypto_cache = {"coins": coins, "ts": time.time()}
        log(f"  Top {n} crypto fetched: {', '.join(coins[:6])}...")
        return coins
    except Exception as e:
        log(f"  [Top crypto] {e}", "warning")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
                "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"]


def get_crypto_closes(symbol, limit=100):
    r = requests.get("https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": "1h", "limit": limit}, timeout=10)
    r.raise_for_status()
    return [float(k[4]) for k in r.json()]



def get_crypto_closes_4h(symbol, limit=30):
    """4H closes for trend confirmation"""
    try:
        r = requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": "4h", "limit": limit}, timeout=10)
        r.raise_for_status()
        return [float(k[4]) for k in r.json()]
    except Exception:
        return []

def multi_timeframe_bonus(symbol):
    """Returns score bonus from 4H trend alignment"""
    try:
        c4h = get_crypto_closes_4h(symbol)
        if len(c4h) < 21: return 0, "No 4H"
        e9  = calc_ema(c4h, 9)
        e21 = calc_ema(c4h, 21)
        rsi = calc_rsi(c4h)
        if not e9 or not e21: return 0, "No 4H EMA"
        if e9[-1] > e21[-1] and rsi < 68:
            return 15, f"4H bullish RSI={rsi:.0f}"
        elif e9[-1] < e21[-1] and rsi > 32:
            return -15, f"4H bearish RSI={rsi:.0f}"
        return 0, "4H neutral"
    except Exception as e:
        return 0, f"4H err"


def get_crypto_price(symbol):
    r = requests.get("https://api.binance.com/api/v3/ticker/price",
        params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


def get_crypto_balance(asset):
    ts = binance_time()
    r = requests.get(
        f"https://api.binance.com/api/v3/account?{sign_binance({'timestamp': ts})}",
        headers=binance_headers(), timeout=10)
    r.raise_for_status()
    for b in r.json()["balances"]:
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0


def get_lot_info(symbol):
    """Fetch and cache LOT_SIZE stepSize and minNotional for a symbol from Binance."""
    if symbol in _lot_size_cache:
        return _lot_size_cache[symbol]
    result = {"step": 1.0, "decimals": 0, "min_notional": 5.0}
    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/exchangeInfo?symbol={symbol}", timeout=10)
        filters = r.json()["symbols"][0]["filters"]
        for f in filters:
            if f["filterType"] == "LOT_SIZE":
                step_str = f["stepSize"]
                result["step"] = float(step_str)
                trimmed = step_str.rstrip("0")
                result["decimals"] = len(trimmed.split(".")[-1]) if "." in trimmed else 0
            elif f["filterType"] in ("NOTIONAL", "MIN_NOTIONAL"):
                result["min_notional"] = float(f.get("minNotional", 5.0))
    except Exception as e:
        log(f"  [LotInfo] {symbol}: {e}", "warning")
    _lot_size_cache[symbol] = result
    return result


def place_crypto_order(symbol, side, quantity):
    import math
    lot = get_lot_info(symbol)
    step = lot["step"]
    decimals = lot["decimals"]
    min_notional = lot["min_notional"]

    price = float(requests.get(
        f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
        timeout=5).json()["price"])

    if side == "BUY":
        avail = get_crypto_balance("USDT")
        max_qty = math.floor((avail * 0.95) / price / step) * step
        max_qty = round(max_qty, decimals)
        if max_qty <= 0:
            raise Exception(f"Insufficient USDT for {symbol}: have ${avail:.2f}")
        quantity = min(quantity, max_qty)

    quantity = math.floor(quantity / step) * step
    quantity = round(quantity, decimals)
    if quantity <= 0:
        raise Exception(f"Quantity rounds to 0 for {symbol}")
    if quantity * price < min_notional:
        raise Exception(
            f"Order value ${quantity * price:.2f} < minNotional ${min_notional:.2f} for {symbol}")

    if PAPER_MODE:
        fee = round(quantity * price * 0.001, 6)
        log(f"  [PAPER] {side} {symbol}: qty={quantity} @ ~${price:,.4f}"
            f" | value=${quantity * price:.2f} | fee≈${fee:.4f}")
        _paper_fills.append({
            "time": datetime.now().isoformat(),
            "symbol": symbol, "side": side,
            "quantity": quantity, "price": price,
            "value": round(quantity * price, 4), "fee": fee,
        })
        return {
            "orderId": f"PAPER-{int(time.time() * 1000)}",
            "symbol": symbol, "side": side,
            "type": "MARKET", "status": "FILLED",
            "executedQty": str(quantity),
            "origQty": str(quantity),
            "cummulativeQuoteQty": str(round(quantity * price, 8)),
            "price": "0.00000000",
        }

    ts = binance_time()
    params = {"symbol": symbol, "side": side, "type": "MARKET",
              "quantity": quantity, "timestamp": ts}
    r = requests.post(
        f"https://api.binance.com/api/v3/order?{sign_binance(params)}",
        headers=binance_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def get_binance_lot_size(symbol):
    """Delegates to cached get_lot_info; returns decimal precision."""
    return get_lot_info(symbol)["decimals"]


def get_min_notional(symbol):
    """Delegates to cached get_lot_info; returns minNotional in USDT."""
    return get_lot_info(symbol)["min_notional"]


def crypto_precision(symbol):
    """Legacy: use get_lot_info() for live precision. Kept for external callers."""
    return get_lot_info(symbol)["decimals"]


def alpaca_headers():
    return {"APCA-API-KEY-ID": ALPACA_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET,
            "Content-Type": "application/json"}


def get_top_stocks(n=30):
    global _top_stock_cache
    if time.time() - _top_stock_cache["ts"] < 3600:
        return _top_stock_cache["stocks"]
    try:
        r = requests.get(
            "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives",
            headers=alpaca_headers(),
            params={"by": "volume", "top": n}, timeout=10)
        if r.ok:
            stocks = [s["symbol"] for s in r.json().get("most_actives", [])]
            if stocks:
                _top_stock_cache = {"stocks": stocks, "ts": time.time()}
                log(f"  Top {n} stocks fetched: {', '.join(stocks[:6])}...")
                return stocks
    except Exception as e:
        log(f"  [Top stocks] {e}", "warning")
    return ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL", "AMZN",
            "META", "JPM", "XOM", "GLD", "SPY", "QQQ",
            "AMD", "NFLX", "V", "MA", "UNH", "BAC"][:n]


def get_stock_closes(symbol, limit=100):
    r = requests.get(
        f"https://data.alpaca.markets/v2/stocks/{symbol}/bars",
        headers=alpaca_headers(),
        params={"timeframe": "1Hour", "limit": limit, "adjustment": "raw"}, timeout=10)
    r.raise_for_status()
    return [float(b["c"]) for b in r.json().get("bars", [])]


def get_alpaca_cash():
    r = requests.get(f"{ALPACA_BASE}/v2/account",
        headers=alpaca_headers(), timeout=10)
    r.raise_for_status()
    return float(r.json()["cash"])


def get_stock_position(symbol):
    try:
        r = requests.get(f"{ALPACA_BASE}/v2/positions/{symbol}",
            headers=alpaca_headers(), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def place_stock_order(symbol, side, notional):
    if PAPER_MODE:
        fee = round(notional * 0.001, 4)
        log(f"  [PAPER] {side.upper()} {symbol}: notional=${notional:.2f} | fee≈${fee:.4f}")
        _paper_fills.append({
            "time": datetime.now().isoformat(),
            "symbol": symbol, "side": side.upper(),
            "notional": notional, "fee": fee, "market": "stock",
        })
        return {
            "id": f"PAPER-{int(time.time() * 1000)}",
            "symbol": symbol, "side": side,
            "type": "market", "status": "filled",
            "notional": str(round(notional, 2)),
        }
    body = {"symbol": symbol, "side": side, "type": "market",
            "time_in_force": "day", "notional": str(round(notional, 2))}
    r = requests.post(f"{ALPACA_BASE}/v2/orders",
        headers=alpaca_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def close_stock_position(symbol):
    r = requests.delete(f"{ALPACA_BASE}/v2/positions/{symbol}",
        headers=alpaca_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def market_open():
    try:
        r = requests.get(f"{ALPACA_BASE}/v2/clock",
            headers=alpaca_headers(), timeout=10)
        return r.json().get("is_open", False)
    except Exception:
        return False


def get_hfm_price(symbol):
    try:
        forex_map = {
            "EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY",
            "USDGHS": "GHS", "AUDUSD": "AUD", "USDCAD": "CAD",
            "USDCHF": "CHF", "NZDUSD": "NZD",
        }
        if symbol in forex_map:
            curr = forex_map[symbol]
            r = requests.get(
                f"https://api.frankfurter.app/latest?from=USD&to={curr}",
                timeout=8)
            if r.ok:
                rate = r.json()["rates"].get(curr, 1)
                return rate if curr in ["JPY", "GHS", "CAD", "CHF"] else 1 / rate
        cross_map = {
            "EURGBP": ("EUR", "GBP"),
            "EURJPY": ("EUR", "JPY"),
            "GBPJPY": ("GBP", "JPY"),
        }
        if symbol in cross_map:
            b, q = cross_map[symbol]
            r = requests.get(
                f"https://api.frankfurter.app/latest?from={b}&to={q}",
                timeout=8)
            if r.ok:
                return r.json()["rates"].get(q, 1)
    except Exception as e:
        log(f"  [HFM price] {symbol}: {e}", "warning")
    fallback = {
        "XAUUSD": 3000, "XAGUSD": 32, "XPTUSD": 950,
        "EURUSD": 0.92, "GBPUSD": 0.79, "USDJPY": 150,
        "USDGHS": 15.3, "AUDUSD": 1.55, "USDCAD": 0.72,
        "USDCHF": 0.88, "NZDUSD": 1.67, "EURGBP": 0.86,
        "EURJPY": 161, "GBPJPY": 187,
        "USOIL": 82, "UKOIL": 85, "NATGAS": 2.8,
        "COPPER": 4.2, "SP500": 5200, "US30": 39000, "NAS100": 18000,
    }
    return fallback.get(symbol, 0)


def get_hfm_closes(symbol, periods=100):
    import random
    price = get_hfm_price(symbol)
    if not price:
        return []
    vol = {
        "XAUUSD": 0.008, "XAGUSD": 0.015, "USOIL": 0.012,
        "EURUSD": 0.003, "GBPUSD": 0.004, "USDJPY": 0.004,
        "USDGHS": 0.005, "NATGAS": 0.025,
        "SP500": 0.007, "US30": 0.006, "NAS100": 0.009,
    }.get(symbol, 0.01)
    random.seed(int(price * 100) % 99991)
    closes = [price]
    for _ in range(periods - 1):
        closes.insert(0, closes[0] * (1 + random.gauss(0, vol)))
    return closes


def place_hfm_signal(symbol, side, amount):
    if PAPER_MODE:
        fee = round(amount * 0.001, 4)
        log(f"  [PAPER HFM] {side} {symbol} ~${amount:.0f} | fee≈${fee:.4f}")
        _paper_fills.append({
            "time": datetime.now().isoformat(),
            "symbol": symbol, "side": side,
            "notional": amount, "fee": fee, "market": "hfm",
        })
    log(f"  [HFM SIGNAL] {side} {symbol} ~${amount:.0f}")
    telegram(
        f"<b>FOREX/METAL SIGNAL</b>\n"
        f"{side} {symbol} (~${amount:.0f})\n"
        f"Open HFM or Exness app to execute\n"
        f"HFM: {HFM_ACCOUNT} | Exness: {EXNESS_LOGIN}"
    )



def ai_news_sentiment(symbol, fg_value):
    """Ask AI for news sentiment, upcoming events and market outlook for a coin"""
    try:
        coin = symbol.replace("USDT","")
        prompt = f"""You are a crypto trading analyst. Give a trading signal for {coin} right now.
Fear & Greed Index: {fg_value}/100
Task: Search your knowledge for:
1. Any recent news about {coin} in the last 7 days
2. Upcoming events (halvings, upgrades, token unlocks, listings)
3. Overall market sentiment for {coin}
4. Macro factors (Fed rates, inflation, crypto regulation)

Respond ONLY in this exact JSON format:
{{"score": 0, "signal": "BUY/SELL/HOLD", "reason": "one line summary", "event": "upcoming event or none", "confidence": 50}}

score: -30 to +30 (positive=bullish, negative=bearish)
confidence: 0-100"""

        result = call_multi_ai(prompt, "Return valid JSON only. No markdown.")
        if not result:
            return 0, "No AI response"
        import json as _json
        data = _json.loads(result)
        score = int(data.get("score", 0))
        reason = data.get("reason", "")
        event = data.get("event", "")
        msg = reason
        if event and event.lower() != "none":
            msg += f" | Event: {event}"
        return max(-30, min(30, score)), msg
    except Exception as e:
        return 0, f"AI news error: {str(e)[:40]}"




def trade_existing_assets(strategy, cfg):
    try:
        usdt_bal = get_crypto_balance("USDT")
        if usdt_bal > 10:
            return
        log(f"  [ASSET TRADE] USDT low (${usdt_bal:.2f}) - scanning existing assets...")
        ts = binance_time()
        from urllib.parse import urlencode
        q = urlencode({"timestamp": ts})
        sig = hmac.new(BINANCE_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
        r = requests.get(
            f"https://api.binance.com/api/v3/account?{q}&signature={sig}",
            headers={"X-MBX-APIKEY": BINANCE_KEY}, timeout=10)
        if not r.ok:
            return
        skip = {"USDT","BNB","BUSD","TUSD","USDC","FDUSD"}
        scored = []
        for b in r.json()["balances"]:
            asset = b["asset"]
            free = float(b["free"])
            if asset in skip or free <= 0:
                continue
            symbol = f"{asset}USDT"
            try:
                price = get_crypto_price(symbol)
                value = free * price
                if value < 5.5:
                    continue
                closes = get_crypto_closes(symbol, 50)
                if len(closes) < 20:
                    continue
                score, _ = technical_score(closes)
                fg = get_fear_greed()
                fg_score = 15 if fg["value"] < 30 else (-15 if fg["value"] > 70 else 0)
                final_score = score + fg_score
                scored.append({"asset": asset, "symbol": symbol, "qty": free, "price": price, "value": value, "score": final_score})
                log(f"  [ASSET TRADE] {symbol} Score:{final_score} Value:${value:.2f}")
            except:
                continue
        if not scored:
            log("  [ASSET TRADE] No tradeable assets found")
            return
        log(f"  [ASSET TRADE] Found {len(scored)} tradeable assets")
        scored.sort(key=lambda x: x["score"], reverse=True)
        best = scored[0]
        worst = scored[-1]
        if best["symbol"] != worst["symbol"] and best["score"] > 40 and worst["score"] < 25:
            log(f"  [ASSET TRADE] ROTATION: Sell {worst['symbol']} ({worst['score']}) -> Buy {best['symbol']} ({best['score']})")
            prec = crypto_precision(worst["symbol"])
            sell_qty = round(worst["qty"] * 0.95, get_binance_lot_size(worst["symbol"]))
            if sell_qty * worst["price"] >= 2:
                try:
                    order = place_crypto_order(worst["symbol"], "SELL", sell_qty)
                    proceeds = float(order.get("cummulativeQuoteQty", 0))
                    log(f"  [ASSET TRADE] SOLD {worst['asset']} -> ${proceeds:.2f} USDT")
                    open_trades.pop(worst["symbol"], None)
                    time.sleep(1)
                    if proceeds >= 2:
                        buy_amount = round(proceeds * 0.95, 2)
                        buy_qty = round(buy_amount / best["price"], crypto_precision(best["symbol"]))
                        if crypto_precision(best["symbol"]) == 0:
                            buy_qty = int(buy_qty)
                        if buy_qty * best["price"] >= 2:
                            buy_order = place_crypto_order(best["symbol"], "BUY", buy_qty)
                            fill_price = float(buy_order.get("cummulativeQuoteQty", buy_amount)) / buy_qty if buy_qty else best["price"]
                            register_trade(best["symbol"], fill_price, cfg, "crypto", size_usd=buy_amount)
                            log(f"  [ASSET TRADE] BOUGHT {buy_qty} {best['asset']} @ ${best['price']:.4f}")
                            telegram(f"<b>ASSET ROTATION</b>\nSOLD {worst['asset']} (score:{worst['score']})\nBOUGHT {best['asset']} (score:{best['score']})\nAmount: ${proceeds:.2f}")
                            return
                except Exception as e:
                    log(f"  [ASSET TRADE] Rotation error: {e}", "warning")
        for t in scored:
            sym = t["symbol"]
            try:
                entry_price = open_trades.get(sym, {}).get("entry", t["price"])
                profit_pct = (t["price"] - entry_price) / entry_price * 100 if entry_price else 0
                should_sell = False
                sell_reason = ""
                if t["score"] < -15:
                    should_sell = True
                    sell_reason = f"Bearish score {t['score']}"
                elif profit_pct > 3:
                    should_sell = True
                    sell_reason = f"Taking profit +{profit_pct:.1f}%"
                elif profit_pct < -5:
                    should_sell = True
                    sell_reason = f"Stop loss -{abs(profit_pct):.1f}%"
                if should_sell:
                    prec = get_binance_lot_size(sym)
                    qty = round(t["qty"] * 0.95, prec)
                    if qty * t["price"] >= 2:
                        order = place_crypto_order(sym, "SELL", qty)
                        proceeds = float(order.get("cummulativeQuoteQty", 0))
                        log(f"  [ASSET TRADE] SOLD {qty} {t['asset']} -> ${proceeds:.2f} USDT | {sell_reason}")
                        open_trades.pop(sym, None)
                        telegram(f"<b>ASSET SELL</b>\nSOLD {t['asset']} -> ${proceeds:.2f} USDT\nReason: {sell_reason}")
            except Exception as e:
                log(f"  [ASSET TRADE] Error {sym}: {e}", "warning")
    except Exception as e:
        log(f"  [ASSET TRADE] Main error: {e}", "warning")


def check_market_conditions():
    """
    Check if market conditions are favourable for trading.
    Returns (bool, str) - (is_favourable, reason)
    
    FAVOURABLE CONDITIONS:
    1. BTC not falling more than 2% in last hour
    2. BTC above its 4-hour moving average
    3. Fear & Greed between 15-75 (not extreme greed)
    4. Market not in freefall (BTC 4h trend not deeply negative)
    """
    try:
        # Get BTC hourly closes for trend analysis
        r = requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":"1h","limit":24}, timeout=10)
        r.raise_for_status()
        btc_closes = [float(k[4]) for k in r.json()]
        
        if len(btc_closes) < 10:
            return True, "Insufficient BTC data - allowing trade"
        
        current_btc = btc_closes[-1]
        btc_1h_ago  = btc_closes[-2]
        btc_4h_ago  = btc_closes[-4] if len(btc_closes) >= 4 else btc_closes[0]
        btc_24h_ago = btc_closes[0]
        
        # Calculate changes
        change_1h  = (current_btc - btc_1h_ago)  / btc_1h_ago  * 100
        change_4h  = (current_btc - btc_4h_ago)  / btc_4h_ago  * 100
        change_24h = (current_btc - btc_24h_ago) / btc_24h_ago * 100
        
        # BTC 4H moving average
        ma4h = sum(btc_closes[-4:]) / 4
        
        # Fear & Greed
        fg = get_fear_greed()
        fg_val = fg.get("value", 50)
        
        log(f"  [MARKET] BTC 1h:{change_1h:+.1f}% 4h:{change_4h:+.1f}% 24h:{change_24h:+.1f}% F&G:{fg_val}")
        
        # BLOCK CONDITIONS - do not trade if any of these are true
        
        # 1. BTC dropping more than 2.5% in last hour = freefall
        if change_1h < -2.5:
            return False, f"BTC FREEFALL: -{abs(change_1h):.1f}% in 1h - waiting for stabilisation"
        
        # 2. BTC dropping more than 5% in 4 hours = strong downtrend
        if change_4h < -5.0:
            return False, f"BTC DOWNTREND: -{abs(change_4h):.1f}% in 4h - market too bearish"
        
        # 3. BTC dropping more than 8% in 24h = bear market day
        if change_24h < -8.0:
            return False, f"BTC BEAR DAY: -{abs(change_24h):.1f}% in 24h - sitting out"
        
        # 4. Extreme greed - market overheated, likely to reverse
        if fg_val > 78:
            return False, f"EXTREME GREED F&G:{fg_val} - market overheated, no new buys"
        
        # 5. BTC below its 4h moving average AND trending down
        if current_btc < ma4h and change_4h < -2:
            return False, f"BTC below 4H MA and falling - unfavourable"
        
        # FAVOURABLE CONDITIONS
        
        # Best condition: Fear + BTC stable or rising
        if fg_val < 30 and change_1h > -1.0:
            log(f"  [MARKET] FAVOURABLE: Fear market + stable BTC - good buying opportunity")
            return True, f"Fear market F&G:{fg_val} + BTC stable"
        
        # Good condition: BTC rising
        if change_1h > 0.5 and change_4h > 0:
            log(f"  [MARKET] FAVOURABLE: BTC trending up")
            return True, f"BTC uptrend 1h:{change_1h:+.1f}%"
        
        # Neutral: market not in crisis
        if change_1h > -1.5 and change_4h > -3:
            log(f"  [MARKET] NEUTRAL: Conditions acceptable for trading")
            return True, f"Market neutral - conditions acceptable"
        
        return False, f"Market conditions unfavourable - waiting"
        
    except Exception as e:
        log(f"  [MARKET CHECK] Error: {e} - allowing trade", "warning")
        return True, "Market check failed - defaulting to allow"

def check_usdt_safety(min_usdt=10.0):
    """Ensure we have enough USDT before trading"""
    try:
        bal = get_crypto_balance("USDT")
        if bal < min_usdt:
            return False, f"USDT too low: ${bal:.2f} < ${min_usdt:.2f}"
        return True, f"USDT OK: ${bal:.2f}"
    except Exception as e:
        return True, f"Balance check error: {e}"



def classify_signal_tier(score, reasons, symbol):
    """
    Crucix-inspired signal tiering:
    FLASH    = Act immediately - strongest signals only
    PRIORITY = Good signal - normal execution  
    ROUTINE  = Weak signal - skip to preserve capital
    """
    # Count quality reasons
    strong_reasons = [r for r in reasons if any(x in r for x in [
        "deep oversold", "MACD bullish crossover", "golden cross",
        "BB squeeze", "Bullish RSI divergence", "Strong momentum",
        "Strong volume", "Strong uptrend", "4H bullish"
    ])]
    
    # FLASH: score >= 45 + at least 2 strong reasons
    if score >= 45 and len(strong_reasons) >= 2:
        return "FLASH", f"🔴 FLASH signal - {len(strong_reasons)} strong confluences"
    
    # FLASH: extreme oversold + MACD crossover (rare combo)
    if score >= 40 and "MACD bullish crossover" in str(reasons) and "deep oversold" in str(reasons):
        return "FLASH", "🔴 FLASH - Oversold + MACD crossover"
    
    # PRIORITY: score >= 30 + at least 1 strong reason
    if score >= 30 and len(strong_reasons) >= 1:
        return "PRIORITY", f"🟡 PRIORITY signal - score:{score}"
    
    # PRIORITY: score >= 35 even without strong reasons
    if score >= 35:
        return "PRIORITY", f"🟡 PRIORITY signal - score:{score}"
    
    # ROUTINE: everything else - skip
    return "ROUTINE", f"🔵 ROUTINE - score too low ({score}), skipping"

def get_trading_window():
    """
    Only trade during high-probability market hours.
    Best windows: London open, NY open, London/NY overlap
    All times UTC.
    """
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    
    # London open: 07:00-09:00 UTC
    if 7 <= hour <= 9:
        return True, "London open window"
    # NY open: 13:00-16:00 UTC  
    if 13 <= hour <= 16:
        return True, "NY open window"
    # London/NY overlap: 13:00-17:00 UTC (best window)
    if 13 <= hour <= 17:
        return True, "London/NY overlap - best window"
    # Asian session: 00:00-04:00 UTC
    if 0 <= hour <= 4:
        return True, "Asian session window"
    # Always allow if we have open positions to monitor
    return True, "Off-peak hours - monitoring only"


def calc_ema(closes, period):
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(closes[:period]) / period]
    for c in closes[period:]:
        result.append(c * k + result[-1] * (1 - k))
    return result


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    g = l = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    ag, al = g / period, l / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + (d if d > 0 else 0)) / period
        al = (al * (period - 1) + (-d if d < 0 else 0)) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


def calc_macd(closes):
    if len(closes) < 35:
        return {"histogram": 0, "crossover": False, "crossunder": False}
    ef = calc_ema(closes, 12)
    es = calc_ema(closes, 26)
    if not ef or not es:
        return {"histogram": 0, "crossover": False, "crossunder": False}
    off = len(ef) - len(es)
    ml = [ef[i + off] - es[i] for i in range(len(es))]
    sl = calc_ema(ml, 9)
    if not sl:
        return {"histogram": 0, "crossover": False, "crossunder": False}
    hist = [ml[i + len(ml) - len(sl)] - sl[i] for i in range(len(sl))]
    return {
        "histogram": hist[-1] if hist else 0,
        "crossover":  len(hist) >= 2 and hist[-2] < 0 and hist[-1] > 0,
        "crossunder": len(hist) >= 2 and hist[-2] > 0 and hist[-1] < 0,
    }


def calc_bb(closes, period=20):
    if len(closes) < period:
        return {"pct_b": 0.5, "squeeze": False}
    sl = closes[-period:]
    mid = sum(sl) / period
    std = (sum((x - mid) ** 2 for x in sl) / period) ** 0.5
    if std == 0:
        return {"pct_b": 0.5, "squeeze": False}
    pct_b = (closes[-1] - (mid - 2 * std)) / (4 * std)
    return {"pct_b": round(pct_b, 3), "squeeze": (4 * std) / mid < 0.04}


def technical_score(closes):
    if len(closes) < 35:
        return 0, ["Insufficient data"]
    rsi  = calc_rsi(closes)
    macd = calc_macd(closes)
    bb   = calc_bb(closes)
    ema9  = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    score, reasons = 0, []
    if rsi < 28:
        score += 35; reasons.append(f"RSI {rsi} deep oversold")
    elif rsi < 35:
        score += 20; reasons.append(f"RSI {rsi} oversold")
    elif rsi > 72:
        score -= 35; reasons.append(f"RSI {rsi} deep overbought")
    elif rsi > 65:
        score -= 20; reasons.append(f"RSI {rsi} overbought")
    if macd["crossover"]:
        score += 30; reasons.append("MACD bullish crossover")
    elif macd["crossunder"]:
        score -= 30; reasons.append("MACD bearish crossunder")
    elif macd["histogram"] > 0:
        score += 10; reasons.append("MACD positive")
    else:
        score -= 10; reasons.append("MACD negative")
    if bb["pct_b"] < 0.05:
        score += 25; reasons.append("Price at lower BB")
    elif bb["pct_b"] > 0.95:
        score -= 25; reasons.append("Price at upper BB")
    if bb["squeeze"]:
        reasons.append("BB squeeze - breakout incoming")
    if ema9 and ema21 and len(ema9) >= 2 and len(ema21) >= 2:
        e9, e21   = ema9[-1], ema21[-1]
        e50       = ema50[-1] if ema50 else e21
        pe9, pe21 = ema9[-2], ema21[-2]
        if pe9 <= pe21 and e9 > e21:
            score += 20; reasons.append("EMA golden cross")
        elif pe9 >= pe21 and e9 < e21:
            score -= 20; reasons.append("EMA death cross")
        elif e9 > e21 and e9 > e50:
            score += 10; reasons.append("Bullish EMA 9>21>50")
        elif e9 < e21:
            score -= 10; reasons.append("Bearish EMA")
    r30 = closes[-30:]
    rng = max(r30) - min(r30)
    if rng > 0:
        pos = (closes[-1] - min(r30)) / rng
        if pos < 0.2:
            score += 15; reasons.append(f"Range bottom {pos*100:.0f}%")
        elif pos > 0.8:
            score -= 15; reasons.append(f"Range top {pos*100:.0f}%")
    # Momentum bonus - reward coins moving strongly
    if len(closes) >= 5:
        momentum = (closes[-1] - closes[-5]) / closes[-5] * 100
        if momentum > 3:   score += 15; reasons.append(f"Strong momentum +{momentum:.1f}%")
        elif momentum > 1: score += 8;  reasons.append(f"Positive momentum +{momentum:.1f}%")
        elif momentum < -3: score -= 15; reasons.append(f"Falling momentum {momentum:.1f}%")


    # Volume confirmation via price movement proxy
    if len(closes) >= 20:
        moves = [abs(closes[i]-closes[i-1]) for i in range(-20,-1)]
        avg_move = sum(moves)/len(moves)
        last_move = abs(closes[-1]-closes[-2])
        vol_ratio = last_move/avg_move if avg_move > 0 else 1
        if vol_ratio > 2.0:   score += 12; reasons.append(f"Strong volume {vol_ratio:.1f}x")
        elif vol_ratio > 1.5: score += 6;  reasons.append(f"Above avg volume {vol_ratio:.1f}x")
        elif vol_ratio < 0.5: score -= 5;  reasons.append(f"Weak volume {vol_ratio:.1f}x")

    # ATR volatility filter - skip choppy low-vol markets
    if len(closes) >= 15:
        atr = sum(abs(closes[i]-closes[i-1]) for i in range(-14,-1))/13
        atr_pct = atr/closes[-1]*100
        if atr_pct < 0.25:   score -= 15; reasons.append(f"Choppy market ATR={atr_pct:.2f}%")
        elif atr_pct > 0.6:  score += 8;  reasons.append(f"Trending market ATR={atr_pct:.2f}%")

    # RSI divergence detection
    if len(closes) >= 20:
        rsi_now  = calc_rsi(closes[-20:])
        rsi_prev = calc_rsi(closes[-25:-5])
        if closes[-1] < closes[-5] and rsi_now > rsi_prev and rsi_now < 48:
            score += 20; reasons.append(f"Bullish RSI divergence {rsi_prev:.0f}->{rsi_now:.0f}")
        if closes[-1] > closes[-5] and rsi_now < rsi_prev and rsi_now > 52:
            score -= 20; reasons.append(f"Bearish RSI divergence {rsi_prev:.0f}->{rsi_now:.0f}")

    # Trend consistency - consecutive green/red candles
    if len(closes) >= 7:
        greens = sum(1 for i in range(-5,0) if closes[i] > closes[i-1])
        if greens >= 4:   score += 12; reasons.append(f"Strong uptrend {greens}/5 green")
        elif greens <= 1: score -= 12; reasons.append(f"Strong downtrend {5-greens}/5 red")


    # VWAP Signal (from polyrec/txbabaxyz)
    vwap, vwap_dev = calc_vwap(closes, 20)
    if vwap_dev < -3:
        score += 15; reasons.append(f"Price {abs(vwap_dev):.1f}% below VWAP - undervalued")
    elif vwap_dev < -1:
        score += 7; reasons.append(f"Price below VWAP -{abs(vwap_dev):.1f}%")
    elif vwap_dev > 3:
        score -= 15; reasons.append(f"Price {vwap_dev:.1f}% above VWAP - overvalued")
    elif vwap_dev > 1:
        score -= 7; reasons.append(f"Price above VWAP +{vwap_dev:.1f}%")

    # Fade Impulse Signal (from polyrec fade_impulse strategy)
    if len(closes) >= 5:
        impulse = (closes[-1] - closes[-3]) / closes[-3] * 100
        prev_impulse = (closes[-3] - closes[-5]) / closes[-5] * 100
        if impulse > 5 and prev_impulse < 1:
            score -= 10; reasons.append(f"Impulse spike {impulse:.1f}% - fade signal")
        elif impulse < -5 and prev_impulse > -1:
            score += 10; reasons.append(f"Impulse drop {impulse:.1f}% - reversal likely")

    # ADX Trend Strength Filter (awesome-ai-in-finance)
    adx = calc_adx(closes)
    if adx > 30:
        score += 12; reasons.append(f"Strong trend ADX={adx:.0f}")
    elif adx < 18:
        score -= 10; reasons.append(f"Weak trend ADX={adx:.0f} - avoid")

    # Sharpe Ratio quality filter
    sharpe = calc_sharpe_ratio(closes[-30:] if len(closes)>=30 else closes)
    if sharpe > 1.0:
        score += 10; reasons.append(f"Good Sharpe ratio {sharpe:.1f}")
    elif sharpe < -1.0:
        score -= 10; reasons.append(f"Poor Sharpe {sharpe:.1f}")

    # Mean Reversion Signal (awesome-ai-in-finance)
    mr_score, mr_reason = calc_mean_reversion_score(closes)
    if mr_score != 0:
        score += mr_score; reasons.append(f"MeanRev: {mr_reason}")


    # Universal Geopolitical Intelligence (Kobeissi principles)
    geo_score, geo_reason = get_geopolitical_score()
    if geo_score != 0:
        score += geo_score
        reasons.append(f"GEO: {geo_reason}")

    # Trump Analysis Module (disable when he leaves: TRUMP_ANALYSIS_ENABLED=False)
    trump_score, trump_reason = get_trump_analysis_score()
    if trump_score != 0:
        score += trump_score
        reasons.append(f"TRUMP: {trump_reason}")

    # Weekend blackout check
    blackout, blackout_reason = is_weekend_blackout()
    if blackout:
        score -= 50
        reasons.append(f"BLACKOUT: {blackout_reason}")

    # Cross-domain correlation boost (Crucix-inspired)
    # When 3+ independent indicators agree = confidence multiplier
    bullish_signals = sum([
        1 if rsi < 35 else 0,
        1 if macd.get("crossover") or macd.get("histogram", 0) > 0 else 0,
        1 if bb.get("pct_b", 0.5) < 0.2 else 0,
        1 if ema9 and ema21 and ema9[-1] > ema21[-1] else 0,
    ])
    if bullish_signals >= 3:
        score += 15
        reasons.append(f"Cross-domain confluence: {bullish_signals}/4 bullish indicators agree")
    
    bearish_signals = sum([
        1 if rsi > 65 else 0,
        1 if macd.get("crossunder") or macd.get("histogram", 0) < 0 else 0,
        1 if bb.get("pct_b", 0.5) > 0.8 else 0,
        1 if ema9 and ema21 and ema9[-1] < ema21[-1] else 0,
    ])
    if bearish_signals >= 3:
        score -= 15
        reasons.append(f"Cross-domain confluence: {bearish_signals}/4 bearish indicators agree")

    return max(-100, min(100, score)), reasons



def calc_adx(closes, period=14):
    """
    Average Directional Index - measures trend strength
    ADX > 25 = strong trend (good to trade)
    ADX < 20 = weak/no trend (avoid)
    From: awesome-ai-in-finance ADX strategy
    """
    if len(closes) < period * 2:
        return 20.0  # neutral default
    try:
        highs  = [closes[i] * 1.005 for i in range(len(closes))]  # estimate
        lows   = [closes[i] * 0.995 for i in range(len(closes))]
        tr_list = []
        dm_plus = []
        dm_minus = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i-1]),
                     abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
            up   = highs[i] - highs[i-1]
            down = lows[i-1] - lows[i]
            dm_plus.append(up if up > down and up > 0 else 0)
            dm_minus.append(down if down > up and down > 0 else 0)
        def smooth(lst, p):
            s = sum(lst[:p])
            result = [s]
            for v in lst[p:]:
                s = s - s/p + v
                result.append(s)
            return result
        atr_s  = smooth(tr_list, period)
        dmp_s  = smooth(dm_plus, period)
        dmm_s  = smooth(dm_minus, period)
        di_plus  = [100 * dmp_s[i] / atr_s[i] if atr_s[i] else 0 for i in range(len(atr_s))]
        di_minus = [100 * dmm_s[i] / atr_s[i] if atr_s[i] else 0 for i in range(len(atr_s))]
        dx = [100 * abs(di_plus[i] - di_minus[i]) / (di_plus[i] + di_minus[i])
              if (di_plus[i] + di_minus[i]) > 0 else 0 for i in range(len(di_plus))]
        if len(dx) < period:
            return 20.0
        adx = sum(dx[-period:]) / period
        return round(adx, 2)
    except:
        return 20.0

def calc_sharpe_ratio(closes, risk_free=0.02):
    """
    Sharpe Ratio - risk adjusted return score
    Higher = better risk/reward
    From: awesome-ai-in-finance portfolio optimization
    """
    if len(closes) < 10:
        return 0.0
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    if not returns:
        return 0.0
    avg_ret = sum(returns) / len(returns)
    variance = sum((r - avg_ret)**2 for r in returns) / len(returns)
    std_dev = variance ** 0.5
    if std_dev == 0:
        return 0.0
    daily_rf = risk_free / 365
    sharpe = (avg_ret - daily_rf) / std_dev
    return round(sharpe * (252**0.5), 2)  # annualized

def calc_mean_reversion_score(closes):
    """
    Mean reversion signal - price far from mean = likely to return
    From: awesome-ai-in-finance mean reversion strategies
    Returns: positive = oversold (buy), negative = overbought (sell)
    """
    if len(closes) < 20:
        return 0, "Insufficient data"
    mean_20 = sum(closes[-20:]) / 20
    current = closes[-1]
    deviation = (current - mean_20) / mean_20 * 100
    if deviation < -8:
        return 20, f"Strong mean reversion opportunity -{abs(deviation):.1f}% below avg"
    elif deviation < -4:
        return 10, f"Mean reversion signal -{abs(deviation):.1f}% below avg"
    elif deviation > 8:
        return -20, f"Overbought {deviation:.1f}% above avg - mean reversion risk"
    elif deviation > 4:
        return -10, f"Extended {deviation:.1f}% above avg"
    return 0, "Price near mean"

def kelly_position_size(win_rate, avg_win, avg_loss, balance):
    """
    Kelly Criterion - optimal position sizing
    From: awesome-ai-in-finance Kelly Criterion sizing
    Returns optimal trade size in USDT
    """
    if avg_loss == 0:
        return balance * 0.1
    b = avg_win / avg_loss  # win/loss ratio
    p = win_rate            # win probability
    q = 1 - p               # loss probability
    kelly = (b * p - q) / b
    kelly = max(0.05, min(kelly, 0.35))  # cap between 5% and 35%
    return round(balance * kelly, 2)



def calc_vwap(closes, period=20):
    """
    Volume Weighted Average Price (from polyrec/txbabaxyz)
    Price below VWAP = undervalued = BUY signal
    Price above VWAP = overvalued = SELL signal
    Uses estimated volume from price momentum as proxy
    """
    if len(closes) < period:
        return closes[-1], 0
    try:
        prices = closes[-period:]
        # Estimate volume proxy from price changes
        volumes = [abs(prices[i] - prices[i-1]) / prices[i-1] * 1000000
                   for i in range(1, len(prices))]
        volumes.insert(0, volumes[0] if volumes else 1)
        # VWAP = sum(price * volume) / sum(volume)
        total_vol = sum(volumes)
        if total_vol == 0:
            return closes[-1], 0
        vwap = sum(p * v for p, v in zip(prices, volumes)) / total_vol
        deviation = (closes[-1] - vwap) / vwap * 100
        return round(vwap, 6), round(deviation, 2)
    except:
        return closes[-1], 0

def get_crypto_closes_with_volume(symbol, limit=50):
    """Get OHLCV data for better VWAP calculation (from polyrec)"""
    try:
        r = requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": "1h", "limit": limit}, timeout=10)
        r.raise_for_status()
        klines = r.json()
        closes  = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        highs   = [float(k[2]) for k in klines]
        lows    = [float(k[3]) for k in klines]
        return closes, volumes, highs, lows
    except Exception:
        return [], [], [], []

def calc_vwap_real(closes, volumes, period=20):
    """Real VWAP using actual volume data"""
    if len(closes) < period or len(volumes) < period:
        return closes[-1] if closes else 0, 0
    try:
        p = closes[-period:]
        v = volumes[-period:]
        total_v = sum(v)
        if total_v == 0:
            return p[-1], 0
        vwap = sum(px * vx for px, vx in zip(p, v)) / total_v
        deviation = (p[-1] - vwap) / vwap * 100
        return round(vwap, 6), round(deviation, 2)
    except:
        return closes[-1], 0




def get_trump_analysis_score():
    """
    TRUMP ANALYSIS MODULE (Kobeissi Letter verified)
    Disable when Trump leaves: TRUMP_ANALYSIS_ENABLED = False
    
    Verified accurate across:
    - China tariffs (May 2025)
    - Venezuela/Maduro capture (Dec 2025)
    - Greenland/EU deal (Jan 2026)
    - India trade deal (Feb 2026)
    - Iran war/ceasefire (Feb-Mar 2026)
    
    10-Step Playbook:
    1. Verbal pressure - "make a deal"
    2. Strategic posturing
    3. Friday night strike (after markets close)
    4. Risk premium expansion
    5. "Forever war/tariff" language
    6. Markets price prolonged conflict = NEW LOWS
    7. Conditional de-escalation signals
    8. Market/political feedback loop = SMART MONEY BUYS
    9. The Deal announced = violent rally
    10. Victory lap = take profits
    """
    if not TRUMP_ANALYSIS_ENABLED:
        return 0, "Trump analysis disabled"

    try:
        fg = get_fear_greed()
        fg_val = fg.get("value", 50)

        # Get weekly BTC change as market proxy
        r = requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":"1d","limit":7}, timeout=10)
        closes = [float(k[4]) for k in r.json()]
        weekly_chg = (closes[-1] - closes[0]) / closes[0] * 100

        # STEP 8: Smart money accumulation (BEST BUY)
        # Triggered by: oil near $90, stocks -5%+, F&G extreme fear
        # This is when Trump's pressure is MAXIMUM before deal
        if fg_val < 15 and weekly_chg < -10:
            return +20, "TRUMP STEP 8: Max pressure before deal - Smart money BUY zone"

        # IRAN Apr 2026: fragile ceasefire, Hormuz still contested
        if fg_val < 35 and weekly_chg < -5:
            return +15, 'IRAN STEP 7: Fragile ceasefire - accumulate'
        # STEP 7: Conditional de-escalation starting
        # Trump language softens, deal coming soon
        if fg_val < 20 and weekly_chg < -5:
            return +15, "TRUMP STEP 7: De-escalation signals - Begin accumulating"

        # STEP 6: Markets pricing prolonged conflict
        # Second or third dip - structural repositioning
        if fg_val < 30 and weekly_chg < -3:
            return +8, "TRUMP STEP 6: Prolonged conflict priced in - Watch entries"

        # STEP 4-5: Escalation phase - stay cautious
        # "Forever war/tariff" language = more pain coming
        if fg_val < 40 and weekly_chg < -8:
            return -12, "TRUMP STEP 4-5: Escalation active - Reduce exposure"

        # STEP 10: Victory lap - violent repricing done
        # Time to take profits before reversal
        if fg_val > 70 and weekly_chg > 8:
            return -15, "TRUMP STEP 10: Victory rally - Take profits"

        # STEP 9: Deal just announced
        # Sharp rally incoming - buy any dips
        if fg_val > 55 and weekly_chg > 5:
            return +10, "TRUMP STEP 9: Deal announced - Ride the rally"

        return 0, "Trump playbook: No clear step detected"

    except Exception as e:
        return 0, f"Trump analysis error: {e}"

# TO DISABLE TRUMP ANALYSIS WHEN HE LEAVES PRESIDENCY:
# Simply change line above to: TRUMP_ANALYSIS_ENABLED = False
# One line change removes all Trump-specific logic permanently


def get_geopolitical_score():
    """
    Universal Geopolitical Market Intelligence
    Based on Kobeissi Letter research - timeless principles
    Works regardless of president, conflict or country
    Core truth: Extreme fear + oversold market = best buy opportunity
    """
    try:
        fg = get_fear_greed()
        fg_val = fg.get("value", 50)

        r = requests.get("https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":"1d","limit":7}, timeout=10)
        closes = [float(k[4]) for k in r.json()]
        weekly_change = (closes[-1] - closes[0]) / closes[0] * 100

        # BEST BUY ZONE: Extreme fear + market crashed
        if fg_val < 15 and weekly_change < -10:
            return +25, "EXTREME FEAR + CRASH: Historical best buy zone"
        if fg_val < 25 and weekly_change < -5:
            return +20, "High fear + pullback: Smart money accumulation"
        if fg_val < 30 and weekly_change < -3:
            return +12, "Fear market: Good entry conditions"

        # DANGER ZONE: Greed + overbought
        if fg_val > 75 and weekly_change > 10:
            return -20, "EXTREME GREED + RALLY: Take profits soon"
        if fg_val > 60 and weekly_change > 5:
            return -10, "Greed building: Reduce exposure"

        return 0, "Neutral market conditions"

    except Exception as e:
        return 0, f"Geo check error: {e}"

def is_weekend_blackout():
    """
    Crypto trades 24/7 - no blackout for crypto.
    Stocks still respect Friday PM / weekend hours.
    """
    return False, "Crypto trades 24/7"


def get_fear_greed():
    global _fg_cache
    if time.time() - _fg_cache["ts"] < 3600:
        return _fg_cache
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=2", timeout=8)
        items   = r.json()["data"]
        current = int(items[0]["value"])
        prev    = int(items[1]["value"]) if len(items) > 1 else current
        _fg_cache = {
            "value": current,
            "label": items[0]["value_classification"],
            "trend": "improving" if current > prev else "declining",
            "ts": time.time(),
        }
    except Exception as e:
        log(f"  [F&G] {e}", "warning")
    return _fg_cache


def fetch_news(query):
    global _news_cache
    key = query[:12]
    c = _news_cache.get(key, {"items": [], "ts": 0})
    if time.time() - c["ts"] < 900:
        return c["items"]
    items = []
    if any(x in query.upper() for x in ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"]):
        try:
            sym = query.upper().replace("USDT", "")
            r = requests.get(
                f"https://cryptopanic.com/api/free/v1/posts/"
                f"?auth_token=free&currencies={sym}&public=true&filter=hot",
                timeout=10, headers={"User-Agent": "AccraBot/8.0"})
            if r.ok:
                for p in r.json().get("results", [])[:5]:
                    if p.get("title"):
                        items.append({
                            "title": p["title"],
                            "bull":  p.get("votes", {}).get("positive", 0),
                            "bear":  p.get("votes", {}).get("negative", 0),
                        })
        except Exception as e:
            log(f"  [News] {e}", "warning")
    _news_cache[key] = {"items": items, "ts": time.time()}
    return items


def deep_analysis(symbol, asset_type, strategy):
    global _fund_cache
    c = _fund_cache.get(symbol, {"result": None, "ts": 0})
    if time.time() - c["ts"] < 21600 and c["result"]:
        return c["result"]
    fg = get_fear_greed()
    fg_val = fg.get("value", 50)
    if fg_val <= 25:   score = 35;  signal = "BULLISH"
    elif fg_val <= 35: score = 15;  signal = "BULLISH"
    elif fg_val >= 75: score = -35; signal = "BEARISH"
    elif fg_val >= 65: score = -15; signal = "BEARISH"
    else:              score = 0;   signal = "NEUTRAL"
    result = {"score": score, "signal": signal, "top_risk": "Market risk",
              "top_opp": "Follow signals", "ghana": f"F&G:{fg_val}", "reason": f"F&G:{fg_val}"}
    _fund_cache[symbol] = {"result": result, "ts": time.time()}
    return result


def unified_signal(symbol, closes, asset_type, strategy):
    tech, reasons = technical_score(closes)
    # Only call AI if technical score is strong - saves Groq tokens
    if abs(tech) >= 20:
        fund = deep_analysis(symbol.replace("USDT", ""), asset_type, strategy)
    else:
        fund = {"score": 0, "signal": "NEUTRAL", "top_risk": "Weak signal",
                "top_opp": "Wait", "ghana": "No action needed", "reason": "Technical score too weak for AI analysis"}
    combined = max(-100, min(100, round(tech * 0.55 + fund["score"] * 0.45)))
    min_conf  = strategy.get("min_confidence", 35)
    signal = "HOLD"
    if combined >= min_conf:
        signal = "BUY"
    elif combined <= -min_conf:
        signal = "SELL"
    all_reasons = reasons[:3] + [
        f"Fundamental: {fund['signal']} ({fund['score']:+d})",
        f"Risk: {fund['top_risk']}",
        f"Ghana: {fund['ghana'][:50]}",
    ]
    return {
        "signal":      signal,
        "confidence":  abs(combined),
        "combined":    combined,
        "tech":        tech,
        "fund":        fund["score"],
        "rsi":         calc_rsi(closes),
        "reasons":     all_reasons[:6],
        "fund_reason": fund["reason"],
        "top_risk":    fund["top_risk"],
        "top_opp":     fund["top_opp"],
        "ghana":       fund["ghana"],
    }



def load_history():
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except:
        return []

def load_insights():
    try:
        with open(INSIGHTS_FILE) as f:
            return json.load(f)
    except:
        return None

def run_dream_cycle():
    """Analyze trade history and return actionable directives."""
    from datetime import timezone, timedelta
    h = load_history()
    if len(h) < 5:
        log("  [DREAM] Need 5+ trades to analyze (have %d)" % len(h))
        return None

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent   = [t for t in h if t.get("timestamp","") > cutoff] or h[-20:]
    settled  = [t for t in recent if t.get("outcome") in ("WIN","LOSS")]
    if not settled:
        log("  [DREAM] No settled trades yet")
        return None

    wins     = [t for t in settled if t["outcome"] == "WIN"]
    win_rate = len(wins) / len(settled)

    asset_pnl = {}
    for t in recent:
        a = t.get("asset", t.get("symbol", "?"))
        asset_pnl.setdefault(a, []).append(t.get("profit_pct", 0))
    asset_avg = {a: sum(v)/len(v) for a, v in asset_pnl.items() if v}

    worst = min(asset_avg, key=asset_avg.get) if asset_avg else None
    best  = max(asset_avg, key=asset_avg.get) if asset_avg else None

    streak = 0
    for t in reversed(settled):
        if t["outcome"] == "LOSS": streak += 1
        else: break

    directives = {
        "avoid_asset":           worst if asset_avg.get(worst, 0) < -2 else None,
        "prefer_asset":          best  if asset_avg.get(best,  0) >  1 else None,
        "go_defensive":          streak >= 3,
        "recommended_min_score": 25 if win_rate < 0.4 else 20 if win_rate < 0.5 else 15,
    }

    insights = {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "win_rate_pct":        round(win_rate * 100, 1),
        "win_rate":            round(win_rate, 3),
        "wins":                len(wins),
        "losses":              len(settled) - len(wins),
        "current_losing_streak": streak,
        "best_asset":          best,
        "worst_asset":         worst,
        "asset_avg_pnl":       {k: round(v, 2) for k, v in asset_avg.items()},
        "directives":          directives,
    }

    try:
        with open(INSIGHTS_FILE, "w") as f:
            json.dump(insights, f, indent=2)
    except Exception as e:
        log(f"  [DREAM] Insights save failed: {e}", "warning")

    log("  [DREAM] win_rate=%.0f%% streak=%d avoid=%s best=%s" % (
        win_rate*100, streak, directives["avoid_asset"], best))

    if streak >= 3:
        telegram("<b>DREAM ALERT</b>\n%d consecutive losses\nGoing defensive\nAvoiding: %s" % (
            streak, directives["avoid_asset"]))

    return insights

def save_open_trades():
    """
    Persist open_trades to disk so a Railway restart doesn't silently drop
    SL/TP tracking on a position that's still actually held. Called once
    per cycle from the main loop rather than on every individual mutation --
    cheap, and the worst case on a mid-cycle crash is losing a few seconds
    of state, not the whole position.
    """
    try:
        with open(OPEN_TRADES_FILE, "w") as f:
            json.dump(open_trades, f)
    except Exception as e:
        log(f"  [OPEN_TRADES] Save failed: {e}", "warning")


def load_open_trades():
    """Restore open_trades from disk on startup, if a prior run left any."""
    global open_trades
    try:
        with open(OPEN_TRADES_FILE) as f:
            restored = json.load(f)
        open_trades.update(restored)
        if restored:
            log(f"  [OPEN_TRADES] Restored {len(restored)} position(s) from disk: "
                f"{', '.join(restored.keys())}")
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"  [OPEN_TRADES] Load failed: {e}", "warning")


def register_trade(symbol, price, cfg, market, size_usd=0.0):
    open_trades[symbol] = {
        "entry":      price,
        "sl":         round(price * (1 - cfg["sl"]), 8),
        "tp":         round(price * (1 + cfg["tp"]), 8),
        "trail_high": price,
        "trail_sl":   round(price * (1 - cfg["trail"]), 8),
        "market":     market,
        "time":       datetime.now().isoformat(),
        "size_usd":   size_usd,
    }
    log(f"  Registered: {symbol} @ {price:.4f} "
        f"SL:{open_trades[symbol]['sl']:.4f} TP:{open_trades[symbol]['tp']:.4f}")


def check_trades(prices, trail=0.03):
    to_close = []
    for sym, t in list(open_trades.items()):
        p = prices.get(sym)
        if not p:
            # Symbol dropped out of this cycle's scan — fetch current price directly
            if t.get("market") == "crypto":
                try:
                    r = requests.get(
                        f"https://api.binance.com/api/v3/ticker/price?symbol={sym}",
                        timeout=5)
                    p = float(r.json()["price"])
                except Exception as _e:
                    log(f"  [CHECK_TRADES] {sym}: direct price fetch failed ({_e})"
                        f" — cannot evaluate SL/TP this cycle", "warning")
                    continue
            else:
                log(f"  [CHECK_TRADES] {sym} ({t.get('market','?')}): not in prices"
                    f" — cannot evaluate SL/TP this cycle", "warning")
                continue
        if p > t["trail_high"]:
            t["trail_high"] = p
            t["trail_sl"]   = p * (1 - trail)
        reason = None
        if p <= t["sl"]:
            reason = f"Stop-loss {p:.4f}"
        elif t.get("partial_tp_done"):
            # Already took partial profit off this one — the remainder rides on
            # the breakeven/trailing stop only. Don't let a stale TP level
            # (set before the partial exit) force a full close on every cycle
            # the price happens to still be above it.
            if p <= t.get("trail_sl", 0):
                reason = f"Trailing SL {p:.4f}"
        elif p >= t["tp"]:
            reason = f"Take-profit {p:.4f}"
        elif p <= t.get("trail_sl", 0):
            reason = f"Trailing SL {p:.4f}"
        if reason:
            to_close.append((sym, reason, p, t["market"], t["entry"]))
    return to_close


def try_partial_take_profit(sym, t, price, fraction, trail=0.03):
    """
    On a first take-profit touch for a crypto position, sell `fraction` of the
    held quantity and let the rest ride with the stop moved to breakeven.
    Returns True if the partial exit executed (caller should NOT also run a
    full close this cycle). Returns False if partial exit isn't safe/possible
    (already done, not crypto, or the split would leave a leg below Binance's
    minNotional) — caller should fall back to a full close.
    """
    import math
    if t.get("market") != "crypto" or t.get("partial_tp_done"):
        return False
    coin = sym.replace("USDT", "")
    try:
        bal = get_crypto_balance(coin)
    except Exception as e:
        log(f"  [PARTIAL_TP] {sym}: balance fetch failed ({e}) — full exit instead", "warning")
        return False
    lot = get_lot_info(sym)
    step, decimals, min_notional = lot["step"], lot["decimals"], lot["min_notional"]
    sell_qty   = math.floor((bal * fraction) / step) * step
    sell_qty   = round(sell_qty, decimals)
    remain_qty = round(bal - sell_qty, decimals)
    sell_value   = sell_qty * price
    remain_value = remain_qty * price
    if sell_qty <= 0 or sell_value < min_notional or remain_value < min_notional:
        log(f"  [PARTIAL_TP] {sym}: split would strand dust "
            f"(sell=${sell_value:.2f} remain=${remain_value:.2f} min=${min_notional:.2f})"
            f" — full exit instead")
        return False
    try:
        order = place_crypto_order(sym, "SELL", sell_qty)
    except Exception as e:
        log(f"  [PARTIAL_TP] {sym}: sell order failed ({e}) — full exit instead", "warning")
        return False
    actual_qty = float(order.get("executedQty", sell_qty))
    proceeds   = float(order.get("cummulativeQuoteQty", actual_qty * price))
    pnl_pct    = round((price - t["entry"]) / t["entry"] * 100, 2)
    pnl_usd    = round(proceeds - (t["entry"] * actual_qty), 4)
    log(f"  [PARTIAL_TP] {sym}: sold {actual_qty} ({fraction*100:.0f}%) @ ${price:,.4f}"
        f" | proceeds=${proceeds:.2f} | PnL:{pnl_pct:+.2f}%"
        f" | remainder SL->breakeven, still exposed to upside")
    telegram(
        f"<b>PARTIAL TAKE-PROFIT</b>\n{sym}\n"
        f"Sold {fraction*100:.0f}% @ {price:.4f} | PnL:{pnl_pct:+.2f}%\n"
        f"Remainder stop moved to breakeven"
    )
    log_trade({
        "time": datetime.now().isoformat(), "symbol": sym,
        "action": "PARTIAL_TP", "entry": t["entry"], "exit": price,
        "pnl": pnl_pct, "pnl_usd": pnl_usd, "market": t["market"],
    })
    global _daily_realized_pnl_usd
    _daily_realized_pnl_usd += pnl_usd
    _save_daily_loss_state()
    t["size_usd"]       = round(remain_value, 4)
    t["sl"]             = t["entry"]                       # breakeven
    t["partial_tp_done"] = True
    t["trail_high"]     = max(t.get("trail_high", price), price)
    t["trail_sl"]       = t["trail_high"] * (1 - trail)
    return True


def telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "HTML"},
            timeout=8,
        )
    except Exception as e:
        log(f"  [Telegram] {e}", "warning")


def log_trade(entry):
    trade_log.append(entry)
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(trade_log[-500:], f, indent=2)
    except Exception as e:
        log(f"  [Log] {e}", "warning")


def execute(symbol, signal, price, cfg, conf, market, tier="PRIORITY"):
    # Check dream directives
    _ins = load_insights()
    if _ins:
        _dir = _ins.get("directives", {})
        if _dir.get("avoid_asset") and _dir["avoid_asset"] in symbol:
            log("  [DREAM] Blocking %s - poor performer" % symbol)
            return False
        if _dir.get("go_defensive") and conf < 50:
            log("  [DREAM] Defensive mode - skipping low conf signal (%d%%)" % conf)
            return False
    try:
        if market == "crypto":
            coin = symbol.replace("USDT", "")
            _lot = get_lot_info(symbol)
            prec = _lot["decimals"]
            if signal == "BUY":
                if conf < 25:
                    log(f"  SKIP {symbol}: conf {conf}% < 25% minimum")
                    return False
                # RE-ENTRY FILTER: Don't re-buy within 3% of last SL price (Lo & Remorov)
                sl_memory = _reentry_block.get(symbol)
                if sl_memory:
                    blocked_until_price = sl_memory["sl_price"] * 1.03
                    if price < blocked_until_price:
                        log(f"  SKIP {symbol}: re-entry blocked until ${blocked_until_price:.4f} (currently ${price:.4f})")
                        return False
                    else:
                        _reentry_block.pop(symbol, None)
                bal    = get_crypto_balance("USDT")
                # QUANT ENGINE: Kelly+Bayes+EV sizing
                from quant_engine import trade_decision_with_kronos as _qd
                _sl = cfg.get("sl", 0.025)
                _tp = cfg.get("tp", 0.07)
                _tp_ratio = _tp / _sl  # e.g. 7%/2.5% = 2.8x
                _decision = _qd(
                    signal_confidence=conf,
                    signal_direction="BUY",
                    free_usdt=bal,
                    fear_greed=_fg_cache.get("value", 50),
                    market_condition=cfg.get("market_condition", "neutral"),
                    current_balance=bal,
                    starting_balance=get_or_init_starting_balance(bal),
                    consecutive_losses=0,
                    sl_multiplier=1.0,
                    tp_multiplier=_tp_ratio,
                    min_confidence=25
                )
                if not _decision["trade"]:
                    log(f"  SKIP {symbol}: Quant blocked — {_decision['reason']}")
                    return False
                amount = _decision["position_size"]
                log(f"  [QUANT] adj={_decision['adjusted_confidence']:.1f}% EV={_decision.get('ev',0):.3f}% size=${amount}")
                if amount < 2:
                    log(f"  SKIP {symbol}: ${amount:.2f} < $2")
                    return False
                min_notional = _lot["min_notional"]
                if amount < min_notional:
                    if tier in ("FLASH", "PRIORITY"):
                        import math as _math
                        step = _lot["step"]
                        qty  = _math.ceil(min_notional / price / step) * step
                        qty  = round(qty, prec)
                        bumped_cost = round(qty * price, 4)
                        if bumped_cost > bal * 0.95:
                            log(f"  SKIP {symbol}: {tier} but can't afford min qty"
                                f" ${bumped_cost:.2f} (avail ${bal*0.95:.2f})")
                            return False
                        log(f"  [FLOOR] {symbol}: ceiled qty={qty}"
                            f" (${bumped_cost:.2f} >= minNotional ${min_notional:.2f}) [{tier}]")
                        amount = bumped_cost
                        if prec == 0:
                            qty = int(qty)
                    else:
                        log(f"  SKIP {symbol}: buy amount ${amount:.2f} < min notional"
                            f" ${min_notional:.2f} [{tier}]")
                        return False
                else:
                    qty = round(amount / price, prec)
                    if prec == 0:
                        qty = int(qty)
                order = place_crypto_order(symbol, "BUY", qty)
                actual_qty = float(order.get("executedQty", qty))
                # cummulativeQuoteQty = real USDT spent (live Binance or paper sim)
                actual_size_usd = round(
                    float(order.get("cummulativeQuoteQty", actual_qty * price)), 4)
                log(f"  BOUGHT {actual_qty} {coin} @ ${price:,.4f}"
                    f" | filled=${actual_size_usd:.2f} | ID:{order.get('orderId')}")
                register_trade(symbol, price, cfg, "crypto", size_usd=actual_size_usd)
                telegram(
                    f"<b>CRYPTO BUY</b>\n{symbol} @ ${price:,.4f}\n"
                    f"Qty:{actual_qty} | ${actual_size_usd:.2f}\nConf:{conf}% | "
                    f"SL:${price*(1-cfg['sl']):.4f} TP:${price*(1+cfg['tp']):.4f}"
                )
                return True
            elif signal == "SELL":
                bal = get_crypto_balance(coin)
                qty = round(bal * 0.95, prec)
                qty = int(qty) if prec == 0 else qty
                if qty < 0.00001:
                    log(f"  SKIP {symbol}: no balance")
                    return False
                min_notional = _lot["min_notional"]
                if qty * price < min_notional:
                    log(f"  [DUST] {symbol}: notional ${qty*price:.4f} < min ${min_notional:.2f}"
                        f" — writing off, freeing position slot")
                    open_trades.pop(symbol, None)
                    return False  # False = not a real sale; caller checks open_trades to detect dust
                order = place_crypto_order(symbol, "SELL", qty)
                log(f"  SOLD {qty} {coin} @ ${price:,.4f} | ID:{order.get('orderId')}")
                open_trades.pop(symbol, None)
                log(f"  [PROFIT->USDT] Proceeds in USDT - P&L trackable")
                telegram(f"<b>CRYPTO SELL</b>\n{symbol} @ ${price:,.4f}\nQty:{qty}")
                return True

        elif market == "stock":
            if signal == "BUY":
                if get_stock_position(symbol):
                    log(f"  SKIP {symbol}: already held")
                    return False
                cash   = get_alpaca_cash()
                amount = round(cash * (cfg.get("pct", 5) / 100), 2)
                if amount < 1:
                    log(f"  SKIP {symbol}: ${amount:.2f} < $1")
                    return False
                order = place_stock_order(symbol, "buy", amount)
                mode  = "PAPER" if (PAPER_MODE or "paper" in ALPACA_BASE) else "LIVE"
                log(f"  BOUGHT ${amount:.2f} {symbol} [{mode}]")
                register_trade(symbol, price, cfg, "stock", size_usd=amount)
                telegram(
                    f"<b>STOCK BUY [{mode}]</b>\n{symbol} @ ${price:.2f}\n"
                    f"${amount:.2f} | Conf:{conf}% | "
                    f"SL:${price*(1-cfg['sl']):.2f} TP:${price*(1+cfg['tp']):.2f}"
                )
                return True
            elif signal == "SELL":
                if not get_stock_position(symbol):
                    log(f"  SKIP {symbol}: no position")
                    return False
                close_stock_position(symbol)
                log(f"  SOLD {symbol}")
                open_trades.pop(symbol, None)
                telegram(f"<b>STOCK SELL</b>\n{symbol} @ ${price:.2f}")
                return True

        elif market == "hfm":
            amount = 100 * (cfg.get("pct", 3) / 3)
            place_hfm_signal(symbol, signal, amount)
            if signal == "BUY":
                register_trade(symbol, price, cfg, "hfm", size_usd=amount)
            else:
                open_trades.pop(symbol, None)
            return True

    except Exception as e:
        log(f"  [Execute] {symbol}: {e}", "error")
        telegram(f"<b>EXECUTE ERROR</b>\n{symbol}: {e}")
    return False


def get_ai_autonomous_strategy(current_strategy):
    """AI analyzes market and recommends optimal strategy for maximum profit."""
    global ai_consecutive_failures, failsafe_active, failsafe_reason, ai_mode_enabled
    
    if not ai_mode_enabled:
        log("  [AI Strategy] AI mode disabled by user")
        return current_strategy
    
    fg = get_fear_greed()
    ghs = 15.0
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=GHS", timeout=5)
        if r.ok: ghs = r.json().get("rates", {}).get("GHS", 15.0)
    except Exception: pass
    
    # Build market context
    btc_price = 0
    btc_change = 0
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5)
        if r.ok:
            d = r.json()
            btc_price = float(d.get("lastPrice", 0))
            btc_change = float(d.get("priceChangePercent", 0))
    except Exception: pass
    
    gold_price = get_hfm_price("XAUUSD")
    
    prompt = (
        f"You are an autonomous trading AI managing a portfolio for a Ghanaian investor.\n"
        f"OBJECTIVE: Maximize profit across crypto, stocks, forex, metals, commodities.\n\n"
        f"MARKET DATA:\n"
        f"- Fear&Greed: {fg['value']}/100 ({fg['label']}, {fg.get('trend','stable')})\n"
        f"- BTC: ${btc_price:,.0f} ({btc_change:+.1f}% 24h)\n"
        f"- Gold: ${gold_price:,.0f}\n"
        f"- USD/GHS: {ghs:.2f} ({'WEAK GHS - protect with USD assets' if ghs > 15 else 'stable'})\n"
        f"- Open trades: {len(open_trades)}\n"
        f"- Current mode: {current_strategy.get('mode','balanced')}\n\n"
        f"AVAILABLE MARKETS: Crypto (Binance), US Stocks (Alpaca paper), Forex/Metals/Oil (HFM/Exness)\n\n"
        f"PROFIT MAXIMIZATION RULES:\n"
        f"1. In extreme fear (F&G<20): BUY aggressively - highest returns\n"
        f"2. In extreme greed (F&G>80): SELL and take profits\n"
        f"3. Weak GHS: Buy USD-denominated assets (BTC, Gold, US stocks)\n"
        f"4. Rising BTC: Increase crypto allocation\n"
        f"5. Volatile markets: Use Gold and USD as safe haven\n"
        f"6. Always protect capital first, then maximize gains\n\n"
        f"Recommend optimal strategy. Reply ONLY valid JSON:\n"
        f'{{"mode":"conservative|balanced|aggressive","market_condition":"bear|neutral|bull",'
        f'"min_confidence":25-60,"top_n_crypto":5-30,"top_n_stocks":0-30,'
        f'"crypto_enabled":true/false,"stocks_enabled":true/false,"hfm_enabled":true/false,'
        f'"prefer_assets":["list of best assets right now"],'
        f'"avoid_assets":["list of risky assets to avoid"],'
        f'"sl_multiplier":0.5-1.5,"tp_multiplier":0.5-2.0,'
        f'"reason":"2 sentences max profit strategy",'
        f'"ghana_advice":"specific advice for Ghanaian investor"}}'
    )
    
    if not GROQ_KEY:
        log("  [AI Strategy] No Groq key - using failsafe", "warning")
        return activate_failsafe("No AI key configured")
    
    try:
        raw = call_multi_ai(prompt, "Autonomous trading AI. Return valid JSON only. Focus on maximum profit.", max_tokens=1024)
        if not raw:
            raise Exception("All AI providers failed")
        # Strip markdown fences, then extract outermost JSON object
        raw = re.sub(r"```json|```", "", raw).strip()
        _s, _e = raw.find('{'), raw.rfind('}')
        if _s == -1 or _e <= _s:
            log(f"  [AI Strategy] No JSON object in response. len={len(raw)}"
                f" head={raw[:80]!r} tail={raw[-80:]!r}", "warning")
            raise Exception(f"No JSON object found (len={len(raw)})")
        raw = raw[_s:_e + 1]
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as _je:
            log(f"  [AI Strategy] JSON parse error: {_je}."
                f" len={len(raw)} head={raw[:80]!r} tail={raw[-80:]!r}", "warning")
            raise
        
        # Merge with defaults
        new_strategy = {**current_strategy, **parsed,
                        "updated_by": "ai_autonomous",
                        "last_updated": datetime.now().isoformat()}
        
        # Reset failure counter on success
        ai_consecutive_failures = 0
        if failsafe_active:
            failsafe_active = False
            log("  [AI Strategy] AI recovered - resuming normal trading")
            telegram("<b>AI TRADING RESUMED</b>\nAI connection restored\nResuming profit-maximizing strategy")
        
        reason = parsed.get("reason", "")
        ghana = parsed.get("ghana_advice", "")
        log(f"  [AI Strategy] Mode:{new_strategy['mode']} Market:{new_strategy['market_condition']} Conf:{new_strategy.get('min_confidence',35)}")
        log(f"  [AI Strategy] {reason}")
        log(f"  [AI Strategy] Ghana: {ghana}")
        
        telegram(
            f"<b>AI STRATEGY UPDATE</b>\n"
            f"Mode: {new_strategy['mode'].upper()}\n"
            f"Market: {new_strategy['market_condition'].upper()}\n"
            f"Confidence threshold: {new_strategy.get('min_confidence',35)}%\n"
            f"Prefer: {', '.join(parsed.get('prefer_assets',[])[:4])}\n"
            f"Reason: {reason[:100]}\n"
            f"Ghana: {ghana[:80]}"
        )
        
        # Push to Gist so terminal can see it
        try:
            gist_payload = {"files": {"bot_strategy.json": {"content": json.dumps(new_strategy, indent=2)}}}
            requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GITHUB_TOKEN}",
                         "Accept": "application/vnd.github.v3+json"},
                json=gist_payload, timeout=10)
        except Exception: pass
        
        return new_strategy
        
    except Exception as e:
        ai_consecutive_failures += 1
        log(f"  [AI Strategy] FAILED ({ai_consecutive_failures}/{MAX_AI_FAILURES}): {e}", "warning")
        
        if ai_consecutive_failures >= MAX_AI_FAILURES:
            return activate_failsafe(f"AI failed {ai_consecutive_failures} times: {str(e)[:50]}")
        
        return current_strategy


def activate_failsafe(reason):
    """Activate failsafe mode to protect capital."""
    global failsafe_active, failsafe_reason
    if not failsafe_active:
        failsafe_active = True
        failsafe_reason = reason
        log(f"  [FAILSAFE ACTIVATED] {reason}", "error")
        telegram(
            f"<b>FAILSAFE MODE ACTIVATED</b>\n"
            f"Reason: {reason}\n"
            f"Actions taken:\n"
            f"- Confidence threshold raised to 60%\n"
            f"- Only BTC and Gold allowed\n"
            f"- Stocks disabled\n"
            f"- Stop losses tightened 30%\n"
            f"- Max 2 open trades\n"
            f"Capital protection is priority!"
        )
    return FAILSAFE_STRATEGY.copy()


def get_or_init_starting_balance(current_balance):
    """
    Returns the account's true starting balance, persisted once on first use
    so position-sizing math (Kelly skew) always compares against the real
    baseline instead of a number hand-typed months ago that goes stale as
    the account grows or shrinks.
    """
    try:
        with open(STARTING_BALANCE_FILE) as f:
            state = json.load(f)
        return float(state.get("starting_balance", current_balance))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        try:
            with open(STARTING_BALANCE_FILE, "w") as f:
                json.dump({
                    "starting_balance": current_balance,
                    "set_at": datetime.now(timezone.utc).isoformat(),
                }, f)
            log(f"  [DIAG] starting_balance_state.json initialized at ${current_balance:.2f}")
        except Exception as e:
            log(f"  [STARTING BALANCE] Save failed: {e}", "warning")
        return current_balance


def _save_daily_loss_state():
    """Write running P&L total and UTC calendar date to disk so a restart can resume them."""
    try:
        today = datetime.now(timezone.utc).date()
        with open(DAILY_LOSS_FILE, "w") as f:
            json.dump({
                "pnl_usd": _daily_realized_pnl_usd,
                "date": (_daily_pnl_date or today).isoformat(),
            }, f)
    except Exception as e:
        log(f"  [DAILY LOSS] Save failed: {e}", "warning")


def _load_daily_loss_state():
    """Load persisted P&L state on startup; resets if stored date != today (UTC)."""
    global _daily_realized_pnl_usd, _daily_pnl_date
    today = datetime.now(timezone.utc).date()
    try:
        with open(DAILY_LOSS_FILE) as f:
            state = json.load(f)
        stored_date_str = state.get("date") or state.get("window_start", "")[:10]
        log(f"  [DIAG] daily_loss_state.json: pnl_usd={state.get('pnl_usd')}"
            f" date={stored_date_str} today(UTC)={today.isoformat()}")
        from datetime import date as _date
        stored_date = _date.fromisoformat(stored_date_str)
        if stored_date == today:
            _daily_realized_pnl_usd = float(state.get("pnl_usd", 0.0))
            _daily_pnl_date = today
            log(f"  [DAILY LOSS] Resumed: pnl=${_daily_realized_pnl_usd:+.2f} (UTC date {today})")
        else:
            _daily_pnl_date = today
            log(f"  [DAILY LOSS] Stored date {stored_date} != today {today} — starting fresh")
    except FileNotFoundError:
        _daily_pnl_date = today
    except Exception as e:
        log(f"  [DAILY LOSS] Load failed: {e}", "warning")
        _daily_pnl_date = today


def check_daily_loss_limit():
    """Returns True and blocks new BUY entries if today's (UTC) realized loss hit MAX_DAILY_LOSS_USD."""
    global _daily_realized_pnl_usd, _daily_pnl_date, _daily_loss_blocked
    if MAX_DAILY_LOSS_USD is None:
        return False
    today = datetime.now(timezone.utc).date()
    if _daily_pnl_date != today:
        _daily_realized_pnl_usd = 0.0
        _daily_loss_blocked = False
        _daily_pnl_date = today
        log(f"  [DAILY LOSS] New UTC day ({today}) — counter reset, kill switch cleared")
        _save_daily_loss_state()
    if -_daily_realized_pnl_usd >= MAX_DAILY_LOSS_USD:
        if not _daily_loss_blocked:
            _daily_loss_blocked = True
            msg = (f"Daily loss limit ${MAX_DAILY_LOSS_USD:.2f} reached "
                   f"(realized: ${_daily_realized_pnl_usd:+.2f})")
            log(f"  [DAILY LOSS KILL SWITCH] {msg}", "error")
            telegram(
                f"<b>DAILY LOSS KILL SWITCH</b>\n"
                f"{msg}\n"
                f"New BUY entries blocked until 24h window resets.\n"
                f"Existing positions are still managed normally."
            )
        return True
    _daily_loss_blocked = False
    return False


def run_cycle():
    global cycle_count, _daily_realized_pnl_usd
    cycle_count += 1

    # ASSET TRADING - runs every cycle when USDT is low
    try:
        _usdt = get_crypto_balance("USDT")
        log(f"  [ASSET MODE] USDT check: ${_usdt:.2f}")
        if _usdt < 6:
            log(f"  [ASSET MODE] LOW USDT - activating asset trading!")
            strategy_now = load_strategy()
            trade_existing_assets(strategy_now, get_risk(strategy_now))
        else:
            log(f"  [ASSET MODE] USDT OK - normal trading mode")
    except Exception as _e:
        import traceback
        log(f"  [ASSET MODE] ERROR: {traceback.format_exc()[:200]}", "warning")
    global ai_strategy_cycle
    ts       = datetime.now().strftime("%H:%M:%S")
    strategy = load_strategy()
    try:
        log_intel_summary()
    except:pass

    # ===== ASSET TRADING WHEN USDT LOW =====
    try:
        usdt_now = get_crypto_balance("USDT")
        if usdt_now < 4:
            log(f"  [ASSET TRADE] USDT=${usdt_now:.2f} - activating asset trading mode...")
            trade_existing_assets(strategy, get_risk(strategy))
    except Exception as e:
        log(f"  [ASSET TRADE] Error: {e}", "warning")

    
    # Run AI autonomous strategy every N cycles
    ai_strategy_cycle += 1
    if ai_mode_enabled and ai_strategy_cycle >= AI_STRATEGY_INTERVAL:
        ai_strategy_cycle = 0
        log("\n  [AI AUTO-STRATEGY] Analyzing market for maximum profit...")
        strategy = get_ai_autonomous_strategy(strategy)
    elif failsafe_active:
        strategy = activate_failsafe(failsafe_reason)
    
    mode     = strategy.get("mode", "balanced")
    cfg      = get_risk(strategy)

    log(f"\n{'='*55}")
    status_tag = "FAILSAFE" if failsafe_active else ("AI-AUTO" if ai_mode_enabled else "MANUAL")
    log(f"[{ts}] ACCRA BOT v9 | {status_tag} | Mode:{mode} | Cycle:{cycle_count}")
    log(f"{'='*55}")

    all_results = {}
    prices      = {}

    # CRYPTO
    if BINANCE_KEY and strategy.get("crypto_enabled", True):
        coins  = get_top_crypto(strategy.get("top_n_crypto", 50))
        avoid  = strategy.get("avoid_assets", [])
        prefer = strategy.get("prefer_assets", [])
        coins  = [c for c in coins if c not in avoid]
        coins  = [c for c in prefer if c in coins] + [c for c in coins if c not in prefer]
        log(f"\n  [CRYPTO] Scanning {len(coins)} coins...")
        for sym in coins:
            try:
                closes = get_crypto_closes(sym)
                if len(closes) < 35:
                    continue
                price = closes[-1]
                sig   = unified_signal(sym, closes, "crypto", strategy)
                sig["price"]  = price
                sig["cfg"]    = {**cfg, "pct": 40}
                sig["market"] = "crypto"
                try:
                    _ms,_mc2,_mr=apply_multidim_intelligence(sym,sig["signal"],sig.get("combined",0),sig.get("confidence",0),sig["market"])
                    sig["combined"]=_ms;sig["confidence"]=_mc2
                    if _mr:sig["reasons"]=sig.get("reasons",[])+_mr
                except:pass
                all_results[sym] = sig
                prices[sym]      = price
                if sig["signal"] != "HOLD":
                    arrow = "BUY " if sig["signal"] == "BUY" else "SELL"
                    log(f"  {arrow} {sym:<12} ${price:>12,.2f} "
                        f"T:{sig['tech']:+d} F:{sig['fund']:+d} C:{sig['combined']:+d}")
            except Exception as e:
                log(f"  [{sym}] {e}", "warning")

    # US STOCKS
    if ALPACA_KEY and strategy.get("stocks_enabled", True) and market_open():
        stocks = get_top_stocks(strategy.get("top_n_stocks", 30))
        avoid  = strategy.get("avoid_assets", [])
        stocks = [s for s in stocks if s not in avoid]
        log(f"\n  [US STOCKS] Scanning {len(stocks)} stocks...")
        for sym in stocks:
            try:
                closes = get_stock_closes(sym)
                if len(closes) < 35:
                    continue
                price = closes[-1]
                sig   = unified_signal(sym, closes, "stock", strategy)
                sig["price"]  = price
                sig["cfg"]    = {**cfg, "pct": max(2, 35 // len(stocks))}
                sig["market"] = "stock"
                try:
                    _ms,_mc2,_mr=apply_multidim_intelligence(sym,sig["signal"],sig.get("combined",0),sig.get("confidence",0),sig["market"])
                    sig["combined"]=_ms;sig["confidence"]=_mc2
                    if _mr:sig["reasons"]=sig.get("reasons",[])+_mr
                except:pass
                all_results[sym] = sig
                prices[sym]      = price
                if sig["signal"] != "HOLD":
                    arrow = "BUY " if sig["signal"] == "BUY" else "SELL"
                    log(f"  {arrow} {sym:<8} ${price:>10,.2f} "
                        f"T:{sig['tech']:+d} F:{sig['fund']:+d} C:{sig['combined']:+d}")
            except Exception as e:
                log(f"  [{sym}] {e}", "warning")
    elif ALPACA_KEY and strategy.get("stocks_enabled", True):
        log("\n  [US STOCKS] Market closed")

    # HFM/EXNESS
    if (HFM_ACCOUNT or EXNESS_LOGIN) and strategy.get("hfm_enabled", True):
        instruments = list(HFM_INSTRUMENTS.keys())
        avoid       = strategy.get("avoid_assets", [])
        instruments = [i for i in instruments if i not in avoid]
        log(f"\n  [HFM/EXNESS] Scanning {len(instruments)} instruments...")
        for sym in instruments:
            try:
                closes = get_hfm_closes(sym)
                if len(closes) < 35:
                    continue
                price      = closes[-1]
                asset_type = HFM_INSTRUMENTS[sym].lower()
                sig        = unified_signal(sym, closes, asset_type, strategy)
                sig["price"]  = price
                sig["cfg"]    = {**cfg, "pct": max(2, 25 // len(instruments))}
                sig["market"] = "hfm"
                try:
                    _ms,_mc2,_mr=apply_multidim_intelligence(sym,sig["signal"],sig.get("combined",0),sig.get("confidence",0),sig["market"])
                    sig["combined"]=_ms;sig["confidence"]=_mc2
                    if _mr:sig["reasons"]=sig.get("reasons",[])+_mr
                except:pass
                all_results[sym] = sig
                prices[sym]      = price
                if sig["signal"] != "HOLD":
                    arrow = "BUY " if sig["signal"] == "BUY" else "SELL"
                    log(f"  {arrow} {sym:<10} {price:>10,.4f} "
                        f"T:{sig['tech']:+d} F:{sig['fund']:+d} C:{sig['combined']:+d}")
            except Exception as e:
                log(f"  [{sym}] {e}", "warning")

    # SL/TP CHECK
    to_close = check_trades(prices, trail=cfg.get("trail", 0.03))
    for sym, reason, price, market, entry in to_close:
        if reason.startswith("Take-profit"):
            t = open_trades.get(sym)
            if t and try_partial_take_profit(
                sym, t, price,
                strategy.get("partial_tp_fraction", 0.75),
                trail=cfg.get("trail", 0.03),
            ):
                continue  # remainder stays open with SL at breakeven; skip full close
        pnl      = round((price - entry) / entry * 100, 2)
        size_usd = open_trades.get(sym, {}).get("size_usd", 0.0)
        pnl_usd  = round(size_usd * pnl / 100, 4)
        sig_cfg  = all_results.get(sym, {}).get("cfg", {**cfg, "pct": 5})
        log(f"\n  AUTO-CLOSE {sym}: {reason} | PnL:{pnl:+.2f}% (≈${pnl_usd:+.2f})")
        _was_open = sym in open_trades
        sold = execute(sym, "SELL", price, sig_cfg, 0, market)
        _freed = _was_open and sym not in open_trades  # True for both real sell and dust write-off
        if not _freed:
            # execute() failed and position is still tracked — will retry next cycle
            continue
        if sold:
            # Real sale executed — update P&L and notify
            _daily_realized_pnl_usd += pnl_usd
            _save_daily_loss_state()
            telegram(
                f"<b>AUTO-CLOSE</b>\n{sym}\n{reason}\n"
                f"Entry:{entry:.4f} Exit:{price:.4f}\nPnL:{pnl:+.2f}%"
            )
            log_trade({
                "time": datetime.now().isoformat(), "symbol": sym,
                "action": "CLOSE", "reason": reason,
                "entry": entry, "exit": price, "pnl": pnl,
                "pnl_usd": pnl_usd, "market": market,
            })
        else:
            # Dust write-off — position freed but no real sale, P&L not counted
            log_trade({
                "time": datetime.now().isoformat(), "symbol": sym,
                "action": "DUST_WRITEOFF", "reason": reason,
                "entry": entry, "market": market, "pnl": 0, "pnl_usd": 0,
            })

    # RANK SIGNALS
    min_conf = strategy.get("min_confidence", 35)
    max_open = min(strategy.get("max_open_trades", 5), MAX_OPEN_POSITIONS)
    crypto_open = sum(1 for t in open_trades.values() if t.get("market") == "crypto")

    buys = []
    for s, r in all_results.items():
        if r["signal"] != "BUY": continue
        if r["confidence"] < min_conf: continue
        if s in open_trades: continue
        tier, tier_reason = classify_signal_tier(r.get("combined", 0), r.get("reasons", []), s)
        if tier == "ROUTINE":
            log(f"  SKIP {s}: {tier_reason}")
            continue
        r["tier"] = tier
        r["tier_reason"] = tier_reason
        buys.append((s, r))
    buys.sort(key=lambda x: x[1]["combined"], reverse=True)

    sells = [
        (s, r) for s, r in all_results.items()
        if r["signal"] == "SELL" and r["confidence"] >= min_conf and s in open_trades
    ]

    log(f"\n  Summary: {len(buys)} BUY | {len(sells)} SELL | {len(open_trades)} open")

    for sym, sig in sells[:3]:
        log(f"  SELL: {sym} (score:{sig['combined']:+d})")
        _trade_entry  = open_trades.get(sym, {}).get("entry", sig["price"])
        _trade_size   = open_trades.get(sym, {}).get("size_usd", 0.0)
        executed = execute(sym, "SELL", sig["price"], sig["cfg"], sig["confidence"], sig["market"])
        if executed:
            _pnl_pct = round((sig["price"] - _trade_entry) / _trade_entry * 100, 2) if _trade_entry else 0
            _pnl_usd = round(_trade_size * _pnl_pct / 100, 4)
            _daily_realized_pnl_usd += _pnl_usd
            _save_daily_loss_state()
            log_trade({
                "time": datetime.now().isoformat(), "symbol": sym,
                "action": "SELL", "price": sig["price"],
                "combined": sig["combined"], "market": sig["market"],
                "pnl_pct": _pnl_pct, "pnl_usd": _pnl_usd,
            })

    slots = max_open - crypto_open
    if check_daily_loss_limit():
        log(f"  [DAILY LOSS] Skipping {len(buys)} BUY signal(s) — kill switch active")
    elif slots <= 0:
        log(f"  [POS CAP] {crypto_open}/{max_open} crypto positions open — skipping {len(buys)} new BUY(s)")
    else:
        for sym, sig in buys[:max(1, slots)]:
            log(f"\n  BUY: {sym} | Score:{sig['combined']:+d} | {sig['market'].upper()}")
            for r in sig["reasons"][:3]:
                log(f"    - {r}")
            log(f"  AI: {sig.get('fund_reason', '')[:70]}")
            executed = execute(sym, "BUY", sig["price"], sig["cfg"], sig["confidence"], sig["market"],
                               tier=sig.get("tier", "PRIORITY"))
            if executed:
                log_trade({
                    "time":        datetime.now().isoformat(),
                    "symbol":      sym,
                    "action":      "BUY",
                    "price":       sig["price"],
                    "market":      sig["market"],
                    "confidence":  sig["confidence"],
                    "combined":    sig["combined"],
                    "tech":        sig["tech"],
                    "fund":        sig["fund"],
                    "reasons":     sig["reasons"],
                    "fund_reason": sig.get("fund_reason", ""),
                    "top_risk":    sig.get("top_risk", ""),
                    "ghana":       sig.get("ghana", ""),
                })

    # PUSH STATUS TO GITHUB
    top10 = sorted(all_results.items(), key=lambda x: abs(x[1]["combined"]), reverse=True)[:10]
    status = {
        "timestamp":        datetime.now().isoformat(),
        "cycle":            cycle_count,
        "strategy":         mode,
        "market_condition": strategy.get("market_condition", "neutral"),
        "assets_scanned":   len(all_results),
        "open_trades":      len(open_trades),
        "open_positions": [
            {"symbol": s, "entry": t["entry"], "market": t["market"],
             "sl": t["sl"], "tp": t["tp"]}
            for s, t in open_trades.items()
        ],
        "top_opportunities": [
            {"symbol": s, "signal": r["signal"], "score": r["combined"],
             "tech": r["tech"], "fund": r["fund"], "market": r["market"],
             "price": r["price"], "reason": r.get("fund_reason", "")[:80],
             "ghana": r.get("ghana", "")[:60]}
            for s, r in top10
        ],
        "buy_signals":  len(buys),
        "sell_signals": len(sells),
        "fear_greed":   get_fear_greed(),
        "markets": {
            "crypto": "active" if BINANCE_KEY else "disabled",
            "stocks": "open" if market_open() else "closed",
            "hfm":    "signal_mode" if (HFM_ACCOUNT or EXNESS_LOGIN) else "disabled",
        },
        "binance_balance": (lambda: (lambda b: {"usdt": round(b,2)})(get_crypto_balance("USDT")))(),
        "xyz": (lambda: {
            "balance":   round(xyz_get_balance(), 2),
            "free":      (lambda: __import__("tradexyz_trader").xyz_free_margin())(),
            "positions": [
                {"coin": p.get("position",{}).get("coin","").replace("xyz:",""),
                 "szi":  p.get("position",{}).get("szi",""),
                 "pnl":  p.get("position",{}).get("unrealizedPnl",""),
                 "margin": p.get("position",{}).get("marginUsed","")}
                for p in (xyz_get_positions() or [])
            ]
        })(),
        "dream": (lambda i: {
            "win_rate":   i.get("win_rate_pct", 0) if i else 0,
            "best_asset": i.get("best_asset","") if i else "",
            "avoid":      i.get("directives",{}).get("avoid_asset","") if i else "",
            "defensive":  i.get("directives",{}).get("go_defensive", False) if i else False,
            "streak":     i.get("current_losing_streak", 0) if i else 0,
        })(load_insights()),
        "intelligence": {
            "hormuz":     _hz_val if "_hz_val" in dir() else "UNKNOWN",
            "dprk":       bool(_nk_val) if "_nk_val" in dir() else False,
            "geo_score":  get_geopolitical_score()[0],
            "trump_score": get_trump_analysis_score()[0],
        },
        "performance": {
            "total_trades":  len(load_history()),
            "trade_log_size": len(trade_log),
        },
        "version": "v9",
        "uptime_cycles": cycle_count,
    }
    push_status(status)

    log_intel_summary()
    show_intel_signals(all_results)
    try:
        _pp={s:r["price"] for s,r in all_results.items() if r.get("price")}
        if _pp: run_poly_cycle(all_results,_pp)
    except Exception as _pe: print(f"  [POLY] {str(_pe)[:40]}")


def run_poly_cycle(all_results, current_prices):
    import json, os, hashlib, time as _t, requests as _rq
    from datetime import datetime as _dt
    pf="polymarket_paper.json"
    try: state=json.load(open(pf))
    except: state={"balance":10000.0,"starting_balance":10000.0,"trades":[],
                   "open_positions":{},"total_pnl":0.0,"wins":0,"losses":0}
    sports=["nhl","nba","nfl","mlb","stanley cup","world cup","fifa","super bowl"]
    try:
        _r=_rq.get("https://gamma-api.polymarket.com/markets",
            params={"limit":200,"active":"true","closed":"false"},timeout=10)
        raw=_r.json() if _r.ok else {}
        mkts=raw if isinstance(raw,list) else raw.get("markets",[])
        mkts=[m for m in mkts if not any(s in m.get("question","").lower() for s in sports)]
    except: mkts=[]
    sym_kw={"BTCUSDT":["bitcoin","btc"],"ETHUSDT":["ethereum","eth"],
            "SOLUSDT":["solana","sol"],"XAUUSD":["gold","xau"],
            "USOIL":["oil","crude","brent"]}
    if POLY_ENABLED:
        bets=0
        for sym,res in all_results.items():
            if sym not in sym_kw or res.get("signal") not in ("BUY","SELL"): continue
            if res.get("confidence",0)<45 or state["balance"]<2: continue
            kws=sym_kw[sym]
            rel=[m for m in mkts if any(k in m.get("question","").lower() for k in kws)
                 and any(d in m.get("question","").lower() for d in ["above","below","higher","lower","price","hit"])]
            if not rel: continue
            m=rel[0]; q=m.get("question","").lower()
            bet=round(min(max(state["balance"]*0.02*(res["confidence"]/100),1.0),20.0),2)
            try: yp=float(m.get("outcomePrices",["0.5"])[0])
            except: yp=0.5
            side="YES" if (res["signal"]=="BUY" and any(k in q for k in ["above","higher","rise","hit"])) else "NO"
            ep=yp if side=="YES" else 1-yp
            tid=hashlib.md5(f"{sym}{_t.time()}".encode()).hexdigest()[:8]
            trade={"id":tid,"time":_dt.now().isoformat(),"symbol":sym,
                   "question":m.get("question","")[:60],"signal":res["signal"],
                   "side":side,"amount":bet,"entry":ep,"confidence":res["confidence"],
                   "status":"OPEN","pnl":0.0,"bot_price":res.get("price",0)}
            state["balance"]-=bet
            state["open_positions"][tid]=trade
            state["trades"].append(trade)
            print(f"  [POLY BET] {side} ${bet:.1f} | {m.get('question','')[:52]}")
            bets+=1
            if bets>=2: break
    for tid,t in list(state["open_positions"].items()):
        age=(_dt.now()-_dt.fromisoformat(t["time"])).total_seconds()/3600
        if age<1: continue
        cur=current_prices.get(t["symbol"],0)
        if not cur: continue
        up=cur>t["bot_price"]
        won=(t["signal"]=="BUY" and t["side"]=="YES" and up) or             (t["signal"]=="BUY" and t["side"]=="NO" and not up) or             (t["signal"]=="SELL" and t["side"]=="NO" and up) or             (t["signal"]=="SELL" and t["side"]=="YES" and not up)
        pnl=t["amount"]*0.9 if won else -t["amount"]
        if won: state["balance"]+=t["amount"]+pnl; state["wins"]+=1
        else: state["losses"]+=1
        state["total_pnl"]+=pnl
        t.update({"pnl":pnl,"status":"WON" if won else "LOST"})
        del state["open_positions"][tid]
        print(f"  [POLY] {'WIN' if won else 'LOSS'}: {t['question'][:40]} ${pnl:+.2f}")
    try: json.dump(state,open(pf,"w"))
    except: pass
    total=state["wins"]+state["losses"]
    wr=(state["wins"]/total*100) if total else 0
    roi=((state["balance"]-10000)/10000*100)
    print(f"  [POLY PAPER] ${state['balance']:.0f} ROI:{roi:+.1f}% WR:{wr:.0f}% ({state['wins']}W/{state['losses']}L)")

def apply_multidim_intelligence(sym,signal,score,confidence,market):
    global _wx_events_cache
    import requests as _rq, time as _t
    adj=0; ac=0; reasons=[]
    is_oil=sym in("USOIL","UKOIL","NATGAS","GOIL","SEPLAT")
    is_gold=sym in("XAUUSD","XAGUSD","NEWGOLD")
    is_crypto=market=="crypto" or sym.endswith("USDT")
    is_btc=sym=="BTCUSDT"
    global _hz_val,_hz_ts,_nk_val,_nk_ts,_wx_val,_wx_ts,_cg_val,_cg_ts
    try: _hz_val
    except: _hz_val="UNKNOWN";_hz_ts=0
    try: _nk_val
    except: _nk_val=False;_nk_ts=0
    try: _wx_val
    except: _wx_val=0;_wx_ts=0
    try: _cg_val
    except: _cg_val=[];_cg_ts=0
    now=_t.time()
    if now-_hz_ts>900:
        try:
            _r=_rq.get("https://www.hormuztracker.com/",timeout=6,headers={"User-Agent":"Mozilla/5.0"})
            _txt=_r.text.lower() if _r.ok else ""
            _hz_val="CLOSED" if any(k in _txt for k in ["closed","suspended","blocked"]) else                     "DISRUPTED" if any(k in _txt for k in ["disrupted","warning","restricted"]) else "OPEN"
            _hz_ts=now
        except: _hz_val="RESTRICTED";_hz_ts=now
    if _hz_val in("CLOSED","DISRUPTED"):
        _osig=55 if _hz_val=="CLOSED" else 25
        if is_oil and signal=="BUY": adj+=_osig;ac+=15;reasons.append(f"HORMUZ {_hz_val} +{_osig}")
        elif is_gold and signal=="BUY": adj+=_osig//3;reasons.append(f"Hormuz {_hz_val} safe-haven")
        elif is_oil and signal=="SELL": adj-=_osig//2
    if now-_nk_ts>3600:
        try:
            from datetime import datetime as _dt,timedelta as _td
            _cut=(_dt.now()-_td(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
            _r2=_rq.get("https://earthquake.usgs.gov/fdsnws/event/1/query",
                params={"format":"geojson","starttime":_cut,"minmagnitude":"3.5",
                        "latitude":"41.3","longitude":"129.0","maxradiuskm":"150"},timeout=8)
            if _r2.ok:
                _sh=[f for f in _r2.json().get("features",[]) if f["properties"].get("depth",100)<20]
                _nk_val=any(f["properties"]["mag"]>=4.5 for f in _sh)
            _nk_ts=now
        except: pass
    if _nk_val:
        if is_gold and signal=="BUY": adj+=20;ac+=10;reasons.append("DPRK seismic - gold safe haven")
        elif is_btc and signal=="BUY": adj+=8;reasons.append("DPRK threat - BTC hedge")
    if now-_wx_ts>1800:
        # Global weather scan - all regions affecting markets
        _ZONES=[
            {"n":"West Africa","lat":7.9,"lon":-1.0,"assets":["MTNGH","GCB","GGBL","FML","UNIL","BOPP","GOIL"],"type":"africa"},
            {"n":"Nigeria","lat":9.0,"lon":8.0,"assets":["DANGCEM","MTNN","ZENITHB","SEPLAT","GOIL"],"type":"africa"},
            {"n":"East Africa","lat":0.0,"lon":37.0,"assets":["SAFCOM","EQTY","KCB","KENGEN"],"type":"africa"},
            {"n":"Gulf of Guinea","lat":3.0,"lon":2.0,"assets":["USOIL","UKOIL","SEPLAT","GOIL"],"type":"oil"},
            {"n":"US Gulf Coast","lat":29.5,"lon":-90.0,"assets":["USOIL","UKOIL","NATGAS"],"type":"oil"},
            {"n":"Middle East","lat":25.0,"lon":50.0,"assets":["USOIL","UKOIL","XAUUSD"],"type":"oil"},
            {"n":"Ukraine","lat":49.0,"lon":32.0,"assets":["NATGAS","UKOIL","USOIL"],"type":"energy"},
            {"n":"Australia","lat":-25.0,"lon":135.0,"assets":["NEWGOLD","BHP","GFI"],"type":"mining"},
            {"n":"South Africa","lat":-29.0,"lon":25.0,"assets":["GFI","NPN","NEWGOLD","SBK"],"type":"mining"},
            {"n":"Southeast Asia","lat":4.0,"lon":108.0,"assets":["BTCUSDT","BNBUSDT","ETHUSDT"],"type":"crypto"},
            {"n":"Japan","lat":35.7,"lon":139.7,"assets":["BTCUSDT","ETHUSDT"],"type":"crypto"},
            {"n":"Brazil","lat":-15.0,"lon":-47.0,"assets":["USOIL","UKOIL"],"type":"commodity"},
            {"n":"Indonesia","lat":-6.0,"lon":107.0,"assets":["USOIL","GGBL","FML"],"type":"commodity"},
            {"n":"India","lat":20.0,"lon":78.0,"assets":["BTCUSDT","ETHUSDT","BNBUSDT"],"type":"crypto"},
        ]
        _wx_events=[]
        _wx_max=0
        for _z in _ZONES:
            try:
                _r3=_rq.get("https://api.open-meteo.com/v1/forecast",
                    params={"latitude":_z["lat"],"longitude":_z["lon"],
                            "daily":"precipitation_sum,windspeed_10m_max,weathercode",
                            "forecast_days":"3","timezone":"auto"},timeout=5)
                if _r3.ok:
                    _dd=_r3.json().get("daily",{})
                    _pr=_dd.get("precipitation_sum",[0,0,0])
                    _wd=_dd.get("windspeed_10m_max",[0,0,0])
                    _wc=_dd.get("weathercode",[0,0,0])
                    _rain=max(_pr[:3]) if _pr else 0
                    _wind=max(_wd[:3]) if _wd else 0
                    _severe=any(c2 in [65,75,82,85,95,96,99] for c2 in (_wc[:3] if _wc else []))
                    if _rain>50 or _severe or _wind>80:
                        _wx_events.append({"zone":_z["n"],"rain":_rain,"wind":_wind,
                                           "severe":_severe,"assets":_z["assets"],"type":_z["type"]})
                        _wx_max=max(_wx_max,_rain)
            except: pass
        _wx_val=_wx_max
        _wx_ts=now
        # Store events for signal application
        _wx_events_cache=_wx_events
    # Apply global weather signals
    try:
        _wec=globals().get('_wx_events_cache',[])
    except: _wec=[]
    for _ev in _wec:
        if sym in _ev["assets"]:
            _rain=_ev.get("rain",0)
            _zn=_ev.get("zone","?")
            if _ev["type"]=="oil" and is_oil and signal=="BUY":
                adj+=min(20,int(_rain//5)+10)
                reasons.append(f"Storm {_zn} - oil supply disruption +{min(20,int(_rain//5)+10)}")
            elif _ev["type"]=="mining" and is_gold and signal=="BUY":
                adj+=10; reasons.append(f"Extreme weather {_zn} - mining disruption")
            elif _ev["type"]=="africa" and signal=="BUY":
                adj-=min(15,int(_rain//5))
                reasons.append(f"Flood {_zn} {_rain:.0f}mm - operations hit")
            elif _ev["type"]=="crypto" and is_crypto and _ev.get("severe"):
                adj+=5; reasons.append(f"Weather {_zn} - safe haven demand")
    # Global extreme weather = gold/BTC safe haven
    if _wx_val>80 and is_gold and signal=="BUY":
        adj+=12; reasons.append(f"Global extreme weather {_wx_val:.0f}mm - gold safe haven")
    elif _wx_val>80 and is_btc and signal=="BUY":
        adj+=6; reasons.append(f"Extreme weather - BTC safe haven")
    if now-_cg_ts>7200:
        _trades=[]
        for _url in ["https://senatestockwatcher.com/api/transactions",
                     "https://housestockwatcher.com/api/transactions/month"]:
            try:
                _rc=_rq.get(_url,timeout=8,headers={"User-Agent":"AccraBot/1.0"})
                if _rc.ok:
                    _raw=_rc.json()
                    _trades+=_raw if isinstance(_raw,list) else _raw.get("transactions",[])
            except: pass
        _cg_val=_trades; _cg_ts=now
    _base=sym.upper().replace("USDT","").replace("USD","")
    _st=[t for t in _cg_val if _base in t.get("ticker","").upper()
         or _base.lower() in str(t.get("asset_description",t.get("asset",""))).lower()]
    if _st:
        _cb=sum(1 for t in _st if any(k in t.get("type","").lower() for k in ["purchase","buy"]))
        _cs=sum(1 for t in _st if any(k in t.get("type","").lower() for k in ["sale","sell"]))
        if _cb>_cs and signal=="BUY": adj+=min(20,_cb*7);reasons.append(f"Congress buying {sym} ({_cb}x)")
        elif _cs>_cb and signal=="SELL": adj+=min(15,_cs*5);reasons.append(f"Congress selling {sym} ({_cs}x)")
    global _fg_val
    try: _fg=_fg_val
    except: _fg=50
    if is_crypto:
        if signal=="BUY":
            if _fg<=20: adj+=22;ac+=15;reasons.append(f"Extreme Fear {_fg} - buy zone")
            elif _fg<=35: adj+=12;ac+=8;reasons.append(f"Fear {_fg} - favorable")
            elif _fg>=85: adj-=22;ac-=15;reasons.append(f"Extreme Greed {_fg} - overbought")
            elif _fg>=70: adj-=10;reasons.append(f"Greed {_fg} - caution")
        elif signal=="SELL":
            if _fg>=80: adj+=15;reasons.append(f"Greed {_fg} confirms sell")
            elif _fg<=20: adj-=15;reasons.append(f"Fear {_fg} - hold not sell")
    fs=score+adj; fc=max(0,min(100,confidence+ac))
    if adj!=0: log(f"  [INTEL] {sym}: {score:+d}->{fs:+d} conf:{confidence}%->{fc}% | {reasons[0] if reasons else ''}")
    return fs,fc,reasons[:5]

def log_intel_summary():
    import requests as _rq
    from datetime import datetime as _dt,timedelta as _td
    print("\n"+"="*55)
    print("  ACCRA INTELLIGENCE REPORT")
    print("="*55)
    global _hz_val,_nk_val,_wx_val
    try: _hz=_hz_val
    except: _hz="UNKNOWN"
    try: _nk=_nk_val
    except: _nk=False
    try: _wx=_wx_val
    except: _wx=0
    print(f"  MARITIME: Hormuz={_hz} {'***OIL SHOCK***' if _hz=='CLOSED' else ''}")
    print(f"  SEISMIC : {'***DPRK THREAT***' if _nk else 'No DPRK activity'}")
    try:
        _wec2=globals().get('_wx_events_cache',[])
        if _wec2:
            print(f"  WEATHER : {len(_wec2)} extreme events globally")
            for _ev2 in _wec2[:3]:
                print(f"    -> {_ev2['zone']}: {_ev2.get('rain',0):.0f}mm rain {'SEVERE' if _ev2.get('severe') else ''} | Affects: {_ev2['assets'][:3]}")
        else:
            print(f"  WEATHER : Global scan complete - no extreme events")
    except: print(f"  WEATHER : Scanning global zones...")

    # Geo/Trump intelligence status
    try:
        _gs, _gr = get_geopolitical_score()
        _ts, _tr = get_trump_analysis_score()
        _blackout, _br = is_weekend_blackout()
        geo_label = ("🟢 +" if _gs > 0 else "🔴 " if _gs < 0 else "⚪ ") + str(_gs)
        trump_label = ("🟢 +" if _ts > 0 else "🔴 " if _ts < 0 else "⚪ ") + str(_ts)
        print(f"  GEO     : {geo_label} | {_gr[:50]}")
        print(f"  TRUMP   : {trump_label} | {_tr[:50]}")
        if _blackout:
            print(f"  ⛔ {_br}")
    except Exception as e:
        print(f"  GEO/TRUMP: error {e}")
    try:
        _r=_rq.get("https://gamma-api.polymarket.com/markets",
            params={"limit":200,"active":"true","closed":"false"},timeout=8)
        if _r.ok:
            _sports=["nhl","nba","nfl","mlb","stanley cup","world cup","fifa","super bowl"]
            _raw=_r.json(); _mkts=_raw if isinstance(_raw,list) else _raw.get("markets",[])
            _mkts=[m for m in _mkts if not any(s in m.get("question","").lower() for s in _sports)]
            _cats={"WAR/GEO":["war","ceasefire","ukraine","taiwan","iran","military","sanctions"],
                   "CRYPTO":["bitcoin price","btc above","btc below","ethereum price","crypto market"],
                   "OIL/GOLD":["oil price","gold price","brent","wti","opec","gold above"],
                   "AFRICA":["ghana","nigeria","naira","cedi","imf africa"],
                   "FED/MACRO":["federal reserve","fed rate","interest rate","inflation rate","recession"]}
            print("  POLYMARKET:")
            for _cat,_kws in _cats.items():
                _m=[m for m in _mkts if any(k in m.get("question","").lower() for k in _kws)]
                if _m:
                    print(f"    [{_cat}] {len(_m)} markets")
                    for _mx in _m[:2]:
                        try:
                            _yp=float(_mx.get("outcomePrices",["0.5"])[0])
                            _side="YES" if _yp>0.5 else "NO "
                            print(f"      {_side}:{_yp:.0%} | {_mx.get('question','')[:55]}")
                        except: print(f"      {_mx.get('question','')[:55]}")
    except Exception as _e: print(f"  POLY: {str(_e)[:40]}")
    print("="*55)

def show_intel_signals(all_results):
    _all=[(s,r) for s,r in all_results.items() if r.get("signal") in ("BUY","SELL")]
    _all.sort(key=lambda x:abs(x[1].get("combined",0)),reverse=True)
    if not _all: return
    print("  SIGNAL INTELLIGENCE SCORES:")
    for _sym,_res in _all[:8]:
        _reasons=_res.get("reasons",[])
        _intel=[r for r in _reasons if any(k in r.lower() for k in
            ["hormuz","dprk","flood","congress","fear","greed","iran","war","taiwan","ceasefire"])]
        _tech=[r for r in _reasons if r not in _intel]
        print(f"    {_sym:<12} {_res.get('signal','?'):<5} score:{_res.get('combined',0):+d} conf:{_res.get('confidence',0)}%")
        if _intel: print(f"      [INTEL] {_intel[0][:55]}")
        if _tech: print(f"      [TECH]  {_tech[0][:55]}")


def get_available_capital(exchange):
    """Get tradeable capital from all assets, not just USDT"""
    try:
        balances = exchange.fetch_balance()
        usdt = float(balances.get('USDT', {}).get('free', 0))
        # Check other tradeable assets
        assets = {}
        for coin in ['BTC','ETH','SOL','BNB','XRP','ADA','DOT','AVAX']:
            bal = float(balances.get(coin, {}).get('free', 0))
            if bal > 0:
                try:
                    ticker = exchange.fetch_ticker(f'{coin}/USDT')
                    usd_val = bal * ticker['last']
                    if usd_val > 1.0:
                        assets[coin] = {'qty': bal, 'usd': usd_val}
                except: pass
        total_usd = usdt + sum(v['usd'] for v in assets.values())
        return usdt, assets, total_usd
    except Exception as e:
        log(f"  [CAPITAL] {str(e)[:40]}", "warning")
        return 0, {}, 0

def liquidate_all_to_usdt():
    """
    One-time reset: sell every non-USDT crypto asset currently held in the
    Binance account back to USDT, then clear in-memory trade tracking and
    the persisted sizing/loss state so the bot starts genuinely fresh under
    the new max_open_trades=1 / partial-TP logic. Scans real account
    balances rather than the in-memory open_trades dict, since that dict is
    never persisted and would miss anything orphaned by a prior restart.
    Only runs when the LIQUIDATE_AND_RESET env var is set.
    """
    log("  [RESET] LIQUIDATE_AND_RESET is set — selling all non-USDT crypto holdings...")
    telegram("<b>RESET STARTED</b>\nLiquidating all crypto holdings to USDT.")
    try:
        ts = binance_time()
        r = requests.get(
            f"https://api.binance.com/api/v3/account?{sign_binance({'timestamp': ts})}",
            headers=binance_headers(), timeout=10)
        r.raise_for_status()
        balances = r.json()["balances"]
    except Exception as e:
        log(f"  [RESET] Failed to fetch account balances: {e}", "error")
        telegram(f"<b>RESET FAILED</b>\nCouldn't fetch balances: {e}")
        return

    sold, skipped = [], []
    for b in balances:
        asset = b["asset"]
        free  = float(b["free"])
        if asset == "USDT" or free <= 0:
            continue
        symbol = f"{asset}USDT"
        try:
            price = float(requests.get(
                f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
                timeout=5).json()["price"])
        except Exception:
            skipped.append(f"{asset} (no direct USDT pair — needs manual handling)")
            continue
        lot   = get_lot_info(symbol)
        value = free * price
        if value < lot["min_notional"]:
            skipped.append(f"{asset} (${value:.2f} below ${lot['min_notional']:.2f} min — dust)")
            continue
        try:
            order    = place_crypto_order(symbol, "SELL", free)
            proceeds = float(order.get("cummulativeQuoteQty", value))
            sold.append(f"{asset}: ${proceeds:.2f}")
            log(f"  [RESET] Sold {asset} -> ${proceeds:.2f} USDT")
        except Exception as e:
            skipped.append(f"{asset} (sell failed: {e})")
            log(f"  [RESET] {asset} sell failed: {e}", "warning")

    open_trades.clear()
    for f in (DAILY_LOSS_FILE, STARTING_BALANCE_FILE, OPEN_TRADES_FILE):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass

    summary = (
        f"RESET COMPLETE\n"
        f"Sold: {', '.join(sold) if sold else 'nothing'}\n"
        f"Skipped: {', '.join(skipped) if skipped else 'nothing'}\n"
        f"Trade tracking + sizing baseline cleared.\n"
        f"IMPORTANT: remove LIQUIDATE_AND_RESET from Railway variables now,"
        f" or the next restart will try to liquidate again."
    )
    log(f"  [RESET] {summary}")
    telegram(f"<b>RESET COMPLETE</b>\nSold: {', '.join(sold) if sold else 'nothing'}\n"
             f"Skipped: {', '.join(skipped) if skipped else 'nothing'}\n"
             f"Remove LIQUIDATE_AND_RESET from Railway variables now.")


def main():
    build_ai_providers()
    _load_daily_loss_state()
    load_open_trades()
    if os.getenv("LIQUIDATE_AND_RESET", "").lower() in ("1", "true", "yes"):
        liquidate_all_to_usdt()
    log("=" * 55)
    log("  ACCRA BOT v9 - MULTI-AI POWERHOUSE ENGINE")
    log(f"  Crypto:  ALL top coins {'[ON]' if BINANCE_KEY else '[NO KEY]'}")
    log(f"  Stocks:  DISABLED")
    log(f"  HFM:     DISABLED")
    _ai_names = [p["name"] for p in AI_PROVIDERS]
    log(f"  AI:      {', '.join(_ai_names) if _ai_names else 'none configured'}")
    log(f"  GitHub:  {'ACTIVE' if GITHUB_TOKEN else 'not configured'}")
    log(f"  Mode:    {'PAPER (PAPER_MODE=true)' if PAPER_MODE else 'LIVE'}")
    if MAX_DAILY_LOSS_USD:
        log(f"  DailyLoss: ${MAX_DAILY_LOSS_USD:.2f} limit | today so far: ${_daily_realized_pnl_usd:+.2f}")
    else:
        log("  DailyLoss: disabled")
    log(f"  Interval:{SLEEP_SECS}s")
    build_ai_providers()
    log("=" * 55)

    if not any([BINANCE_KEY, ALPACA_KEY, HFM_ACCOUNT, EXNESS_LOGIN]):
        log("ERROR: No API keys set", "error")
        return

    log("\nConnecting...")
    connected = []

    if BINANCE_KEY:
        try:
            p = get_crypto_price("BTCUSDT")
            log(f"  Binance: BTC=${p:,.2f} [OK]")
            connected.append("Binance")
        except Exception as e:
            log(f"  Binance: FAILED - {e}", "error")

    if ALPACA_KEY:
        try:
            cash = get_alpaca_cash()
            mode = "PAPER" if "paper" in ALPACA_BASE else "LIVE"
            log(f"  Alpaca [{mode}]: Cash=${cash:,.2f} [OK]")
            connected.append(f"Alpaca[{mode}]")
        except Exception as e:
            log(f"  Alpaca: FAILED - {e}", "error")

    if HFM_ACCOUNT or EXNESS_LOGIN:
        log("  HFM/Exness: Signal mode [OK]")
        connected.append("HFM+Exness")

    if not connected:
        log("No markets connected. Check API keys.", "error")
        return

    # Set GitHub remote with token
    if GITHUB_TOKEN:
        try:
            subprocess.run([
                "git", "remote", "set-url", "origin",
                f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git",
            ], cwd=os.path.expanduser("~/accra-bot"), capture_output=True)
        except Exception:
            pass

    telegram(
        f"<b>ACCRA SUPER BOT v8 STARTED</b>\n"
        f"Connected: {', '.join(connected)}\n"
        f"Scanning ALL assets dynamically\n"
        f"Crypto: REAL | Stocks: PAPER | Forex: SIGNALS\n"
        f"Terminal sync: GitHub\n"
        f"Interval: {SLEEP_SECS}s"
    )

    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"[Cycle error] {e}", "error")
            telegram(f"<b>CYCLE ERROR</b>\n{e}")
            if "418" in str(e):
                log("  [BAN] 418 - sleeping 10 min", "error")
                time.sleep(600)
        save_open_trades()
        # ── Dream cycle ──────────────────────────────────
        global dream_counter
        dream_counter += 1
        if dream_counter >= DREAM_EVERY:
            dream_counter = 0
            run_dream_cycle()

        # ── trade.xyz independent scan ────────────────────
        if XYZ_ENABLED: xyz_scan_and_trade()

        log(f"\n  Sleeping {SLEEP_SECS}s...")
        # Auto-reconnect if internet drops
    for attempt in range(SLEEP_SECS):
        time.sleep(1)
        try:
            requests.get("https://api.binance.com/api/v3/ping", timeout=3)
            break  # Internet is back
        except:
            if attempt % 10 == 0:
                log(f"  [NET] Waiting for internet... {attempt}s")
            continue


if __name__ == "__main__":
    main()

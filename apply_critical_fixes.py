"""
apply_critical_fixes.py — Applies 3 critical fixes to bot.py

Fix 1: Position sizing — drop max_pct from 40% to 5%
Fix 2: AI critic moved out of execution path (advisory only)
Fix 3: SQLite trade journal replaces JSON corruption risk

Run from C:\\Users\\HP\\accra-bot:
    python apply_critical_fixes.py
"""

import os, shutil, sys

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
BAK_PATH = BOT_PATH + ".critfix.bak"

if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"Backup saved -> {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    src = f.read()

original = src
patches  = []

# ─────────────────────────────────────────────────────────────
# FIX 1 — Position sizing: max_pct 40% → 5%
# Also tighten the risk_sizer call cap
# ─────────────────────────────────────────────────────────────
FIX1_MARKER = "                        _sizing = risk_sizer(\n                            usdt=bal, confidence=conf,\n                            closes=_cls_rs, sl_pct=cfg.get(\"sl\", 0.05),\n                        )"
FIX1_INJECT = """                        _sizing = risk_sizer(
                            usdt=bal, confidence=conf,
                            closes=_cls_rs, sl_pct=cfg.get("sl", 0.05),
                            max_pct=0.05,   # CRITICAL FIX: was 0.40, now 5% max
                        )"""

if FIX1_MARKER in src:
    src = src.replace(FIX1_MARKER, FIX1_INJECT, 1)
    patches.append("FIX 1: max_pct 40% -> 5%")
else:
    # Fallback: patch the default in bot_upgrades.py reference
    FIX1_MARKER2 = "               max_pct: float = 0.40) -> dict:"
    FIX1_INJECT2 = "               max_pct: float = 0.05) -> dict:  # CRITICAL FIX: 5% max"
    if FIX1_MARKER2 in src:
        src = src.replace(FIX1_MARKER2, FIX1_INJECT2, 1)
        patches.append("FIX 1: max_pct default 40% -> 5%")
    else:
        print("  FIX 1 marker not found — patching bot_upgrades.py directly")
        ug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_upgrades.py")
        if os.path.exists(ug_path):
            with open(ug_path, "r", encoding="utf-8") as f:
                ug_src = f.read()
            ug_src = ug_src.replace(
                "               max_pct: float = 0.40) -> dict:",
                "               max_pct: float = 0.05) -> dict:  # CRITICAL FIX: 5% max"
            )
            with open(ug_path, "w", encoding="utf-8") as f:
                f.write(ug_src)
            patches.append("FIX 1: max_pct 40% -> 5% (in bot_upgrades.py)")

# ─────────────────────────────────────────────────────────────
# FIX 2 — AI critic: move out of execution path
# Critic now runs ADVISORY only — logs verdict but never blocks
# Execution becomes fully deterministic
# ─────────────────────────────────────────────────────────────
FIX2_MARKER = """                    try:
                        # 1. Critic agent — adversarial AI review
                        _fg_val_now = _fg_cache.get("value", 50)
                        _critic = critic_agent(
                            symbol=symbol, signal=signal,
                            score=conf, confidence=conf,
                            rsi=calc_rsi(get_crypto_closes(symbol, 30)),
                            reasons=[], usdt=bal,
                            open_trades=len(open_trades),
                            fear_greed=_fg_val_now,
                            market=market,
                            call_ai_fn=call_multi_ai,
                        )
                        if not _critic["approved"]:
                            log(f"  [CRITIC] BLOCKED {symbol}: {_critic['verdict']}")
                            return False
                        # Adjust confidence from critic
                        conf = max(0, min(100, conf + _critic["confidence_adj"]))"""

FIX2_INJECT = """                    try:
                        # 1. Critic agent — ADVISORY ONLY (never blocks execution)
                        # Moved out of execution path per critical review:
                        # AI providers fail, outputs drift, parsing breaks.
                        # Execution must be deterministic.
                        _fg_val_now = _fg_cache.get("value", 50)
                        try:
                            _critic = critic_agent(
                                symbol=symbol, signal=signal,
                                score=conf, confidence=conf,
                                rsi=calc_rsi(get_crypto_closes(symbol, 30)),
                                reasons=[], usdt=bal,
                                open_trades=len(open_trades),
                                fear_greed=_fg_val_now,
                                market=market,
                                call_ai_fn=call_multi_ai,
                            )
                            # ADVISORY: log verdict but never block
                            _critic_verdict = _critic.get("verdict", "")
                            _critic_approved = _critic.get("approved", True)
                            _critic_adj = _critic.get("confidence_adj", 0)
                            if not _critic_approved:
                                log(f"  [CRITIC ADVISORY] {symbol}: {_critic_verdict[:60]}")
                                log(f"  [CRITIC ADVISORY] Warning noted — execution continues (deterministic)")
                            else:
                                log(f"  [CRITIC ADVISORY] {symbol}: approved | {_critic_verdict[:60]}")
                            # Soft confidence adjustment only (never hard block)
                            conf = max(0, min(100, conf + max(-10, _critic_adj)))
                        except Exception as _crit_e:
                            log(f"  [CRITIC] Skipped (non-blocking): {_crit_e}", "warning")"""

if FIX2_MARKER in src:
    src = src.replace(FIX2_MARKER, FIX2_INJECT, 1)
    patches.append("FIX 2: AI critic moved to advisory-only")
else:
    print("  FIX 2 marker not found — skipping")

# ─────────────────────────────────────────────────────────────
# FIX 3 — SQLite trade journal
# Replace JSON log_trade with SQLite writes
# Add SQLite init at top of main()
# ─────────────────────────────────────────────────────────────

# 3a: Add SQLite import and init function after existing imports
FIX3_IMPORT_MARKER = "LOG_FILE       = \"trade_log.json\""
FIX3_IMPORT_INJECT = """LOG_FILE       = "trade_log.json"
DB_FILE        = os.path.expanduser("~/accra-bot/trades.db")

def init_db():
    \"\"\"Initialise SQLite trade journal. Safe to call multiple times.\"\"\"
    try:
        import sqlite3
        con = sqlite3.connect(DB_FILE)
        con.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT,
                symbol        TEXT,
                action        TEXT,
                market        TEXT,
                price         REAL,
                quantity      REAL,
                amount_usdt   REAL,
                confidence    INTEGER,
                combined      INTEGER,
                tech          INTEGER,
                fund          INTEGER,
                rsi           REAL,
                fear_greed    INTEGER,
                btc_trend     REAL,
                position_size REAL,
                sl_price      REAL,
                tp_price      REAL,
                entry_reasons TEXT,
                strategy      TEXT,
                market_regime TEXT,
                pnl_pct       REAL,
                won           INTEGER,
                closed_at     TEXT,
                latency_ms    REAL
            )
        \"\"\")
        con.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS metrics (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT,
                usdt_bal   REAL,
                open_trades INTEGER,
                win_rate   REAL,
                profit_factor REAL,
                expectancy REAL,
                sharpe     REAL,
                max_dd     REAL,
                cycle      INTEGER
            )
        \"\"\")
        con.commit()
        con.close()
        log("  [DB] SQLite trade journal ready")
    except Exception as e:
        log(f"  [DB] Init error: {e}", "warning")

def db_log_trade(entry: dict):
    \"\"\"Write a trade to SQLite. Falls back to JSON on error.\"\"\"
    try:
        import sqlite3, json as _j
        con = sqlite3.connect(DB_FILE)
        con.execute(\"\"\"
            INSERT INTO trades (
                ts, symbol, action, market, price, quantity,
                amount_usdt, confidence, combined, tech, fund,
                rsi, fear_greed, btc_trend, position_size,
                sl_price, tp_price, entry_reasons, strategy,
                market_regime, pnl_pct, won, closed_at, latency_ms
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        \"\"\", (
            entry.get("time", entry.get("ts", "")),
            entry.get("symbol",""),
            entry.get("action",""),
            entry.get("market",""),
            entry.get("price", 0),
            entry.get("quantity", 0),
            entry.get("amount_usdt", 0),
            entry.get("confidence", 0),
            entry.get("combined", 0),
            entry.get("tech", 0),
            entry.get("fund", 0),
            entry.get("rsi", 0),
            entry.get("fear_greed", 0),
            entry.get("btc_trend", 0),
            entry.get("position_size", 0),
            entry.get("sl_price", 0),
            entry.get("tp_price", 0),
            _j.dumps(entry.get("reasons", [])),
            entry.get("strategy",""),
            entry.get("market_regime",""),
            entry.get("pnl_pct", None),
            1 if entry.get("won") else (0 if entry.get("won") is False else None),
            entry.get("closed_at", None),
            entry.get("latency_ms", None),
        ))
        con.commit()
        con.close()
    except Exception as e:
        log(f"  [DB] Write error: {e} — falling back to JSON", "warning")
        log_trade(entry)   # fallback

def db_get_metrics() -> dict:
    \"\"\"Compute real performance metrics from SQLite.\"\"\"
    try:
        import sqlite3
        con = sqlite3.connect(DB_FILE)
        rows = con.execute(
            "SELECT pnl_pct, won FROM trades WHERE won IS NOT NULL"
        ).fetchall()
        con.close()
        if len(rows) < 3:
            return {}
        pnls = [r[0] for r in rows if r[0] is not None]
        wins = [r for r in rows if r[1] == 1]
        losses = [r for r in rows if r[1] == 0]
        win_rate = len(wins) / len(rows) if rows else 0
        avg_win  = sum(r[0] for r in wins)  / len(wins)  if wins   else 0
        avg_loss = sum(r[0] for r in losses)/ len(losses) if losses else 0
        profit_factor = abs(avg_win * len(wins)) / abs(avg_loss * len(losses)) if losses and avg_loss != 0 else 999
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        mean_pnl = sum(pnls) / len(pnls)
        variance = sum((p - mean_pnl)**2 for p in pnls) / len(pnls)
        import math as _math
        std_pnl  = _math.sqrt(variance) if variance > 0 else 1
        sharpe   = (mean_pnl / std_pnl) * _math.sqrt(252) if std_pnl > 0 else 0
        cumulative = 0
        peak = 0
        max_dd = 0
        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        return {
            "total_trades":   len(rows),
            "win_rate":       round(win_rate * 100, 1),
            "profit_factor":  round(profit_factor, 2),
            "expectancy":     round(expectancy, 3),
            "sharpe":         round(sharpe, 2),
            "max_drawdown":   round(max_dd, 2),
            "avg_win_pct":    round(avg_win, 2),
            "avg_loss_pct":   round(avg_loss, 2),
        }
    except Exception as e:
        log(f"  [DB] Metrics error: {e}", "warning")
        return {}"""

if FIX3_IMPORT_MARKER in src:
    src = src.replace(FIX3_IMPORT_MARKER, FIX3_IMPORT_INJECT, 1)
    patches.append("FIX 3a: SQLite init + db_log_trade + db_get_metrics added")
else:
    print("  FIX 3a marker not found — skipping")

# 3b: Call init_db() in main() after build_ai_providers()
FIX3_MAIN_MARKER = "    build_ai_providers()\n    log(\"=\" * 55)"
FIX3_MAIN_INJECT = """    build_ai_providers()
    init_db()   # FIX 3: initialise SQLite trade journal
    log("=" * 55)"""

if FIX3_MAIN_MARKER in src:
    src = src.replace(FIX3_MAIN_MARKER, FIX3_MAIN_INJECT, 1)
    patches.append("FIX 3b: init_db() called in main()")
else:
    print("  FIX 3b marker not found — skipping")

# 3c: Replace log_trade calls in run_cycle BUY block with db_log_trade
# and enrich the entry with more fields
FIX3_BUY_MARKER = """                log_trade({
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
            })"""

FIX3_BUY_INJECT = """                _strat_now = load_strategy()
                db_log_trade({
                "time":         datetime.now().isoformat(),
                "symbol":       sym,
                "action":       "BUY",
                "price":        sig["price"],
                "market":       sig["market"],
                "confidence":   sig["confidence"],
                "combined":     sig["combined"],
                "tech":         sig["tech"],
                "fund":         sig["fund"],
                "rsi":          sig.get("rsi", 0),
                "fear_greed":   get_fear_greed().get("value", 50),
                "position_size":sig.get("cfg", {}).get("pct", 5),
                "sl_price":     round(sig["price"] * (1 - sig.get("cfg",{}).get("sl",0.05)), 6),
                "tp_price":     round(sig["price"] * (1 + sig.get("cfg",{}).get("tp",0.05)), 6),
                "strategy":     _strat_now.get("mode","balanced"),
                "market_regime":_strat_now.get("market_condition","neutral"),
                "reasons":      sig["reasons"],
                "fund_reason":  sig.get("fund_reason", ""),
                "top_risk":     sig.get("top_risk", ""),
                "ghana":        sig.get("ghana", ""),
            })
                log_trade({   # keep JSON as secondary backup
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
            })"""

if FIX3_BUY_MARKER in src:
    src = src.replace(FIX3_BUY_MARKER, FIX3_BUY_INJECT, 1)
    patches.append("FIX 3c: BUY trades write to SQLite")
else:
    print("  FIX 3c marker not found — skipping")

# 3d: Add metrics log to status push
FIX3_STATUS_MARKER = '"version": "v9",'
FIX3_STATUS_INJECT = '"version": "v9",\n        "metrics": db_get_metrics(),'

if FIX3_STATUS_MARKER in src:
    src = src.replace(FIX3_STATUS_MARKER, FIX3_STATUS_INJECT, 1)
    patches.append("FIX 3d: real metrics added to status push")
else:
    print("  FIX 3d marker not found — skipping")

# ─────────────────────────────────────────────────────────────
# FIX 4 — Circuit breakers: spread explosion + volatility shock
# ─────────────────────────────────────────────────────────────
FIX4_MARKER = "def check_usdt_safety(min_usdt=10.0):"
FIX4_INJECT = """def check_circuit_breakers(symbol: str, closes: list) -> tuple:
    \"\"\"
    Additional circuit breakers per reviewer recommendations.
    Returns (ok: bool, reason: str)
    \"\"\"
    try:
        # Volatility shock: if last candle moved > 8% halt
        if len(closes) >= 2:
            last_move = abs(closes[-1] - closes[-2]) / closes[-2] * 100
            if last_move > 8.0:
                return False, f"Volatility shock: {last_move:.1f}% candle move on {symbol}"

        # Rapid consecutive moves: 3 candles all > 3% same direction
        if len(closes) >= 4:
            moves = [(closes[i] - closes[i-1]) / closes[i-1] * 100
                     for i in range(-3, 0)]
            all_up   = all(m > 3 for m in moves)
            all_down = all(m < -3 for m in moves)
            if all_up:
                return False, f"Parabolic move detected on {symbol} — avoid chasing"
            if all_down:
                return False, f"Freefall detected on {symbol} — avoid catching knife"

        return True, "Circuit breakers OK"
    except Exception as e:
        return True, f"Breaker check error: {e}"

def check_usdt_safety(min_usdt=10.0):"""

if FIX4_MARKER in src:
    src = src.replace(FIX4_MARKER, FIX4_INJECT, 1)
    patches.append("FIX 4: volatility + parabolic circuit breakers added")
else:
    print("  FIX 4 marker not found — skipping")

# Wire circuit breakers into the crypto scan loop
FIX4_WIRE_MARKER = "                sig   = unified_signal(sym, closes, \"crypto\", strategy)"
FIX4_WIRE_INJECT = """                _cb_ok, _cb_reason = check_circuit_breakers(sym, closes)
                if not _cb_ok:
                    log(f"  [BREAKER] {sym}: {_cb_reason}")
                    continue
                sig   = unified_signal(sym, closes, "crypto", strategy)"""

if FIX4_WIRE_MARKER in src:
    src = src.replace(FIX4_WIRE_MARKER, FIX4_WIRE_INJECT, 1)
    patches.append("FIX 4b: circuit breakers wired into crypto scan")
else:
    print("  FIX 4b marker not found — skipping")

# ── Write ────────────────────────────────────────────────────
if src == original:
    print("\nNo patches applied.")
    sys.exit(1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nPatches applied ({len(patches)}):")
for p in patches:
    print(f"   * {p}")

print("""
==================================================
  NEXT STEPS:
  python apply_critical_fixes.py
  git add -A
  git commit -m "Critical fixes: 5% sizing, advisory critic, SQLite, circuit breakers"
  git push origin master
==================================================
""")

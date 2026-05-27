"""
apply_neural.py — Wires neural_signal.py into bot.py
Run from C:\\Users\\HP\\accra-bot:

    python apply_neural.py
"""

import os, shutil, sys

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
BAK_PATH = BOT_PATH + ".neural.bak"
NN_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neural_signal.py")

if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found.")
    sys.exit(1)

if not os.path.exists(NN_PATH):
    print(f"ERROR: neural_signal.py not found in same folder.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"Backup saved -> {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    src = f.read()

original = src
patches  = []

# ─────────────────────────────────────────────────────────────
# PATCH 1 — Import neural_signal after bot_upgrades import
# ─────────────────────────────────────────────────────────────
NN_IMPORT_MARKER = "    UPGRADES_ENABLED = True\nexcept Exception as _upg_err:\n    UPGRADES_ENABLED = False"
NN_IMPORT_INJECT = """    UPGRADES_ENABLED = True
except Exception as _upg_err:
    UPGRADES_ENABLED = False

try:
    from neural_signal import (
        neural_score, save_pending_features,
        resolve_trade_outcome, nn_status, print_nn_status,
    )
    NN_ENABLED = True
except Exception as _nn_err:
    NN_ENABLED = False
    print(f"[NN] Not loaded: {_nn_err}")"""

if NN_IMPORT_MARKER in src:
    src = src.replace(NN_IMPORT_MARKER, NN_IMPORT_INJECT, 1)
    patches.append("PATCH 1: neural_signal import")
else:
    print("  PATCH 1 marker not found — skipping")

# ─────────────────────────────────────────────────────────────
# PATCH 2 — Neural gate inside execute() BUY block
# Insert after the risk sizer block, before RE-ENTRY FILTER
# ─────────────────────────────────────────────────────────────
NN_GATE_MARKER = "                        # Override amount with risk-sized amount\n                        amount = _sizing[\"amount\"]"
NN_GATE_INJECT = """                        # Override amount with risk-sized amount
                        amount = _sizing["amount"]

                    # ── NEURAL NETWORK GATE ───────────────────────────────
                    if NN_ENABLED:
                        try:
                            from datetime import datetime as _dtnn, timezone as _tznn
                            import requests as _rqnn
                            # Gather features for NN
                            _cls_nn  = get_crypto_closes(symbol, 50)
                            _rsi_nn  = calc_rsi(_cls_nn) if len(_cls_nn) > 14 else 50.0
                            _macd_nn = calc_macd(_cls_nn)
                            _bb_nn   = calc_bb(_cls_nn)
                            _ema9_nn = calc_ema(_cls_nn, 9)
                            _ema21_nn= calc_ema(_cls_nn, 21)
                            _ema_cross_nn = 0
                            if _ema9_nn and _ema21_nn:
                                _ema_cross_nn = 1 if _ema9_nn[-1] > _ema21_nn[-1] else -1
                            _mom_nn = (_cls_nn[-1]/_cls_nn[-6]-1)*100 if len(_cls_nn)>=6 else 0
                            _moves_nn = [abs(_cls_nn[i]-_cls_nn[i-1]) for i in range(-20,-1)] if len(_cls_nn)>=20 else [0]
                            _avg_move_nn = sum(_moves_nn)/len(_moves_nn) if _moves_nn else 1
                            _last_move_nn = abs(_cls_nn[-1]-_cls_nn[-2]) if len(_cls_nn)>=2 else 0
                            _vol_ratio_nn = _last_move_nn/_avg_move_nn if _avg_move_nn > 0 else 1.0
                            _atr_nn = sum(abs(_cls_nn[i]-_cls_nn[i-1]) for i in range(-14,-1))/(13*_cls_nn[-1]) if len(_cls_nn)>=14 else 0.01
                            _fg_nn  = _fg_cache.get("value", 50)
                            _hour_nn = _dtnn.now(_tznn.utc).hour
                            # BTC 4h trend
                            _btc_trend_nn = 0.0
                            try:
                                _r_btc = _rqnn.get("https://api.binance.com/api/v3/klines",
                                    params={"symbol":"BTCUSDT","interval":"4h","limit":2},timeout=5)
                                if _r_btc.ok:
                                    _kk = _r_btc.json()
                                    _btc_trend_nn = (float(_kk[-1][4])-float(_kk[0][4]))/float(_kk[0][4])*100
                            except Exception: pass

                            _nn_result = neural_score(
                                rsi=_rsi_nn,
                                macd_hist=_macd_nn.get("histogram", 0),
                                bb_pct=_bb_nn.get("pct_b", 0.5),
                                ema_cross=_ema_cross_nn,
                                momentum=_mom_nn,
                                vol_ratio=_vol_ratio_nn,
                                atr_pct=_atr_nn,
                                fear_greed=_fg_nn,
                                score=conf,
                                confidence=conf,
                                hour_utc=_hour_nn,
                                btc_trend_pct=_btc_trend_nn,
                            )
                            log(f"  [NN] {symbol} quality={_nn_result['quality']:.2f} {_nn_result['label']}")
                            if not _nn_result["gate"]:
                                log(f"  [NN] BLOCKED {symbol}: {_nn_result['reason']}")
                                return False
                            # Save features so we can record outcome later
                            _trade_id = f"{symbol}_{int(time.time())}"
                            save_pending_features(_trade_id, _nn_result["features"])
                            # Store trade_id so execute caller can resolve it
                            open_trades.setdefault(symbol, {})["nn_trade_id"] = _trade_id
                        except Exception as _nn_e:
                            log(f"  [NN] Gate error: {_nn_e}", "warning")
                    # ─────────────────────────────────────────────────────"""

if NN_GATE_MARKER in src:
    src = src.replace(NN_GATE_MARKER, NN_GATE_INJECT, 1)
    patches.append("PATCH 2: neural gate in execute() BUY")
else:
    print("  PATCH 2 marker not found — skipping")

# ─────────────────────────────────────────────────────────────
# PATCH 3 — Resolve trade outcome when a trade closes (AUTO-CLOSE)
# Insert after the log_trade call in the to_close loop
# ─────────────────────────────────────────────────────────────
NN_RESOLVE_MARKER = '            "pnl": pnl, "market": market,\n        })'
NN_RESOLVE_INJECT = '''            "pnl": pnl, "market": market,
        })
        # ── NN outcome resolution ─────────────────────────────
        if NN_ENABLED:
            try:
                _nn_tid = open_trades.get(sym, {}).get("nn_trade_id", "")
                if _nn_tid:
                    resolve_trade_outcome(_nn_tid, won=pnl > 0)
            except Exception as _nn_re:
                log(f"  [NN] Resolve error: {_nn_re}", "warning")
        # ─────────────────────────────────────────────────────'''

if NN_RESOLVE_MARKER in src:
    src = src.replace(NN_RESOLVE_MARKER, NN_RESOLVE_INJECT, 1)
    patches.append("PATCH 3: NN outcome resolution on trade close")
else:
    print("  PATCH 3 marker not found — skipping")

# ─────────────────────────────────────────────────────────────
# PATCH 4 — Print NN status in main() startup banner
# ─────────────────────────────────────────────────────────────
NN_BANNER_MARKER = "    if UPGRADES_ENABLED:\n        print_upgrade_status()\n    else:\n        log(\"  ⚠  bot_upgrades.py not found — running without upgrades\", \"warning\")"
NN_BANNER_INJECT = """    if UPGRADES_ENABLED:
        print_upgrade_status()
    else:
        log("  bot_upgrades.py not found - running without upgrades", "warning")

    if NN_ENABLED:
        print_nn_status()
    else:
        log("  neural_signal.py not found - running without NN", "warning")"""

if NN_BANNER_MARKER in src:
    src = src.replace(NN_BANNER_MARKER, NN_BANNER_INJECT, 1)
    patches.append("PATCH 4: NN status in main() banner")
else:
    print("  PATCH 4 marker not found - skipping")

# ── Write ────────────────────────────────────────────────────
if src == original:
    print("\nNo patches applied. Check bot.py matches expected version.")
    sys.exit(1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nPatches applied ({len(patches)}/4):")
for p in patches:
    print(f"   * {p}")

print("""
==================================================
  NEXT STEPS:
  1. Copy neural_signal.py to C:\\Users\\HP\\accra-bot\\
  2. python apply_neural.py
  3. git add -A
  4. git commit -m "Add neural network signal scorer"
  5. git push origin master
==================================================
""")

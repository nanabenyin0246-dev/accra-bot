"""
apply_upgrades.py â€” Auto-patches bot.py with all 5 upgrades.
Run once from ~/accra-bot:

    python3 apply_upgrades.py

Creates a backup at bot.py.bak before touching anything.
"""

import os, shutil, sys

BOT_PATH = os.path.expanduser("~/accra-bot/bot.py")
BAK_PATH = BOT_PATH + ".bak"
UPG_PATH = os.path.expanduser("~/accra-bot/bot_upgrades.py")

# â”€â”€ Safety checks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found. Run from ~/accra-bot or adjust BOT_PATH.")
    sys.exit(1)

if not os.path.exists(UPG_PATH):
    print(f"ERROR: {UPG_PATH} not found. Copy bot_upgrades.py to ~/accra-bot first.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"âœ… Backup saved â†’ {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    src = f.read()

original_src = src
patches_applied = []

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATCH 1 â€” Import upgrades at the top (after existing imports)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
IMPORT_MARKER = "from datetime import datetime\nfrom urllib.parse import urlencode"
IMPORT_INJECT = """from datetime import datetime
from urllib.parse import urlencode

# â”€â”€ ZOSTAFF UPGRADES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
try:
    from bot_upgrades import (
        kill_switch, critic_agent, risk_sizer,
        FeaturePipeline, build_standard_pipeline,
        deflated_sharpe_gate, returns_from_closes,
        print_upgrade_status, _load_attempt_count,
    )
    UPGRADES_ENABLED = True
except Exception as _upg_err:
    UPGRADES_ENABLED = False
    print(f"[UPGRADES] Not loaded: {_upg_err}")
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"""

if IMPORT_MARKER in src:
    src = src.replace(IMPORT_MARKER, IMPORT_INJECT, 1)
    patches_applied.append("PATCH 1: imports")
else:
    print("âš   PATCH 1 marker not found â€” skipping import injection")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATCH 2 â€” Kill-switch check at top of run_cycle()
# Inject right after: `cycle_count += 1`
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CYCLE_MARKER = "def run_cycle():\n    global cycle_count\n    cycle_count += 1"
CYCLE_INJECT = """def run_cycle():
    global cycle_count
    cycle_count += 1

    # â”€â”€ KILL-SWITCH CHECK â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if UPGRADES_ENABLED:
        try:
            _usdt_now = get_crypto_balance("USDT")
            kill_switch.record_balance(_usdt_now)

            # Build consecutive losses from dream insights
            _ins_ks = load_insights() or {}
            _consec  = _ins_ks.get("current_losing_streak", 0)

            # Start-of-day balance (stored in file)
            _sod_file = os.path.expanduser("~/accra-bot/sod_balance.json")
            try:
                import json as _jks
                _sod = _jks.load(open(_sod_file)).get("usdt", _usdt_now)
            except Exception:
                _sod = _usdt_now
                try:
                    import json as _jks
                    _jks.dump({"usdt": _usdt_now, "date": datetime.now().isoformat()}, open(_sod_file, "w"))
                except Exception:
                    pass

            _ks_state = {
                "usdt":               _usdt_now,
                "open_trades":        len(open_trades),
                "last_data_ts":       time.time(),
                "consecutive_losses": _consec,
                "start_of_day_usdt":  _sod,
            }
            _ks_ok, _ks_reason = kill_switch.check(_ks_state)
            if not _ks_ok:
                log(f"  [KILL-SWITCH] {_ks_reason}", "error")
                if "Max open trades" not in _ks_reason:
                    # Only hard-halt blocks the whole cycle
                    # Max open trades just blocks new buys, not the cycle
                    if kill_switch.halted:
                        log("  [KILL-SWITCH] Cycle aborted â€” manual reset required")
                        return
        except Exception as _ks_e:
            log(f"  [KILL-SWITCH] Check error: {_ks_e}", "warning")
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"""

if CYCLE_MARKER in src:
    src = src.replace(CYCLE_MARKER, CYCLE_INJECT, 1)
    patches_applied.append("PATCH 2: kill-switch in run_cycle")
else:
    print("âš   PATCH 2 marker not found â€” skipping kill-switch injection")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATCH 3 â€” Critic agent + DSR gate in execute() before BUY
# Inject right after: `if conf < 25:` block inside execute()
# We target the re-entry filter block which is unique enough
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
EXECUTE_MARKER = "                # RE-ENTRY FILTER: Don't re-buy within 3% of last SL price (Lo & Remorov)"
EXECUTE_INJECT = """                # â”€â”€ CRITIC AGENT + DSR GATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if UPGRADES_ENABLED:
                    try:
                        # 1. Critic agent â€” adversarial AI review
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
                        conf = max(0, min(100, conf + _critic["confidence_adj"]))

                        # 2. Deflated Sharpe gate â€” multiple-testing correction
                        _cls_dsr = get_crypto_closes(symbol, 50)
                        if len(_cls_dsr) >= 20:
                            _rets = returns_from_closes(_cls_dsr, signal_position=1)
                            _dsr  = deflated_sharpe_gate(_rets, n_trials=_load_attempt_count())
                            if not _dsr["passed"]:
                                log(f"  [DSR] BLOCKED {symbol}: {_dsr['reason']}")
                                return False

                        # 3. Risk sizer â€” volatility-adjusted Kelly sizing
                        _cls_rs = get_crypto_closes(symbol, 30)
                        _sizing = risk_sizer(
                            usdt=bal, confidence=conf,
                            closes=_cls_rs, sl_pct=cfg.get("sl", 0.05),
                        )
                        if _sizing["amount"] < 2:
                            log(f"  [SIZER] BLOCKED {symbol}: {_sizing['reason']}")
                            return False
                        log(f"  [SIZER] {symbol}: {_sizing['reason']}")
                        # Override amount with risk-sized amount
                        amount = _sizing["amount"]

                    except Exception as _upg_exec_e:
                        log(f"  [UPGRADES] execute error: {_upg_exec_e}", "warning")
                # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

                # RE-ENTRY FILTER: Don't re-buy within 3% of last SL price (Lo & Remorov)"""

if EXECUTE_MARKER in src:
    src = src.replace(EXECUTE_MARKER, EXECUTE_INJECT, 1)
    patches_applied.append("PATCH 3: critic + DSR + sizer in execute()")
else:
    print("âš   PATCH 3 marker not found â€” skipping critic/DSR injection")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATCH 4 â€” Print upgrade status in main() startup banner
# Inject right after the "=" * 55 closing line in main()
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MAIN_MARKER = '    log(f"  Interval:{SLEEP_SECS}s")\n    build_ai_providers()\n    log("=" * 55)'
MAIN_INJECT  = '''    log(f"  Interval:{SLEEP_SECS}s")
    build_ai_providers()
    log("=" * 55)

    # â”€â”€ UPGRADES STATUS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if UPGRADES_ENABLED:
        print_upgrade_status()
    else:
        log("  âš   bot_upgrades.py not found â€” running without upgrades", "warning")
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€'''

if MAIN_MARKER in src:
    src = src.replace(MAIN_MARKER, MAIN_INJECT, 1)
    patches_applied.append("PATCH 4: upgrade status in main()")
else:
    print("âš   PATCH 4 marker not found â€” skipping main() banner")


# â”€â”€ Write patched file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if src == original_src:
    print("\nâŒ No patches were applied. Check that bot.py matches expected version.")
    sys.exit(1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nâœ… Patches applied ({len(patches_applied)}/4):")
for p in patches_applied:
    print(f"   â€¢ {p}")

print(f"\n{'='*50}")
print("  NEXT STEPS:")
print("  1. cp ~/Desktop/bot_upgrades.py ~/accra-bot/")
print("  2. cp ~/Desktop/apply_upgrades.py ~/accra-bot/")
print("  3. cd ~/accra-bot")
print("  4. python3 apply_upgrades.py")
print("  5. git add -A && git commit -m 'Add zostaff upgrades'")
print("  6. git push origin master")
print(f"{'='*50}\n")



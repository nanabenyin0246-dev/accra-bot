"""
clean_rebuild.py — Surgically fixes bot.py by:
1. Removing ALL duplicate function/variable definitions
2. Replacing the broken execute() BUY block with a clean version
3. Fixing main() duplicates

Run from C:\\Users\\HP\\accra-bot:
    python clean_rebuild.py
"""
import os, shutil, sys, re

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
BAK_PATH = BOT_PATH + ".clean.bak"

if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"Backup -> {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print(f"Loaded {len(lines)} lines")
fixes = []

# ── Helper ────────────────────────────────────────────────────
def find_line(lines, pattern, start=0):
    for i in range(start, len(lines)):
        if pattern in lines[i]:
            return i
    return -1

def find_func_end(lines, start):
    """Find the line after a function ends (next def/class at same or lower indent)."""
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(lines[i]) - len(stripped)
        if indent <= base_indent and (stripped.startswith('def ') or stripped.startswith('class ')):
            return i
    return len(lines)

# ─────────────────────────────────────────────────────────────
# STEP 1: Remove duplicate DB_FILE block
# Find second occurrence of DB_FILE = ... and remove until INSIGHTS_FILE
# ─────────────────────────────────────────────────────────────
db_occurrences = [i for i, l in enumerate(lines) if 'DB_FILE' in l and 'expanduser' in l]
if len(db_occurrences) >= 2:
    second = db_occurrences[1]
    end_marker = find_line(lines, 'INSIGHTS_FILE', second)
    if end_marker > second:
        del lines[second:end_marker]
        fixes.append(f"STEP 1: Removed duplicate DB_FILE block (lines {second}-{end_marker})")
        print(f"  ✓ Removed duplicate DB block ({end_marker - second} lines)")
else:
    print("  ✓ No duplicate DB block found")

# ─────────────────────────────────────────────────────────────
# STEP 2: Remove duplicate check_circuit_breakers
# ─────────────────────────────────────────────────────────────
cb_occurrences = [i for i, l in enumerate(lines) if 'def check_circuit_breakers(' in l]
if len(cb_occurrences) >= 2:
    second = cb_occurrences[1]
    end = find_func_end(lines, second)
    del lines[second:end]
    fixes.append(f"STEP 2: Removed duplicate check_circuit_breakers()")
    print(f"  ✓ Removed duplicate check_circuit_breakers ({end - second} lines)")
else:
    print("  ✓ No duplicate check_circuit_breakers found")

# ─────────────────────────────────────────────────────────────
# STEP 3: Remove duplicate circuit breaker CALL in crypto scan
# ─────────────────────────────────────────────────────────────
cb_calls = [i for i, l in enumerate(lines) if 'check_circuit_breakers(sym, closes)' in l]
if len(cb_calls) >= 2:
    # Keep first, remove second + its if block (3 lines)
    second_call = cb_calls[1]
    # Remove: the _cb_ok line, if not _cb_ok line, log line, continue line
    j = second_call
    while j < len(lines) and j < second_call + 5:
        l = lines[j].strip()
        if l.startswith('_cb_ok') or l.startswith('if not _cb_ok') or \
           '_cb_reason' in l or (l.startswith('log') and 'BREAKER' in l) or l == 'continue':
            lines[j] = ''
            j += 1
        else:
            break
    fixes.append("STEP 3: Removed duplicate circuit breaker call")
    print("  ✓ Removed duplicate circuit breaker call")
else:
    print("  ✓ No duplicate circuit breaker call found")

# ─────────────────────────────────────────────────────────────
# STEP 4: Remove duplicate metrics key in status dict
# ─────────────────────────────────────────────────────────────
metrics_lines = [i for i, l in enumerate(lines) if '"metrics": db_get_metrics()' in l]
if len(metrics_lines) >= 2:
    # Remove first occurrence (keep the one nearest "version" key)
    del lines[metrics_lines[0]]
    fixes.append("STEP 4: Removed duplicate metrics key")
    print("  ✓ Removed duplicate metrics key")
else:
    print("  ✓ No duplicate metrics key found")

# ─────────────────────────────────────────────────────────────
# STEP 5: Fix main() duplicates (build_ai_providers + init_db called twice)
# ─────────────────────────────────────────────────────────────
main_start = find_line(lines, 'def main():')
if main_start >= 0:
    # Find all init_db() calls after main_start
    init_calls = [i for i in range(main_start, len(lines)) if 'init_db()' in lines[i]]
    if len(init_calls) >= 2:
        # Remove the second one
        lines[init_calls[1]] = ''
        fixes.append("STEP 5a: Removed duplicate init_db() in main()")
        print("  ✓ Removed duplicate init_db()")

    # Find all build_ai_providers() calls after main_start
    bap_calls = [i for i in range(main_start, len(lines)) if 'build_ai_providers()' in lines[i] and 'def ' not in lines[i]]
    if len(bap_calls) >= 2:
        lines[bap_calls[1]] = ''
        fixes.append("STEP 5b: Removed duplicate build_ai_providers() in main()")
        print("  ✓ Removed duplicate build_ai_providers()")
else:
    print("  ✗ main() not found")

# ─────────────────────────────────────────────────────────────
# STEP 6: Fix broken execute() BUY block
# Find the execute function and replace the entire BUY crypto block
# ─────────────────────────────────────────────────────────────
exec_start = find_line(lines, 'def execute(symbol, signal, price, cfg, conf, market):')
if exec_start < 0:
    exec_start = find_line(lines, 'def execute(')
    
if exec_start >= 0:
    print(f"  Found execute() at line {exec_start}")
    
    # Find the BUY signal section start
    buy_start = find_line(lines, "if signal == \"BUY\":", exec_start)
    if buy_start < 0:
        buy_start = find_line(lines, 'if signal == "BUY":', exec_start)
    
    # Find RE-ENTRY FILTER line (after our upgrades block)
    reentry = find_line(lines, "RE-ENTRY FILTER:", exec_start)
    
    print(f"  BUY block starts at line {buy_start}")
    print(f"  RE-ENTRY FILTER at line {reentry}")
    
    if buy_start > 0 and reentry > buy_start:
        # Find the conf < 25 check (start of our replacement)
        conf_check = find_line(lines, 'if conf < 25:', buy_start)
        if conf_check < 0:
            conf_check = find_line(lines, "conf < 25", buy_start)
        
        print(f"  conf<25 check at line {conf_check}")
        
        if conf_check > 0 and conf_check < reentry:
            # Get indent from the conf check line
            indent = ' ' * (len(lines[conf_check]) - len(lines[conf_check].lstrip()))
            
            # Build clean replacement block
            clean_block = f'''{indent}if conf < 25:
{indent}    log(f"  SKIP {{symbol}}: conf {{conf}}% < 25% minimum")
{indent}    return False

{indent}# Get balance early — needed by all upgrade checks below
{indent}bal = get_crypto_balance("USDT")

{indent}# ── UPGRADES: Critic (advisory) + DSR Gate + Risk Sizer ──────
{indent}if UPGRADES_ENABLED:
{indent}    try:
{indent}        # 1. Critic — advisory only, never blocks execution
{indent}        _fg_val_now = _fg_cache.get("value", 50)
{indent}        try:
{indent}            _critic = critic_agent(
{indent}                symbol=symbol, signal=signal,
{indent}                score=conf, confidence=conf,
{indent}                rsi=calc_rsi(get_crypto_closes(symbol, 30)),
{indent}                reasons=[], usdt=bal,
{indent}                open_trades=len(open_trades),
{indent}                fear_greed=_fg_val_now,
{indent}                market=market,
{indent}                call_ai_fn=call_multi_ai,
{indent}            )
{indent}            _verdict = _critic.get("verdict", "")
{indent}            if not _critic.get("approved", True):
{indent}                log(f"  [CRITIC ADVISORY] {{symbol}}: {{_verdict[:60]}}")
{indent}            conf = max(0, min(100, conf + max(-10, _critic.get("confidence_adj", 0))))
{indent}        except Exception as _ce:
{indent}            log(f"  [CRITIC] Skipped: {{_ce}}", "warning")

{indent}        # 2. Deflated Sharpe gate
{indent}        _cls_dsr = get_crypto_closes(symbol, 50)
{indent}        if len(_cls_dsr) >= 20:
{indent}            _rets = returns_from_closes(_cls_dsr, signal_position=1)
{indent}            _dsr  = deflated_sharpe_gate(_rets, n_trials=_load_attempt_count())
{indent}            if not _dsr["passed"]:
{indent}                log(f"  [DSR] BLOCKED {{symbol}}: {{_dsr['reason']}}")
{indent}                return False

{indent}        # 3. Risk sizer — 5% max position
{indent}        _cls_rs = get_crypto_closes(symbol, 30)
{indent}        _sizing = risk_sizer(
{indent}            usdt=bal, confidence=conf,
{indent}            closes=_cls_rs, sl_pct=cfg.get("sl", 0.05),
{indent}            max_pct=0.05,
{indent}        )
{indent}        if _sizing["amount"] >= 2:
{indent}            amount = _sizing["amount"]
{indent}            log(f"  [SIZER] {{symbol}}: {{_sizing['reason']}}")

{indent}    except Exception as _upg_e:
{indent}        log(f"  [UPGRADES] execute error: {{_upg_e}}", "warning")

{indent}# ── Neural Network Gate ──────────────────────────────────────
{indent}if NN_ENABLED:
{indent}    try:
{indent}        from datetime import datetime as _dtnn, timezone as _tznn
{indent}        import requests as _rqnn
{indent}        _cls_nn   = get_crypto_closes(symbol, 50)
{indent}        _rsi_nn   = calc_rsi(_cls_nn) if len(_cls_nn) > 14 else 50.0
{indent}        _macd_nn  = calc_macd(_cls_nn)
{indent}        _bb_nn    = calc_bb(_cls_nn)
{indent}        _ema9_nn  = calc_ema(_cls_nn, 9)
{indent}        _ema21_nn = calc_ema(_cls_nn, 21)
{indent}        _ema_cross_nn = 0
{indent}        if _ema9_nn and _ema21_nn:
{indent}            _ema_cross_nn = 1 if _ema9_nn[-1] > _ema21_nn[-1] else -1
{indent}        _mom_nn = (_cls_nn[-1]/_cls_nn[-6]-1)*100 if len(_cls_nn)>=6 else 0
{indent}        _moves_nn = [abs(_cls_nn[i]-_cls_nn[i-1]) for i in range(-20,-1)] if len(_cls_nn)>=20 else [0.01]
{indent}        _avg_move_nn = sum(_moves_nn)/len(_moves_nn) if _moves_nn else 1
{indent}        _last_move_nn = abs(_cls_nn[-1]-_cls_nn[-2]) if len(_cls_nn)>=2 else 0
{indent}        _vol_ratio_nn = _last_move_nn/_avg_move_nn if _avg_move_nn > 0 else 1.0
{indent}        _atr_nn = sum(abs(_cls_nn[i]-_cls_nn[i-1]) for i in range(-14,-1))/(13*_cls_nn[-1]) if len(_cls_nn)>=14 and _cls_nn[-1]>0 else 0.01
{indent}        _fg_nn  = _fg_cache.get("value", 50)
{indent}        _hour_nn = _dtnn.now(_tznn.utc).hour
{indent}        _btc_trend_nn = 0.0
{indent}        try:
{indent}            _r_btc = _rqnn.get("https://api.binance.com/api/v3/klines",
{indent}                params={{"symbol":"BTCUSDT","interval":"4h","limit":2}},timeout=5)
{indent}            if _r_btc.ok:
{indent}                _kk = _r_btc.json()
{indent}                _btc_trend_nn = (float(_kk[-1][4])-float(_kk[0][4]))/float(_kk[0][4])*100
{indent}        except Exception:
{indent}            pass
{indent}        _nn_result = neural_score(
{indent}            rsi=_rsi_nn, macd_hist=_macd_nn.get("histogram", 0),
{indent}            bb_pct=_bb_nn.get("pct_b", 0.5), ema_cross=_ema_cross_nn,
{indent}            momentum=_mom_nn, vol_ratio=_vol_ratio_nn, atr_pct=_atr_nn,
{indent}            fear_greed=_fg_nn, score=conf, confidence=conf,
{indent}            hour_utc=_hour_nn, btc_trend_pct=_btc_trend_nn,
{indent}        )
{indent}        log(f"  [NN] {{symbol}} quality={{_nn_result['quality']:.2f}} {{_nn_result['label']}}")
{indent}        if not _nn_result["gate"]:
{indent}            log(f"  [NN] BLOCKED {{symbol}}: {{_nn_result['reason']}}")
{indent}            return False
{indent}        _trade_id = f"{{symbol}}_{{int(time.time())}}"
{indent}        save_pending_features(_trade_id, _nn_result["features"])
{indent}        open_trades.setdefault(symbol, {{}})["nn_trade_id"] = _trade_id
{indent}    except Exception as _nn_e:
{indent}        log(f"  [NN] Gate error: {{_nn_e}}", "warning")

'''
            # Replace lines from conf_check to reentry-1
            new_lines = clean_block.split('\n')
            new_lines = [l + '\n' for l in new_lines]
            lines[conf_check:reentry] = new_lines
            fixes.append(f"STEP 6: Replaced broken execute() BUY block ({reentry - conf_check} lines → {len(new_lines)} lines)")
            print(f"  ✓ Replaced execute() BUY block cleanly")
        else:
            print(f"  ✗ Could not find conf<25 check before RE-ENTRY FILTER")
    else:
        print(f"  ✗ Could not locate BUY block boundaries")
else:
    print("  ✗ execute() function not found")

# ─────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────
src = ''.join(lines)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nFixes applied ({len(fixes)}):")
for fx in fixes:
    print(f"   ✓ {fx}")

# Quick syntax check
import ast
try:
    ast.parse(src)
    print("\n✅ SYNTAX CHECK PASSED — bot.py is valid Python")
except SyntaxError as e:
    print(f"\n❌ SYNTAX ERROR at line {e.lineno}: {e.msg}")
    print(f"   Near: {e.text}")
    print("   Restore from backup: copy bot.py.clean.bak bot.py")

print("""
==================================================
  NEXT STEPS:
  git add -A
  git commit -m "Clean rebuild: all 9 review issues fixed"
  git push origin master
==================================================
""")

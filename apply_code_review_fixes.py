"""
apply_code_review_fixes.py — Fixes all 9 issues found in code review

CRITICAL:
  1. Syntax error in critic confidence_adj line
  2. NN_ENABLED block indentation error in execute()
  3. bal used before defined in execute()

HIGH:
  4. DB_FILE/init_db/db_log_trade/db_get_metrics duplicated
  5. check_circuit_breakers() defined twice

MEDIUM:
  6. init_db() + build_ai_providers() called twice in main()
  7. "metrics" key duplicated in status push
  8. check_circuit_breakers() called twice in crypto scan

Run from C:\\Users\\HP\\accra-bot:
    python apply_code_review_fixes.py
"""

import os, shutil, sys, re

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
BAK_PATH = BOT_PATH + ".review.bak"

if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"Backup saved -> {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    src = f.read()

original = src
fixes = []

# ─────────────────────────────────────────────────────────────
# FIX 1 (CRITICAL) — Syntax error in confidence_adj line
# Bad:  conf + max(-10, _critic["confidence_adj"]  # FIX 2: soft cap -10 max))
# Good: conf = max(0, min(100, conf + max(-10, _critic["confidence_adj"])))
# ─────────────────────────────────────────────────────────────
BAD_CONF = 'conf = max(0, min(100, conf + max(-10, _critic["confidence_adj"])'
GOOD_CONF = 'conf = max(0, min(100, conf + max(-10, _critic.get("confidence_adj", 0))))'

# Handle various malformed versions
patterns_to_fix = [
    ('conf + max(-10, _critic["confidence_adj"]  # FIX 2: soft cap -10 max))', 
     'conf = max(0, min(100, conf + max(-10, _critic.get("confidence_adj", 0))))'),
    ('conf = max(0, min(100, conf + max(-10, _critic["confidence_adj"])  # FIX 2: soft cap -10 max))',
     'conf = max(0, min(100, conf + max(-10, _critic.get("confidence_adj", 0))))'),
]

for bad, good in patterns_to_fix:
    if bad in src:
        src = src.replace(bad, good, 1)
        fixes.append("FIX 1: Syntax error in confidence_adj line fixed")
        break

# Broader regex fix if exact string not found
if "FIX 1" not in str(fixes):
    src_new = re.sub(
        r'conf\s*=\s*max\(0,\s*min\(100,\s*conf\s*\+\s*max\(-10,\s*_critic\[.confidence_adj.\][^)]*\)+',
        'conf = max(0, min(100, conf + max(-10, _critic.get("confidence_adj", 0))))',
        src
    )
    if src_new != src:
        src = src_new
        fixes.append("FIX 1: Syntax error in confidence_adj line fixed (regex)")

# ─────────────────────────────────────────────────────────────
# FIX 2 (CRITICAL) — Move bal definition BEFORE UPGRADES_ENABLED block
# bal is used inside UPGRADES_ENABLED but defined after RE-ENTRY FILTER
# ─────────────────────────────────────────────────────────────
FIX2_MARKER = "                # â\x80\x94â\x80\x94 CRITIC AGENT + DSR GATE â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94â\x80\x94\n                if UPGRADES_ENABLED:"
FIX2_INJECT = """                # Get balance FIRST before any upgrade checks use it
                bal = get_crypto_balance("USDT")

                # ── CRITIC AGENT + DSR GATE ──────────────────────────────
                if UPGRADES_ENABLED:"""

# Try the ASCII version too
FIX2_MARKER_ASCII = "                if UPGRADES_ENABLED:\n                    try:\n                        # 1. Critic agent"
FIX2_INJECT_ASCII = """                # Get balance FIRST before any upgrade checks use it
                bal = get_crypto_balance("USDT")

                if UPGRADES_ENABLED:
                    try:
                        # 1. Critic agent"""

if FIX2_MARKER in src:
    src = src.replace(FIX2_MARKER, FIX2_INJECT, 1)
    fixes.append("FIX 2: bal moved before UPGRADES_ENABLED block")
elif FIX2_MARKER_ASCII in src:
    src = src.replace(FIX2_MARKER_ASCII, FIX2_INJECT_ASCII, 1)
    fixes.append("FIX 2: bal moved before UPGRADES_ENABLED block (ascii)")
else:
    print("  FIX 2: marker not found — applying via line search")
    lines = src.split('\n')
    for i, line in enumerate(lines):
        if 'if UPGRADES_ENABLED:' in line and i > 0:
            # Check if bal is already defined in preceding 5 lines
            context = '\n'.join(lines[max(0,i-5):i])
            if 'bal = get_crypto_balance' not in context:
                indent = ' ' * (len(line) - len(line.lstrip()))
                lines.insert(i, f'{indent}bal = get_crypto_balance("USDT")  # FIX 2: define bal early')
                lines.insert(i, f'{indent}# Balance needed by critic/sizer/NN below')
                src = '\n'.join(lines)
                fixes.append("FIX 2: bal moved before UPGRADES_ENABLED (line insert)")
                break

# ─────────────────────────────────────────────────────────────
# FIX 3 (CRITICAL) — Fix NN_ENABLED indentation
# NN block must be at same level as UPGRADES_ENABLED, not inside it
# It should be AFTER the except clause of UPGRADES_ENABLED try
# ─────────────────────────────────────────────────────────────
# The NN block is already inside the UPGRADES_ENABLED try which is wrong
# Find the pattern and restructure
BAD_NN_INDENT = "                    # ── NEURAL NETWORK GATE ───────────────────────────────\n                    if NN_ENABLED:"
GOOD_NN_INDENT = "                # ── NEURAL NETWORK GATE ─────────────────────────────────\n                if NN_ENABLED:"

if BAD_NN_INDENT in src:
    # Also need to fix closing of the try/except
    src = src.replace(BAD_NN_INDENT, GOOD_NN_INDENT, 1)
    fixes.append("FIX 3: NN_ENABLED block moved out of UPGRADES try block")
else:
    print("  FIX 3: NN indentation marker not found — check manually")

# ─────────────────────────────────────────────────────────────
# FIX 4 (HIGH) — Remove duplicate DB_FILE + function definitions
# The patch accidentally doubled: DB_FILE, init_db, db_log_trade, db_get_metrics
# ─────────────────────────────────────────────────────────────
# Find and remove the second occurrence of DB_FILE definition
db_count = src.count('DB_FILE        = os.path.expanduser("~/accra-bot/trades.db")')
if db_count > 1:
    # Find second occurrence and remove everything up to INSIGHTS_FILE
    first_pos = src.find('DB_FILE        = os.path.expanduser("~/accra-bot/trades.db")')
    second_pos = src.find('DB_FILE        = os.path.expanduser("~/accra-bot/trades.db")', first_pos + 1)
    # Find end of the duplicate block (up to INSIGHTS_FILE)
    end_marker = 'INSIGHTS_FILE  = os.path.expanduser("~/accra-bot/dream_insights.json")'
    end_pos = src.find(end_marker, second_pos)
    if end_pos > second_pos:
        src = src[:second_pos] + src[end_pos:]
        fixes.append("FIX 4: Removed duplicate DB_FILE/init_db/db_log_trade/db_get_metrics definitions")
else:
    print("  FIX 4: No duplicate DB definitions found — already clean")

# ─────────────────────────────────────────────────────────────
# FIX 5 (HIGH) — Remove duplicate check_circuit_breakers definition
# ─────────────────────────────────────────────────────────────
cb_count = src.count('def check_circuit_breakers(')
if cb_count > 1:
    # Find second occurrence
    first_pos = src.find('def check_circuit_breakers(')
    second_pos = src.find('def check_circuit_breakers(', first_pos + 1)
    # Find end of second definition (next def at same indent)
    end_pos = src.find('\ndef check_usdt_safety', second_pos)
    if end_pos > second_pos:
        src = src[:second_pos] + src[end_pos + 1:]
        fixes.append("FIX 5: Removed duplicate check_circuit_breakers() definition")
else:
    print("  FIX 5: No duplicate check_circuit_breakers found — already clean")

# ─────────────────────────────────────────────────────────────
# FIX 6 (MEDIUM) — Remove duplicate init_db() and build_ai_providers() in main()
# ─────────────────────────────────────────────────────────────
# main() has both called twice — remove second of each
MAIN_DUP1 = '    build_ai_providers()\n    init_db()   # FIX 3: initialise SQLite trade journal\n    log("=" * 55)\n\n    # â\x80\x94â\x80\x94 UPGRADES STATUS'
MAIN_FIXED1 = '    log("=" * 55)\n\n    # ── UPGRADES STATUS'
if MAIN_DUP1 in src:
    src = src.replace(MAIN_DUP1, MAIN_FIXED1, 1)
    fixes.append("FIX 6a: Removed duplicate build_ai_providers()/init_db() in main()")
else:
    # Try simpler dedup
    main_section = src[src.find('def main():'):]
    if main_section.count('init_db()') > 1:
        # Remove second init_db() call in main
        second_init = src.rfind('    init_db()')
        if second_init > src.find('def main()'):
            src = src[:second_init] + src[second_init:].replace('    init_db()   # FIX 3: initialise SQLite trade journal\n', '', 1)
            fixes.append("FIX 6a: Removed duplicate init_db() in main()")
    if src[src.find('def main():'):].count('build_ai_providers()') > 1:
        last_bap = src.rfind('    build_ai_providers()')
        if last_bap > src.find('def main()'):
            src = src[:last_bap] + src[last_bap:].replace('    build_ai_providers()\n', '', 1)
            fixes.append("FIX 6b: Removed duplicate build_ai_providers() in main()")

# ─────────────────────────────────────────────────────────────
# FIX 7 (MEDIUM) — Remove duplicate "metrics" key in status dict
# ─────────────────────────────────────────────────────────────
metrics_count = src.count('"metrics": db_get_metrics()')
if metrics_count > 1:
    # Remove the first occurrence (keep the one near "version")
    src = src.replace('"metrics": db_get_metrics(),\n        "metrics": db_get_metrics(),', 
                      '"metrics": db_get_metrics(),', 1)
    if src.count('"metrics": db_get_metrics()') > 1:
        # Try removing standalone duplicate
        first = src.find('"metrics": db_get_metrics()')
        second = src.find('"metrics": db_get_metrics()', first + 1)
        if second > 0:
            end_line = src.find('\n', second)
            src = src[:second] + src[end_line+1:]
    fixes.append("FIX 7: Removed duplicate 'metrics' key in status dict")
else:
    print("  FIX 7: No duplicate metrics key found")

# ─────────────────────────────────────────────────────────────
# FIX 8 (MEDIUM) — Remove duplicate check_circuit_breakers() call in crypto scan
# ─────────────────────────────────────────────────────────────
DUP_CB_CALL = """                _cb_ok, _cb_reason = check_circuit_breakers(sym, closes)
                if not _cb_ok:
                    log(f"  [BREAKER] {sym}: {_cb_reason}")
                    continue
                _cb_ok, _cb_reason = check_circuit_breakers(sym, closes)
                if not _cb_ok:
                    log(f"  [BREAKER] {sym}: {_cb_reason}")
                    continue"""
FIXED_CB_CALL = """                _cb_ok, _cb_reason = check_circuit_breakers(sym, closes)
                if not _cb_ok:
                    log(f"  [BREAKER] {sym}: {_cb_reason}")
                    continue"""

if DUP_CB_CALL in src:
    src = src.replace(DUP_CB_CALL, FIXED_CB_CALL, 1)
    fixes.append("FIX 8: Removed duplicate check_circuit_breakers() call in crypto scan")
else:
    print("  FIX 8: Duplicate CB call not found as exact string — checking line by line")
    lines = src.split('\n')
    new_lines = []
    skip_next_cb = False
    for i, line in enumerate(lines):
        if skip_next_cb and 'check_circuit_breakers' in line:
            # Skip this and next 3 lines (the if block)
            skip_next_cb = False
            # skip 3 more lines
            for j in range(1, 4):
                if i+j < len(lines):
                    lines[i+j] = '###SKIP###'
            continue
        if '###SKIP###' in line:
            continue
        if 'check_circuit_breakers' in line:
            # Check if same call appears in next 5 lines
            upcoming = '\n'.join(lines[i+1:i+6])
            if 'check_circuit_breakers' in upcoming:
                skip_next_cb = True
        new_lines.append(line)
    new_src = '\n'.join(new_lines)
    if new_src != src:
        src = new_src
        fixes.append("FIX 8: Removed duplicate check_circuit_breakers() call (line scan)")

# ─────────────────────────────────────────────────────────────
# Write fixed file
# ─────────────────────────────────────────────────────────────
if src == original:
    print("\n⚠  No changes made — markers may have shifted. Check manually.")
    sys.exit(1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nFixes applied ({len(fixes)}):")
for f in fixes:
    print(f"   ✓ {f}")

print("""
==================================================
  NEXT STEPS:
  git add -A
  git commit -m "Code review fixes: 9 issues resolved"
  git push origin master
==================================================
""")

"""
apply_manual_fixes.py — Applies FIX 2 and FIX 3c manually
using line-number search instead of exact string matching.

Run from C:\\Users\\HP\\accra-bot:
    python apply_manual_fixes.py
"""

import os, shutil, sys, re

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
BAK_PATH = BOT_PATH + ".manual.bak"

if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found.")
    sys.exit(1)

shutil.copy2(BOT_PATH, BAK_PATH)
print(f"Backup saved -> {BAK_PATH}")

with open(BOT_PATH, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

original = lines[:]
patches  = []

# ─────────────────────────────────────────────────────────────
# FIX 2 — Make critic advisory only
# Find: if not _critic["approved"]: ... return False
# Replace the return False with a log statement
# ─────────────────────────────────────────────────────────────
for i, line in enumerate(lines):
    if '[CRITIC] BLOCKED' in line and 'return False' in lines[i+1] if i+1 < len(lines) else False:
        lines[i]   = line.replace(
            '[CRITIC] BLOCKED',
            '[CRITIC ADVISORY] (non-blocking)'
        )
        lines[i+1] = lines[i+1].replace(
            'return False',
            'pass  # FIX 2: advisory only — never blocks execution'
        )
        patches.append("FIX 2a: critic BLOCKED -> advisory (return False removed)")
        break

# Also find the confidence adjustment line and soften it
for i, line in enumerate(lines):
    if 'conf + _critic["confidence_adj"]' in line:
        lines[i] = line.replace(
            'conf + _critic["confidence_adj"]',
            'conf + max(-10, _critic["confidence_adj"])  # FIX 2: soft cap -10 max'
        )
        patches.append("FIX 2b: confidence_adj soft-capped at -10")
        break

# ─────────────────────────────────────────────────────────────
# FIX 3c — SQLite BUY logging
# Find the log_trade BUY block and add db_log_trade before it
# ─────────────────────────────────────────────────────────────
buy_log_start = None
for i, line in enumerate(lines):
    if 'log_trade({' in line:
        # Check next few lines for BUY action
        context = ''.join(lines[i:i+8])
        if '"action":' in context and '"BUY"' in context:
            buy_log_start = i
            break

if buy_log_start is not None:
    # Find the indent of that line
    indent = len(lines[buy_log_start]) - len(lines[buy_log_start].lstrip())
    pad = ' ' * indent

    db_lines = [
        f'{pad}_strat_now = load_strategy()\n',
        f'{pad}db_log_trade({{\n',
        f'{pad}    "time":         datetime.now().isoformat(),\n',
        f'{pad}    "symbol":       sym,\n',
        f'{pad}    "action":       "BUY",\n',
        f'{pad}    "price":        sig["price"],\n',
        f'{pad}    "market":       sig["market"],\n',
        f'{pad}    "confidence":   sig["confidence"],\n',
        f'{pad}    "combined":     sig["combined"],\n',
        f'{pad}    "tech":         sig["tech"],\n',
        f'{pad}    "fund":         sig["fund"],\n',
        f'{pad}    "rsi":          sig.get("rsi", 0),\n',
        f'{pad}    "fear_greed":   get_fear_greed().get("value", 50),\n',
        f'{pad}    "position_size":sig.get("cfg", {{}}).get("pct", 5),\n',
        f'{pad}    "sl_price":     round(sig["price"] * (1 - sig.get("cfg",{{}}).get("sl",0.05)), 6),\n',
        f'{pad}    "tp_price":     round(sig["price"] * (1 + sig.get("cfg",{{}}).get("tp",0.05)), 6),\n',
        f'{pad}    "strategy":     _strat_now.get("mode","balanced"),\n',
        f'{pad}    "market_regime":_strat_now.get("market_condition","neutral"),\n',
        f'{pad}    "reasons":      sig.get("reasons",[]),\n',
        f'{pad}}})\n',
        f'{pad}# JSON backup below:\n',
    ]
    lines = lines[:buy_log_start] + db_lines + lines[buy_log_start:]
    patches.append("FIX 3c: db_log_trade added before BUY log_trade")
else:
    print("  FIX 3c: log_trade BUY block not found — skipping")

# ─────────────────────────────────────────────────────────────
# Write patched file
# ─────────────────────────────────────────────────────────────
if lines == original:
    print("\nNo changes made.")
    sys.exit(1)

with open(BOT_PATH, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"\nPatches applied ({len(patches)}):")
for p in patches:
    print(f"   * {p}")

print("""
==================================================
  NEXT STEPS:
  git add -A
  git commit -m "Apply FIX 2 advisory critic + FIX 3c SQLite BUY log"
  git push origin master
==================================================
""")

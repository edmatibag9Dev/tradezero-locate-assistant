import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import rules

CFG = {"auto_reject_at_per_share": 0.20, "warn_at_per_share": 0.10}

CASES = [
    # (rate, expected_action, expected_warn)
    (0.0045, rules.ASK, False),   # sub-penny -> ask (Ed's option 1)
    (0.01,   rules.ASK, False),
    (0.05,   rules.ASK, False),
    (0.0999, rules.ASK, False),
    (0.10,   rules.ASK, True),    # Rob's warning band starts
    (0.1999, rules.ASK, True),    # top of the ask band
    (0.20,   rules.AUTO_REJECT, False),  # boundary: .20 exactly is rejected
    (0.35,   rules.AUTO_REJECT, False),
    (1.50,   rules.AUTO_REJECT, False),  # EDHL-style $150-on-100-shares locate
]

failures = 0
for rate, action, warn in CASES:
    got = rules.evaluate(rate, CFG)
    ok = got["action"] == action and got["warn"] == warn
    print(f"{'PASS' if ok else 'FAIL'}  rate=${rate:<7} -> {got['action']:<11} warn={got['warn']}")
    failures += 0 if ok else 1

print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
sys.exit(1 if failures else 0)

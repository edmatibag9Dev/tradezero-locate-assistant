"""Locate approval rules.

Ed's rule set (2026-08-10):
  - rate >= auto_reject_at ($0.20/share): auto-reject, never opens an accept window
  - rate <  auto_reject_at: ask for approval (includes sub-penny locates)
  - rate >= warn_at ($0.10/share): still asks, but with a spoken warning
    (Rob Booker's "10c+ borrow is a warning signal" rule)
"""

AUTO_REJECT = "AUTO_REJECT"
ASK = "ASK"


def evaluate(rate_per_share: float, rules_cfg: dict) -> dict:
    auto_reject_at = rules_cfg["auto_reject_at_per_share"]
    warn_at = rules_cfg["warn_at_per_share"]

    if rate_per_share >= auto_reject_at:
        return {"action": AUTO_REJECT, "warn": False}
    return {"action": ASK, "warn": rate_per_share >= warn_at}

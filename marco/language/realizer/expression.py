"""Expression Selector: which declared (or learned) way of saying a frame fits here.

Candidates come from the language file (``expressions``, and ``rules`` for a
rule id) and from learned candidates. A candidate is usable when the roles it
requires are present and its conditions hold: polarity, register, the act it
serves. Learned candidates are tried first in the register they were observed
in; declared candidates follow in declared order, so the last declared one is
the plainest fallback. The semantic check decides; selection only orders.
"""


def _usable(candidate, prop, *, register, intent):
    roles = prop.get("roles", {})
    if any(role not in roles for role in candidate.get("requires", [])):
        return False
    when = candidate.get("when", {})
    if "polarity" in when and when["polarity"] != prop.get("polarity", True):
        return False
    if "intent" in when and intent not in when["intent"]:
        return False
    registers = candidate.get("register")
    if registers and register not in registers:
        return False
    return True


def candidates(decl, prop, *, register, intent, learned=()):
    frame = prop["frame"]
    if frame == "rule":
        rule = (prop["roles"].get("rule") or {}).get("id")
        parts = decl.get("rules", {}).get(rule)
        return [{"id": "rule", "parts": parts}] if parts else []
    declared = decl.get("expressions", {}).get(frame, [])
    own = [c for c in learned if c.get("frame") == frame and c.get("enabled", True)]
    ordered = own + list(declared)
    return [c for c in ordered if _usable(c, prop, register=register, intent=intent)]

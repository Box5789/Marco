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


def candidates(decl, prop, *, register, intent, learned=(), prefer=None):
    """Usable candidates in order. A learned candidate is not used for an answer
    fragment: the answer keeps the declared expressions and their ellipsis.
    ``prefer`` puts one candidate first (the one a coordinated clause already used)."""
    from marco.language.realizer.packs import meaning_declarations
    select = meaning_declarations()["frames"].get(prop["frame"], {}).get("select_by")
    frame = prop["frame"]
    if select:
        chosen = (prop["roles"].get(select["role"]) or {}).get("id")
        parts = decl.get(select["table"], {}).get(chosen)
        return [{"id": chosen, "parts": parts}] if parts else []
    declared = decl.get("expressions", {}).get(frame, [])
    own = [c for c in learned if c.get("frame") == frame and c.get("enabled", True) and not prop.get("answer")]
    ordered = own + list(declared)
    if prefer is not None:
        ordered = [c for c in ordered if c.get("id") == prefer] + [c for c in ordered if c.get("id") != prefer]
    return [c for c in ordered if _usable(c, prop, register=register, intent=intent)]

"""Bounded, evidence-first concept candidates from saved action events.

This is intentionally a small overlay beside the Binary KG.  It generalises
only an observed action-program shape; it never asserts that a repeated action
causes some unobserved outcome.  Candidate application is an explicit derived
classification with the event records that support it.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


SCHEMA = "nai-experience-concepts-v1"


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix, value):
    return "%s:%s" % (prefix, hashlib.sha256(_key(value).encode("utf-8")).hexdigest()[:16])


def _shape(event, effects):
    """Variableise values but retain role wiring, condition and program shape."""
    program = event.get("program") or {}
    steps = []
    for step in program.get("steps") or []:
        row = {key: value for key, value in step.items() if key not in {"status", "value"}}
        # Constants in an action program are part of the behaviour.  Event
        # participant values are not; those are represented by role keys.
        steps.append(row)
    return {"roles": sorted((program.get("signature") or {}).get("open_roles", {}).values()),
            "role_slots": sorted((program.get("signature") or {}).get("role_slots", {}).values()),
            "fixed_values": sorted((program.get("signature") or {}).get("fixed_values", {}).items()),
            "polarity": event.get("polarity", True), "modality": event.get("modality", "asserted"),
            "conditions": [sorted((row or {}).get("triple", [])) for row in event.get("conditions") or []],
            "steps": steps,
            "effect_predicates": sorted({row[1] for row in effects if isinstance(row, list) and len(row) == 3})}


def _experience(record):
    event = record.get("event") or {}
    if (record.get("status") != "executed" or event.get("polarity", True) is not True
            or event.get("modality", "asserted") != "asserted" or not event.get("id")):
        return None
    shape = _shape(event, record.get("effects") or [])
    values = {key: value for key, value in (event.get("roles") or {}).items()
              if isinstance(value, str) and value}
    return {"event_id": event["id"], "action": event.get("action"), "shape": shape,
            "shape_id": _id("shape", shape), "value_fingerprint": _key(values),
            "record_fingerprint": _key({"roles": values, "source": (event.get("evidence") or {}).get("text")}),
            "definition_version": event.get("definition_version")}


class ExperienceConceptStore:
    def __init__(self, *, support_limit=32, candidate_limit=64, validation_limit=32):
        self.support_limit = support_limit
        self.candidate_limit = candidate_limit
        self.validation_limit = validation_limit
        self.candidates = []
        self.applications = []
        self.disabled_ids = set()
        self.complete = True
        self.reason = None

    def sync(self, records):
        """Recompute candidates from durable event records, never source text."""
        events = [row for row in (_experience(record) for record in records) if row is not None]
        by_shape = {}
        for row in events:
            by_shape.setdefault((row["action"], row["shape_id"]), []).append(row)
        candidates = []
        complete, reason = True, None
        for (action, shape_id), rows in sorted(by_shape.items(), key=lambda pair: _key(pair[0])):
            distinct = []
            seen = set()
            for row in rows:
                # Repeating the identical stored utterance is not a new
                # independent experience merely because it acquired a new
                # event id during the dialogue.
                marker = row["record_fingerprint"]
                if marker not in seen:
                    seen.add(marker); distinct.append(row)
            if len(distinct) < 3:
                continue
            if len(candidates) >= self.candidate_limit:
                complete, reason = False, "candidate_limit"; break
            training, validation = distinct[:3], distinct[3:self.validation_limit + 3]
            counterexamples = [row["event_id"] for row in events
                               if row["action"] == action and row["shape_id"] != shape_id]
            candidate_id = _id("concept", {"action": action, "shape": training[0]["shape"]})
            status = "candidate"
            if counterexamples:
                status = "inactive"
            elif validation:
                status = "active"
            if candidate_id in self.disabled_ids:
                status = "inactive"
            candidate = {"id": candidate_id,
                         "schema": SCHEMA, "structural_definition": deepcopy(training[0]["shape"]),
                         "scope": {"action": action, "definition_versions": sorted({row["definition_version"] for row in distinct})},
                         "evidence_event_ids": [row["event_id"] for row in training],
                         "support_event_ids": [row["event_id"] for row in validation],
                         "counterexample_event_ids": counterexamples[:self.support_limit],
                         "status": status,
                         "validation": {"matched_holdouts": len(validation),
                                        "counterexamples": len(counterexamples),
                                        "complete": len(validation) < self.validation_limit},
                         "limits": {"support": self.support_limit, "candidates": self.candidate_limit,
                                    "validation": self.validation_limit}}
            candidates.append(candidate)
        applications = []
        for candidate in candidates:
            if candidate["status"] != "active":
                continue
            training = set(candidate["evidence_event_ids"])
            for row in events:
                if (row["action"] == candidate["scope"]["action"]
                        and row["shape"] == candidate["structural_definition"]
                        and row["event_id"] not in training):
                    applications.append({"id": "application:%s:%s" % (candidate["id"], row["event_id"]),
                                         "candidate_id": candidate["id"], "event_id": row["event_id"],
                                         "conclusion": [row["event_id"], "instance_of", candidate["id"]],
                                         "derived_conclusion": [row["event_id"], "classified_by", candidate["id"]],
                                         "premise_event_ids": list(candidate["evidence_event_ids"]),
                                         "validation_event_ids": list(candidate["support_event_ids"]),
                                         "valid": True})
        self.candidates, self.applications = candidates, applications
        self.complete, self.reason = complete, reason
        return self.snapshot()

    def snapshot(self):
        return {"schema": SCHEMA, "candidates": deepcopy(self.candidates),
                "applications": deepcopy(self.applications), "complete": self.complete,
                "reason": self.reason, "disabled_ids": sorted(self.disabled_ids),
                "limits": {"support": self.support_limit, "candidates": self.candidate_limit,
                           "validation": self.validation_limit}}

    def restore(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA:
            raise ValueError("invalid_experience_concept_snapshot")
        if not isinstance(snapshot.get("candidates"), list) or not isinstance(snapshot.get("applications"), list):
            raise ValueError("invalid_experience_concept_snapshot")
        self.candidates = deepcopy(snapshot["candidates"])
        self.applications = deepcopy(snapshot["applications"])
        disabled = snapshot.get("disabled_ids", [])
        if not isinstance(disabled, list) or any(not isinstance(value, str) for value in disabled):
            raise ValueError("invalid_experience_concept_snapshot")
        self.disabled_ids = set(disabled)
        self.complete = bool(snapshot.get("complete", True)); self.reason = snapshot.get("reason")

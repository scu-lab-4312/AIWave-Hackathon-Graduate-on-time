"""Session-scoped, agent-neutral user profile.

The orchestrator remembers a small set of *user-level* entities (where the user
is, whether they need a wheelchair, how to reach them) so that switching between
specialist agents feels like talking to one assistant with continuous memory
instead of three agents that each start from a blank slate.

This is intentionally separate from per-task ``known_facts``: task state
(selected driver, quote, booking, issue type...) stays isolated per agent, while
these shared entities are the only things allowed to cross agent boundaries.
"""

# Agent-neutral entity keys the assistant carries for the whole session.
CANONICAL_KEYS = ("city", "district", "special_needs", "contact_name", "contact_phone")

# Reserved profile keys (underscore-prefixed) hold session context rather than
# user entities. They are never seeded into a specialist's known_facts.
LAST_AGENT_KEY = "_last_agent"
# Ordered list of not-yet-run steps for a multi-service plan (see routing.plan_steps).
PENDING_PLAN_KEY = "_pending_plan"

# User-facing labels for each specialist, used when the orchestrator needs to
# refer back to a service the user was in the middle of.
SERVICE_LABELS = {
    "taxi-agent": "接送預約",
    "repair-agent": "居家修繕",
    "medical-agent": "藥局查詢",
}


def service_label(agent: str | None) -> str:
    """Human label for a specialist agent (falls back to a neutral term)."""
    return SERVICE_LABELS.get(agent or "", "服務")


def remember_last_agent(profile: dict, agent: str | None) -> dict:
    """Record the most recent specialist the user engaged, for recovery copy."""
    if not agent:
        return profile
    updated = dict(profile)
    updated[LAST_AGENT_KEY] = agent
    return updated


def last_agent(profile: dict) -> str | None:
    value = profile.get(LAST_AGENT_KEY)
    return value if isinstance(value, str) and value else None


def set_pending_plan(profile: dict, steps: list[dict]) -> dict:
    """Store the remaining steps of a multi-service plan (or clear when empty)."""
    updated = dict(profile)
    if steps:
        updated[PENDING_PLAN_KEY] = [dict(step) for step in steps]
    else:
        updated.pop(PENDING_PLAN_KEY, None)
    return updated


def pending_plan(profile: dict) -> list[dict]:
    """The not-yet-run steps of the current plan ([] when there is none)."""
    value = profile.get(PENDING_PLAN_KEY)
    return [dict(step) for step in value] if isinstance(value, list) else []


def pop_next_step(profile: dict) -> tuple[dict | None, dict]:
    """Return (next step, profile without it). (None, profile) when empty."""
    steps = pending_plan(profile)
    if not steps:
        return None, profile
    return steps[0], set_pending_plan(profile, steps[1:])


def clear_pending_plan(profile: dict) -> dict:
    """Drop any queued plan steps; a no-op when none are stored."""
    if PENDING_PLAN_KEY not in profile:
        return profile
    return set_pending_plan(profile, [])

# How each specialist names the facts that map onto the canonical entities.
# Generic aliases are listed before specific ones so the specific key wins when
# both are present (dict insertion order is preserved on iteration).
#   agent -> {specialist_fact_key: canonical_key}
_AGENT_TO_CANONICAL: dict[str, dict[str, str]] = {
    "taxi-agent": {
        "city": "city",
        "pickup_city": "city",
        "district": "district",
        "pickup_district": "district",
        "special_needs": "special_needs",
        "contact_name": "contact_name",
        "contact_phone": "contact_phone",
    },
    "repair-agent": {
        "city": "city",
        "district": "district",
        "contact_name": "contact_name",
        "contact_phone": "contact_phone",
    },
    "medical-agent": {
        "city": "city",
        "district": "district",
    },
}

# Canonical -> the fact key each specialist expects when we seed a fresh task.
# Built by reversing the map above; when several specialist keys share a
# canonical target, the last one wins (e.g. taxi seeds ``pickup_city``).
_CANONICAL_TO_AGENT: dict[str, dict[str, str]] = {
    agent: {canonical: fact_key for fact_key, canonical in mapping.items()}
    for agent, mapping in _AGENT_TO_CANONICAL.items()
}

_EMPTY = (None, "", [], {})


def extract_profile_updates(agent: str, known_facts: dict) -> dict:
    """Pull agent-neutral entities out of one specialist's ``known_facts``."""
    mapping = _AGENT_TO_CANONICAL.get(agent, {})
    updates: dict[str, object] = {}
    for fact_key, canonical in mapping.items():
        value = known_facts.get(fact_key)
        if value not in _EMPTY:
            updates[canonical] = value
    return updates


def merge_profile(profile: dict, agent: str, known_facts: dict) -> dict:
    """Return ``profile`` updated with any shared entities the agent just learned."""
    merged = dict(profile)
    merged.update(extract_profile_updates(agent, known_facts))
    return merged


def seed_task_facts(agent: str, profile: dict) -> dict:
    """Translate remembered entities into the fact keys ``agent`` expects.

    This is what makes a domain switch feel seamless: a fresh task for a new
    agent starts already knowing the user's location / needs, so the agent does
    not ask for them again.
    """
    mapping = _CANONICAL_TO_AGENT.get(agent, {})
    seeded: dict[str, object] = {}
    for canonical, fact_key in mapping.items():
        value = profile.get(canonical)
        if value not in _EMPTY:
            seeded[fact_key] = value
    return seeded

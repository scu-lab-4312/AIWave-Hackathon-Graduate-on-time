"""Best-effort points feedback for completed specialist services (Option A).

This is a *display-only* integration with the teammate's stateless points API
(`POST /points/reward`). The API maps a service scenario to a fixed number of
points and returns which demo products that amount could redeem. It does not
track identity or accumulate a balance, so we never fail a real service turn
just because the points lookup was unavailable: any error is swallowed and the
service response is returned untouched.

Privacy: only the coarse ``scenario`` label crosses the boundary here. No task
facts, message text, or medical detail is ever sent to the points API.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request


logger = logging.getLogger("orchestrator.rewards")

DEFAULT_POINTS_API_URL = (
    "https://q08q1hqlvi.execute-api.us-east-1.amazonaws.com/dev/points/reward"
)

# Set REWARD_POINTS_ENABLED=false to skip the live lookup entirely (used by the
# offline test suite, or to disable the integration without a code change).

# Which points scenario each specialist maps to. Agents not listed here simply
# earn no points (e.g. platform help, unsupported services).
AGENT_TO_SCENARIO = {
    "medical-agent": "medicine",
    "taxi-agent": "transport",
    "repair-agent": "repair",
}

# Socket timeout for the HTTP call itself. Note this does NOT bound DNS
# resolution, so it cannot be the only safeguard (see the hard deadline below).
_REQUEST_TIMEOUT_SECONDS = 2.0

# Absolute wall-clock cap on how long a completed turn may wait for rewards.
# The lookup runs in a daemon thread; if it has not finished by this deadline we
# abandon it and return the turn immediately. This is what makes a DNS/connect
# stall (which the socket timeout above cannot bound) unable to slow a turn.
_HARD_DEADLINE_SECONDS = 2.5

# Circuit breaker: after this many consecutive failures, skip the lookup
# entirely for a cooldown window instead of paying the deadline on every turn.
_FAILURE_THRESHOLD = 2
_COOLDOWN_SECONDS = 60.0

_breaker_lock = threading.Lock()
_consecutive_failures = 0
_disabled_until = 0.0  # time.monotonic() deadline; 0 means the breaker is closed


def _points_api_url() -> str:
    return os.getenv("REWARD_POINTS_API_URL", DEFAULT_POINTS_API_URL).strip()


def _breaker_is_open() -> bool:
    """True while the breaker is tripped and lookups should be skipped."""
    with _breaker_lock:
        return time.monotonic() < _disabled_until


def _record_result(*, success: bool) -> None:
    """Update breaker state after an attempt; trip it on repeated failure."""
    global _consecutive_failures, _disabled_until
    with _breaker_lock:
        if success:
            _consecutive_failures = 0
            _disabled_until = 0.0
        else:
            _consecutive_failures += 1
            if _consecutive_failures >= _FAILURE_THRESHOLD:
                _disabled_until = time.monotonic() + _COOLDOWN_SECONDS


def _reset_breaker() -> None:
    """Test helper: force the breaker back to a clean, closed state."""
    global _consecutive_failures, _disabled_until
    with _breaker_lock:
        _consecutive_failures = 0
        _disabled_until = 0.0


def _fetch_points(scenario: str, sink: list) -> None:
    """Blocking HTTP call, run inside a daemon thread; append payload on success.

    Any failure is swallowed here: the caller treats an empty ``sink`` (whether
    from an error or from the hard deadline elapsing) as "no reward this turn".
    """
    payload = json.dumps({"scenario": scenario}).encode("utf-8")
    request = urllib.request.Request(
        _points_api_url(),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        if isinstance(body, dict) and body.get("points_earned"):
            sink.append(body)
    except Exception:  # noqa: BLE001 - fire-and-forget worker must never raise
        logger.warning("Points lookup failed for scenario=%s", scenario, exc_info=True)


def award_service_points(target_agent: str) -> dict | None:
    """Look up the reward for a completed service; return None on any problem.

    The network call can never slow a turn by more than ``_HARD_DEADLINE_SECONDS``:
    it runs in a daemon thread we stop waiting on once the deadline elapses. A
    circuit breaker skips the call outright after repeated failures so a broken
    egress path does not cost every completed turn the full deadline.

    Returns the raw API payload (``scenario``, ``points_earned``,
    ``redeemable_products``) so callers can format a notice and/or forward the
    structured data to the frontend.
    """
    if os.getenv("REWARD_POINTS_ENABLED", "true").strip().lower() == "false":
        return None
    scenario = AGENT_TO_SCENARIO.get(target_agent)
    if not scenario:
        return None
    if _breaker_is_open():
        logger.debug("Points breaker open; skipping lookup for %s", target_agent)
        return None

    sink: list = []
    worker = threading.Thread(
        target=_fetch_points,
        args=(scenario, sink),
        name="reward-points-lookup",
        daemon=True,
    )
    worker.start()
    worker.join(_HARD_DEADLINE_SECONDS)

    reward = sink[0] if sink else None
    if reward is None and worker.is_alive():
        logger.warning(
            "Points lookup for %s exceeded %.1fs deadline; returning turn without reward",
            target_agent,
            _HARD_DEADLINE_SECONDS,
        )
    _record_result(success=reward is not None)
    return reward


def reward_notice(reward: dict | None) -> str:
    """Human-facing sentence to append after a completed service, or ''."""
    if not reward:
        return ""
    points = reward.get("points_earned")
    if not points:
        return ""
    products = [
        product
        for product in (reward.get("redeemable_products") or [])
        if isinstance(product, dict) and product.get("product_name")
    ]
    if products:
        listed = "、".join(
            f"{product['product_name']}（{product['points_required']} 點）"
            if product.get("points_required") is not None
            else str(product["product_name"])
            for product in products
        )
        return f"本次服務已為您累積 {points} 點回饋，目前可兌換：{listed}。"
    return f"本次服務已為您累積 {points} 點回饋。"


def append_reward_notice(message: str, reward: dict | None) -> str:
    """Append the reward sentence to a specialist message when one applies."""
    notice = reward_notice(reward)
    if not notice:
        return message
    return f"{message}\n\n{notice}"

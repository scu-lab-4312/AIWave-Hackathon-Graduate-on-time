"""Reliable routing and task-state orchestration for the home-service agent."""

import logging
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.context import RequestContext

from apps.orchestrator.prompts import static_reply
from apps.orchestrator.routing import classify_route
from apps.orchestrator.specialist_client import invoke_specialist
from apps.orchestrator.task_state import MEMORY_ID, build_state_agent, load_active_task, save_turn
from shared.contracts import ActiveTask, HandoffRequest, RouteAction, SpecialistResponse, TaskStatus
from shared.ids import new_task_id


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

MEDICAL_CITY_ALIASES = {
    "台北市": "台北市", "臺北市": "台北市", "台北": "台北市", "臺北": "台北市",
    "新北市": "新北市", "新北": "新北市",
    "台中市": "台中市", "臺中市": "台中市", "台中": "台中市", "臺中": "台中市",
}
MEDICAL_DISTRICT_AFTER_CITY = re.compile(r"([\u4e00-\u9fff]{1,4}(?:區|鄉|鎮|市))")
MEDICAL_DISTRICT_STANDALONE = re.compile(
    r"(?:^|[在於住、，,\s])([\u4e00-\u9fff]{1,3}(?:區|鄉|鎮|市))"
)


def _medical_handoff_input(message: str, known_facts: dict) -> tuple[str, dict]:
    """Allow only coarse location data to cross the Medical boundary."""
    safe_facts = {
        key: str(value)
        for key, value in known_facts.items()
        if key in {"city", "district"} and value
    }
    city_end: int | None = None
    for alias in sorted(MEDICAL_CITY_ALIASES, key=len, reverse=True):
        city_start = message.find(alias)
        if city_start >= 0:
            safe_facts["city"] = MEDICAL_CITY_ALIASES[alias]
            city_end = city_start + len(alias)
            break
    district_match = MEDICAL_DISTRICT_AFTER_CITY.search(message[city_end:]) if city_end else None
    if not district_match:
        district_match = MEDICAL_DISTRICT_STANDALONE.search(message)
    if district_match:
        safe_facts["district"] = district_match.group(1)
    location = "、".join(
        f"{label}={safe_facts[key]}"
        for key, label in (("city", "城市"), ("district", "行政區"))
        if key in safe_facts
    )
    return (f"只使用以下位置資料：{location}" if location else "尚未提供城市與行政區。"), safe_facts


def _next_known_facts(specialist: SpecialistResponse, fallback: dict) -> dict:
    """Persist structured specialist state needed for the next conversational turn."""
    facts = dict(specialist.data.get("known_facts") or fallback)
    for key in ("stage", "estimate", "provider_options", "booking", "pharmacy_options"):
        value = specialist.data.get(key)
        if value not in (None, [], {}):
            facts[key] = value
    return facts


def process_turn(prompt: str, session_id: str, actor_id: str) -> dict:
    """Route one turn, update sticky task state, and return a transparent result."""
    state_agent, manager = build_state_agent(session_id, actor_id)
    active_task = load_active_task(session_id, state_agent)
    routing = classify_route(prompt, active_task)
    specialist: SpecialistResponse | None = None
    specialist_backend: str | None = None

    if routing.action == RouteAction.CANCEL and active_task:
        active_task.status = TaskStatus.CANCELLED
        result = "已取消目前的服務任務。"
        active_task = None
    elif routing.action == RouteAction.DISPATCH:
        logger.info(
            "DISPATCH %s task=%s sticky=%s message_length=%s",
            routing.target_agent,
            routing.sticky_task_id or "new",
            bool(routing.sticky_task_id),
            len(prompt),
        )
        task_id = active_task.task_id if active_task else new_task_id()
        known_facts = active_task.known_facts if active_task else {}
        handoff_message = prompt
        if routing.target_agent == "medical-agent":
            handoff_message, known_facts = _medical_handoff_input(prompt, known_facts)
        handoff = HandoffRequest(
            task_id=task_id,
            actor_id=actor_id,
            conversation_id=session_id,
            intent=routing.sub_intent or "repair_unspecified",
            message=handoff_message,
            known_facts=known_facts,
            missing_fields=active_task.missing_fields if active_task else [],
            safety_alert=routing.safety_alert,
        )
        specialist, specialist_backend = invoke_specialist(routing.target_agent or "repair-agent", handoff)
        if specialist.status == TaskStatus.NEEDS_INPUT:
            next_facts = _next_known_facts(specialist, handoff.known_facts)
            if routing.target_agent == "medical-agent":
                next_facts = {
                    key: value for key, value in next_facts.items() if key in {"city", "district"}
                }
            active_task = ActiveTask(
                task_id=specialist.task_id,
                target_agent=routing.target_agent or specialist.agent,
                intent=handoff.intent,
                known_facts=next_facts,
                missing_fields=specialist.data.get("missing_fields", []),
            )
        else:
            active_task = None
        result = specialist.message
    elif routing.sticky_task_id and routing.action == RouteAction.CLARIFY:
        result = "目前還在處理原本的服務需求。你要先完成它，還是取消後建立新需求？"
    else:
        result = static_reply(routing.intent)

    memory_prompt = "[medical service request redacted]" if routing.intent.value == "medical" else prompt
    save_turn(session_id, memory_prompt, result, active_task, state_agent, manager)
    return {
        "result": result,
        "session_id": session_id,
        "memory_enabled": bool(MEMORY_ID),
        "routing": routing.model_dump(mode="json"),
        "specialist": specialist.model_dump(mode="json") if specialist else None,
        "specialist_backend": specialist_backend,
        "active_task": active_task.model_dump(mode="json") if active_task else None,
    }


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict, context: RequestContext) -> dict:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return {"result": "請提供 prompt 欄位，例如 {\"prompt\": \"我家水管在漏水\"}"}
    session_id = context.session_id or payload.get("session_id") or "default-session"
    actor_id = payload.get("actor_id") or "anonymous"
    return process_turn(prompt, session_id, actor_id)


if __name__ == "__main__":
    app.run()

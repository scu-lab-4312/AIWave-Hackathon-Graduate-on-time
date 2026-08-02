"""Reliable routing and task-state orchestration for the home-service agent."""

import logging
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.context import RequestContext

from apps.orchestrator.profile import (
    last_agent,
    merge_profile,
    remember_last_agent,
    seed_task_facts,
    service_label,
)
from apps.orchestrator.prompts import static_reply
from apps.orchestrator.routing import classify_route, looks_like_selection
from apps.orchestrator.specialist_client import invoke_specialist
from apps.orchestrator.task_state import (
    MEMORY_ID,
    build_state_agent,
    load_active_task,
    load_shared_profile,
    save_turn,
)
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
    if city_end is None:
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
    for key in (
        "stage", "estimate", "provider_options", "driver_options", "booking", "pharmacy_options"
    ):
        value = specialist.data.get(key)
        if value not in (None, [], {}):
            facts[key] = value
    return facts


def _fallback_reply(prompt: str, routing, shared_profile: dict) -> str:
    """Reply for turns we could not confidently route.

    A bare selection or short confirmation ("我要選第 1 位…") carries no keyword,
    so once its task is gone (booking completed, or the previous turn dropped mid
    flight) it would otherwise dead-end in a generic, context-blind message. When
    we still remember the last service the user was in, we acknowledge it so the
    experience stays continuous instead of feeling like the assistant forgot
    everything.
    """
    recent_agent = last_agent(shared_profile)
    if recent_agent and looks_like_selection(prompt):
        label = service_label(recent_agent)
        return (
            f"您先前的{label}目前沒有進行中的流程可以套用這個選擇了，"
            f"可能已完成或因連線中斷而中止。若您剛才已收到預約編號，代表預約已送出；"
            f"若沒有，我可以幫您重新開始{label}，要繼續嗎？"
        )
    if recent_agent and routing.intent.value == "unknown":
        label = service_label(recent_agent)
        return (
            f"我不太確定您這次的需求。您先前在使用{label}；"
            "需要的話我可以繼續協助接送、居家修繕，或依地區查詢藥局，請再說明一下。"
        )
    return static_reply(routing.intent)


def process_turn(prompt: str, session_id: str, actor_id: str) -> dict:
    """Route one turn, update sticky task state, and return a transparent result."""
    state_agent, manager = build_state_agent(session_id, actor_id)
    active_task = load_active_task(session_id, state_agent)
    shared_profile = load_shared_profile(session_id, state_agent)
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
        # 只有同一個專業 Agent 才延續舊任務；切換領域時開全新任務，避免舊任務的
        # task_id 與任務級 known_facts 洩漏到新的專業 Agent。但跨 Agent 的使用者實體
        # （所在地、特殊需求等）會從 shared_profile 帶入，讓使用者感覺是同一個助理，
        # 不必重複提供已經說過的資訊。
        is_continuation = active_task is not None and active_task.target_agent == routing.target_agent
        task_id = active_task.task_id if is_continuation else new_task_id()
        if is_continuation:
            known_facts = dict(active_task.known_facts)
        else:
            known_facts = seed_task_facts(routing.target_agent or "", shared_profile)
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
            missing_fields=active_task.missing_fields if is_continuation else [],
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
        # 把本輪學到的跨 Agent 使用者實體（地點、特殊需求等）併回 session profile，
        # 讓之後切換到別的專業 Agent 時能自動沿用。含 handoff.known_facts 是為了保留
        # medical 從訊息解析出的城市／行政區，即使 specialist 未回傳也不遺失。
        learned_facts = dict(handoff.known_facts)
        learned_facts.update(specialist.data.get("known_facts") or {})
        shared_profile = merge_profile(shared_profile, routing.target_agent or "", learned_facts)
        shared_profile = remember_last_agent(shared_profile, routing.target_agent)
        result = specialist.message
    elif routing.sticky_task_id and routing.action == RouteAction.CLARIFY:
        result = "目前還在處理原本的服務需求。你要先完成它，還是取消後建立新需求？"
    else:
        result = _fallback_reply(prompt, routing, shared_profile)

    memory_prompt = "[medical service request redacted]" if routing.intent.value == "medical" else prompt
    save_turn(session_id, memory_prompt, result, active_task, state_agent, manager, shared_profile)
    return {
        "result": result,
        "session_id": session_id,
        "memory_enabled": bool(MEMORY_ID),
        "shared_profile": shared_profile,
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

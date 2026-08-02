"""Reliable routing and task-state orchestration for the home-service agent."""

import logging
import re

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.context import RequestContext

from apps.orchestrator.profile import (
    clear_pending_plan,
    last_agent,
    merge_profile,
    pending_plan,
    pop_next_step,
    remember_last_agent,
    seed_task_facts,
    service_label,
    set_pending_plan,
)
from apps.orchestrator.prompts import static_reply
from apps.orchestrator.rewards import append_reward_notice, award_service_points
from apps.orchestrator.routing import classify_route, looks_like_selection, plan_steps
from apps.orchestrator.specialist_client import invoke_specialist
from apps.orchestrator.task_state import (
    MEMORY_ID,
    build_state_agent,
    load_active_task,
    load_shared_profile,
    save_turn,
)
from shared.contracts import (
    ActiveTask,
    HandoffRequest,
    IntentName,
    RouteAction,
    SpecialistResponse,
    TaskStatus,
)
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


def _chain_seed(prev_agent: str, prev: SpecialistResponse, next_agent: str) -> dict:
    """Facts to carry from a just-completed step into the next planned step.

    The only cross-step data we pass today is a taxi destination derived from the
    pharmacy the Medical step surfaced. This stays within the privacy boundary:
    a pharmacy's public name and address is not medical information.
    """
    if prev_agent == "medical-agent" and next_agent == "taxi-agent":
        options = prev.data.get("pharmacy_options") or []
        if options:
            first = options[0]
            name = first.get("name") or "指定藥局"
            address = first.get("address")
            return {"destination": f"{name}（{address}）" if address else name}
    return {}


def _chained_message(next_agent: str, seed: dict) -> str:
    """Synthesized instruction for a step the orchestrator starts on its own."""
    if next_agent == "taxi-agent":
        destination = seed.get("destination")
        return f"請協助安排前往「{destination}」的接送。" if destination else "請協助安排接送服務。"
    if next_agent == "repair-agent":
        return "請接續協助處理居家修繕需求。"
    if next_agent == "medical-agent":
        return "請協助查詢附近藥局的公開聯絡資訊。"
    return "請接續處理下一項服務。"


def process_turn(prompt: str, session_id: str, actor_id: str) -> dict:
    """Route one turn, update sticky task state, and return a transparent result."""
    state_agent, manager = build_state_agent(session_id, actor_id)
    active_task = load_active_task(session_id, state_agent)
    shared_profile = load_shared_profile(session_id, state_agent)
    routing = classify_route(prompt, active_task)
    specialist: SpecialistResponse | None = None
    specialist_backend: str | None = None
    reward: dict | None = None
    specialists: list[dict] = []

    if routing.action == RouteAction.CANCEL and active_task:
        active_task.status = TaskStatus.CANCELLED
        result = "已取消目前的服務任務。"
        active_task = None
        shared_profile = clear_pending_plan(shared_profile)
    elif routing.action == RouteAction.DISPATCH:
        # 只有同一個專業 Agent 才延續舊任務；切換領域時開全新任務，避免舊任務的
        # task_id 與任務級 known_facts 洩漏到新的專業 Agent。但跨 Agent 的使用者實體
        # （所在地、特殊需求等）會從 shared_profile 帶入，讓使用者感覺是同一個助理。
        is_continuation = active_task is not None and active_task.target_agent == routing.target_agent

        # 複合語句（一句話跨多個領域，如「搭車去拿藥」）在此建立循序計畫：第一步當本輪
        # 目標，其餘步驟排入待辦佇列。單一意圖的新訊息則清掉任何殘留計畫，避免沿用過期
        # 的待辦。延續中的任務不重建計畫，保留既有佇列。
        if not is_continuation:
            steps = plan_steps(prompt)
            if steps:
                first = steps[0]
                routing = routing.model_copy(
                    update={
                        "target_agent": first["target_agent"],
                        "intent": IntentName(first["intent"]),
                        "sub_intent": first["sub_intent"],
                        "safety_alert": None,
                        "reason": "偵測到跨多個服務的需求，建立循序計畫："
                        + " → ".join(step["target_agent"] for step in steps),
                    }
                )
                shared_profile = set_pending_plan(shared_profile, steps[1:])
            else:
                shared_profile = clear_pending_plan(shared_profile)

        logger.info(
            "DISPATCH %s task=%s sticky=%s message_length=%s plan_remaining=%s",
            routing.target_agent,
            routing.sticky_task_id or "new",
            bool(routing.sticky_task_id),
            len(prompt),
            len(pending_plan(shared_profile)),
        )

        messages: list[str] = []
        current_target = routing.target_agent or "repair-agent"
        current_sub_intent = routing.sub_intent or "repair_unspecified"
        current_message = prompt
        current_safety = routing.safety_alert
        chain_seed: dict = {}
        # 迴圈上限：本步 + 待辦佇列步數，避免任何意外的無限串接。
        max_steps = 1 + len(pending_plan(shared_profile))

        for step_index in range(max_steps):
            # 只有「本輪第一步」才可能是延續舊任務；被串接起來的後續步驟一律開新任務。
            continuation = is_continuation and step_index == 0
            task_id = active_task.task_id if continuation else new_task_id()
            if continuation:
                step_facts = dict(active_task.known_facts)
            else:
                step_facts = seed_task_facts(current_target, shared_profile)
                step_facts.update(chain_seed)

            handoff_message = current_message
            if current_target == "medical-agent":
                handoff_message, step_facts = _medical_handoff_input(current_message, step_facts)

            handoff = HandoffRequest(
                task_id=task_id,
                actor_id=actor_id,
                conversation_id=session_id,
                intent=current_sub_intent,
                message=handoff_message,
                known_facts=step_facts,
                missing_fields=active_task.missing_fields if continuation else [],
                safety_alert=current_safety,
            )
            specialist, specialist_backend = invoke_specialist(current_target, handoff)
            specialists.append(specialist.model_dump(mode="json"))

            # 把本步學到的跨 Agent 使用者實體併回 session profile。含 handoff.known_facts
            # 是為了保留 medical 從訊息解析出的城市／行政區，即使 specialist 未回傳也不遺失。
            learned_facts = dict(handoff.known_facts)
            learned_facts.update(specialist.data.get("known_facts") or {})
            shared_profile = merge_profile(shared_profile, current_target, learned_facts)
            shared_profile = remember_last_agent(shared_profile, current_target)

            step_message = specialist.message

            if specialist.status == TaskStatus.NEEDS_INPUT:
                # 本步還需要更多資訊：暫停計畫，待辦佇列原封保留到下一輪延續。
                next_facts = _next_known_facts(specialist, handoff.known_facts)
                if current_target == "medical-agent":
                    next_facts = {
                        key: value for key, value in next_facts.items() if key in {"city", "district"}
                    }
                active_task = ActiveTask(
                    task_id=specialist.task_id,
                    target_agent=current_target,
                    intent=current_sub_intent,
                    known_facts=next_facts,
                    missing_fields=specialist.data.get("missing_fields", []),
                )
                messages.append(step_message)
                break

            # 非 needs_input：本步結束（completed / failed / cancelled）。
            active_task = None
            # 只有服務真正完成才發點；查點是 best-effort，查不到就靜默略過。
            if specialist.status == TaskStatus.COMPLETED:
                step_reward = award_service_points(current_target)
                if step_reward:
                    reward = step_reward
                    step_message = append_reward_notice(step_message, step_reward)
            messages.append(step_message)

            next_step, shared_profile = pop_next_step(shared_profile)
            if next_step is None:
                break
            if specialist.status != TaskStatus.COMPLETED:
                # 前一步沒有成功完成，無法可靠串接後續（例如拿不到藥局地址當目的地）。
                # 停止計畫並說明，讓使用者能自行接續。
                shared_profile = clear_pending_plan(shared_profile)
                messages.append(
                    f"後續的{service_label(next_step['target_agent'])}我先暫停了，"
                    "稍後可以再試，或直接告訴我需要的資訊。"
                )
                break

            # 串接下一步：帶入本步產出的資料（如藥局地址→接送目的地）。
            chain_seed = _chain_seed(current_target, specialist, next_step["target_agent"])
            current_target = next_step["target_agent"]
            current_sub_intent = next_step["sub_intent"]
            current_message = _chained_message(current_target, chain_seed)
            current_safety = None

        result = "\n\n".join(message for message in messages if message)
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
        "specialists": specialists,
        "specialist_backend": specialist_backend,
        "active_task": active_task.model_dump(mode="json") if active_task else None,
        "reward": reward,
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

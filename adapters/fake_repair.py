"""Deterministic fake Repair Agent used to validate the handoff contract."""

import uuid

from adapters.base import SpecialistClient
from shared.contracts import ActiveTask, HandoffRequest, SpecialistResponse, TaskStatus


LOCATIONS = ("廚房", "浴室", "廁所", "客廳", "房間", "陽台", "屋頂", "地下室")


def _extract_initial_facts(message: str, intent: str) -> dict[str, object]:
    facts: dict[str, object] = {"original_request": message}
    for location in LOCATIONS:
        if location in message:
            facts["location"] = location
            break
    if "已經關" in message or "已關" in message:
        facts["safety_action_taken"] = True
    if intent == "plumbing_leak":
        for rate in ("每秒一滴", "一直滴", "大量", "一直噴", "慢慢滴"):
            if rate in message:
                facts["leak_rate"] = rate
                break
    return facts


def _required_fields(intent: str) -> list[str]:
    return {
        "plumbing_leak": ["location", "leak_rate"],
        "plumbing_clog": ["location", "overflow_status"],
        "electrical_power": ["location", "power_scope"],
        "electrical_light": ["location", "power_scope"],
        "repair_unspecified": ["issue_detail", "location"],
    }.get(intent, ["issue_detail", "location"])


def _question_for(field: str) -> str:
    return {
        "location": "問題發生在家中的哪個位置？",
        "leak_rate": "漏水速度大約多快，例如慢慢滴、每秒一滴，還是持續流出？",
        "overflow_status": "目前有沒有溢水，或水位持續上升？",
        "power_scope": "目前是只有單一設備異常，還是整個空間都沒有電？",
        "issue_detail": "請再描述具體狀況，例如漏水、堵塞、跳電或燈具不亮。",
    }[field]


def _apply_follow_up(task: ActiveTask, message: str) -> None:
    if not task.missing_fields:
        return
    field = task.missing_fields[0]
    task.known_facts[field] = message.strip()


def handle_repair(
    message: str,
    intent: str,
    active_task: ActiveTask | None,
    safety_alert: str | None,
    task_id: str | None = None,
) -> tuple[SpecialistResponse, ActiveTask | None]:
    """Process one specialist turn and return its user response and next task state."""
    if active_task:
        task = active_task.model_copy(deep=True)
        _apply_follow_up(task, message)
    else:
        task = ActiveTask(
            task_id=task_id or str(uuid.uuid4()),
            intent=intent,
            known_facts=_extract_initial_facts(message, intent),
        )

    task.missing_fields = [field for field in _required_fields(task.intent) if field not in task.known_facts]
    if task.missing_fields:
        task.status = TaskStatus.NEEDS_INPUT
        question = _question_for(task.missing_fields[0])
        prefix = ""
        if safety_alert == "electrical_danger":
            prefix = "請先不要觸碰設備；若安全可行，關閉對應電源並遠離冒煙或火花處。"
        elif safety_alert == "shut_off_water":
            prefix = "若安全可行，請先關閉總水閥並避開積水區域。"
        response = SpecialistResponse(
            task_id=task.task_id,
            status=TaskStatus.NEEDS_INPUT,
            message=f"{prefix}{question}",
            data={"known_facts": task.known_facts, "missing_fields": task.missing_fields},
        )
        return response, task

    task.status = TaskStatus.COMPLETED
    response = SpecialistResponse(
        task_id=task.task_id,
        status=TaskStatus.COMPLETED,
        message="修繕專員已完成初步問題辨識；必要資訊已收齊，下一步可以接師傅媒合服務。",
        data={
            "issue_type": task.intent,
            "known_facts": task.known_facts,
            "ready_for_matching": True,
        },
    )
    return response, None


class FakeRepairClient(SpecialistClient):
    """Contract-compatible fallback; never performs external side effects."""

    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        active_task = None
        if request.known_facts or request.missing_fields:
            active_task = ActiveTask(
                task_id=request.task_id,
                intent=request.intent,
                known_facts=request.known_facts,
                missing_fields=request.missing_fields,
            )
        response, _ = handle_repair(
            message=request.message,
            intent=request.intent,
            active_task=active_task,
            safety_alert=request.safety_alert,
            task_id=request.task_id,
        )
        return response

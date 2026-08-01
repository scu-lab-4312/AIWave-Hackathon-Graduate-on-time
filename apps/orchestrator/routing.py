"""Small, deterministic routing policy for the hackathon scope."""

from shared.contracts import ActiveTask, IntentName, RouteAction, RoutingDecision, TaskStatus


REPAIR_KEYWORDS = {
    "漏水", "爆管", "淹水", "水管", "水龍頭", "馬桶", "堵塞", "阻塞", "排水",
    "插座", "電線", "電路", "跳電", "斷電", "沒電", "燈具", "燈泡", "不亮", "水電",
}
MEDICAL_KEYWORDS = {
    "領藥", "拿藥", "取藥", "備藥", "領取", "藥局", "藥師",
    "處方", "處方箋", "處方籤", "處方簽", "慢箋", "慢性處方",
}
TAXI_KEYWORDS = {
    "叫車", "計程車", "搭車", "預約車", "接送", "接我", "載我",
    "復康巴士", "無障礙車", "輪椅車", "就醫專車", "uber", "Uber",
}
UNSUPPORTED_KEYWORDS = {"搬家", "清潔", "打掃", "洗衣", "除蟲", "冷氣清洗", "家事服務"}
PLATFORM_KEYWORDS = {"怎麼使用", "如何使用", "怎麼用", "收費", "平台", "支援什麼", "服務範圍"}
CANCEL_KEYWORDS = {"取消", "不用了", "先不要", "停止處理"}
NEW_TASK_MARKERS = {"另外", "還有一個", "另一個問題", "順便"}


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _repair_sub_intent(text: str) -> str:
    if _contains_any(text, {"漏水", "爆管", "淹水", "水管", "水龍頭"}):
        return "plumbing_leak"
    if _contains_any(text, {"馬桶", "堵塞", "阻塞", "排水"}):
        return "plumbing_clog"
    if _contains_any(text, {"插座", "電線", "電路", "跳電", "斷電", "沒電"}):
        return "electrical_power"
    if _contains_any(text, {"燈具", "燈泡", "不亮"}):
        return "electrical_light"
    return "repair_unspecified"


def _safety_alert(text: str) -> str | None:
    if _contains_any(text, {"冒煙", "火花", "燒焦", "觸電", "起火"}):
        return "electrical_danger"
    if _contains_any(text, {"爆管", "淹水", "大量漏水", "一直噴"}):
        return "shut_off_water"
    return None


def classify_route(message: str, active_task: ActiveTask | None = None) -> RoutingDecision:
    text = message.strip()

    if active_task and active_task.status == TaskStatus.NEEDS_INPUT:
        active_intent = {
            "medical-agent": IntentName.MEDICAL,
            "taxi-agent": IntentName.TAXI,
            "repair-agent": IntentName.REPAIR,
        }.get(active_task.target_agent, IntentName.UNKNOWN)
        if _contains_any(text, CANCEL_KEYWORDS):
            return RoutingDecision(
                intent=active_intent,
                sub_intent=active_task.intent,
                confidence=1,
                target_agent=active_task.target_agent,
                action=RouteAction.CANCEL,
                reason="使用者明確取消目前任務",
                sticky_task_id=active_task.task_id,
            )
        if _contains_any(text, NEW_TASK_MARKERS):
            return RoutingDecision(
                intent=IntentName.UNKNOWN,
                confidence=0.6,
                action=RouteAction.CLARIFY,
                needs_clarification=True,
                reason="目前已有進行中的任務，偵測到可能的新需求",
                sticky_task_id=active_task.task_id,
            )
        return RoutingDecision(
            intent=active_intent,
            sub_intent=active_task.intent,
            confidence=1,
            target_agent=active_task.target_agent,
            action=RouteAction.DISPATCH,
            safety_alert=_safety_alert(text) if active_intent == IntentName.REPAIR else None,
            reason="延續目前進行中的專業任務",
            sticky_task_id=active_task.task_id,
        )

    if _contains_any(text, TAXI_KEYWORDS):
        return RoutingDecision(
            intent=IntentName.TAXI,
            sub_intent="accessible_ride",
            confidence=0.97,
            target_agent="taxi-agent",
            action=RouteAction.DISPATCH,
            reason="訊息包含叫車、接送或無障礙乘車需求",
        )
    if _contains_any(text, MEDICAL_KEYWORDS):
        return RoutingDecision(
            intent=IntentName.MEDICAL,
            sub_intent="pharmacist_contact",
            confidence=0.97,
            target_agent="medical-agent",
            action=RouteAction.DISPATCH,
            reason="訊息包含找藥局或藥師聯絡方式的需求",
        )
    if _contains_any(text, REPAIR_KEYWORDS):
        return RoutingDecision(
            intent=IntentName.REPAIR,
            sub_intent=_repair_sub_intent(text),
            confidence=0.95,
            target_agent="repair-agent",
            action=RouteAction.DISPATCH,
            safety_alert=_safety_alert(text),
            reason="訊息包含支援範圍內的居家水電問題",
        )
    if _contains_any(text, UNSUPPORTED_KEYWORDS):
        return RoutingDecision(
            intent=IntentName.UNSUPPORTED_SERVICE,
            confidence=0.98,
            action=RouteAction.REPLY,
            reason="訊息屬於目前未支援的居家服務",
        )
    if _contains_any(text, PLATFORM_KEYWORDS) or text in {"你好", "嗨", "哈囉", "hello", "hi"}:
        return RoutingDecision(
            intent=IntentName.PLATFORM_HELP,
            confidence=0.9,
            action=RouteAction.REPLY,
            reason="訊息是平台使用問題或一般招呼",
        )
    return RoutingDecision(
        intent=IntentName.UNKNOWN,
        confidence=0.35,
        action=RouteAction.CLARIFY,
        needs_clarification=True,
        reason="資訊不足，無法可靠判斷需求",
    )

"""User-facing orchestration copy; domain advice belongs to specialists."""

from shared.contracts import IntentName


def static_reply(intent: IntentName) -> str:
    if intent == IntentName.PLATFORM_HELP:
        return "你好！目前平台支援居家水電修繕；直接描述問題，我會轉交修繕專員協助。"
    if intent == IntentName.UNSUPPORTED_SERVICE:
        return "目前僅支援居家水電修繕，清潔、搬家等服務尚未開放。"
    return "我還無法確定你的需求。請描述是漏水、馬桶、水管、電路、插座或燈具問題。"

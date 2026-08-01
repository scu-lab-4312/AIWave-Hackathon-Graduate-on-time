"""User-facing orchestration copy; domain advice belongs to specialists."""

from shared.contracts import IntentName


def static_reply(intent: IntentName) -> str:
    if intent == IntentName.PLATFORM_HELP:
        return "你好！目前平台支援居家水電修繕，以及依地區尋找藥局藥師 LINE；不需提供任何醫療資訊。"
    if intent == IntentName.UNSUPPORTED_SERVICE:
        return "目前支援居家水電修繕，以及依地區尋找藥局藥師 LINE；清潔、搬家等服務尚未開放。"
    return "我還無法確定需求。你可以描述居家修繕問題，或告訴我想在哪個城市、行政區找藥師。"

"""User-facing orchestration copy; domain advice belongs to specialists."""

from shared.contracts import IntentName


def static_reply(intent: IntentName) -> str:
    if intent == IntentName.PLATFORM_HELP:
        return "你好！目前平台支援居家水電修繕、依地區尋找藥局聯絡電話，以及預約接送車輛。"
    if intent == IntentName.UNSUPPORTED_SERVICE:
        return "目前支援居家水電修繕、依地區尋找藥局聯絡電話，以及預約接送車輛；清潔、搬家等服務尚未開放。"
    return (
        "我還無法確定您的需求。您可以描述居家修繕問題、預約一般或無障礙接送，"
        "或告訴我想在哪個城市、行政區找藥局。"
    )

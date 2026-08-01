"""Safe Medical fallback that returns no invented pharmacy contacts."""

from adapters.base import SpecialistClient
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


class FakeMedicalClient(SpecialistClient):
    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        return SpecialistResponse(
            task_id=request.task_id,
            agent="medical-agent",
            status=TaskStatus.FAILED,
            message="藥局聯絡資訊服務暫時無法使用；為避免提供錯誤聯絡方式，請稍後再試。",
            data={"stage": "failed", "known_facts": {}, "missing_fields": []},
            error={"code": "MEDICAL_AGENT_UNAVAILABLE", "retryable": True},
        )

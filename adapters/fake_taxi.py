"""Safe Taxi fallback that never invents drivers or bookings."""

from adapters.base import SpecialistClient
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


class FakeTaxiClient(SpecialistClient):
    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        return SpecialistResponse(
            task_id=request.task_id,
            agent="taxi-agent",
            status=TaskStatus.FAILED,
            message="接送預約服務暫時無法使用；為避免提供錯誤司機或預訂資訊，請稍後再試。",
            data={"stage": "failed", "known_facts": {}, "missing_fields": []},
            error={"code": "TAXI_AGENT_UNAVAILABLE", "retryable": True},
        )

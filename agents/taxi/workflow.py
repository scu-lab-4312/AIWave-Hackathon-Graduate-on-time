"""Protocol-neutral Taxi Agent workflow."""

import json

from agents.taxi.agent import build_agent
from agents.taxi.schemas import TaxiAssessment
from agents.taxi.tools.gateway import build_gateway_client
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


def process_handoff(request: HandoffRequest) -> SpecialistResponse:
    instruction = {
        "task_id": request.task_id,
        "actor_id": request.actor_id,
        "intent": request.intent,
        "latest_user_message": request.message,
        "known_facts": request.known_facts,
        "missing_fields_from_previous_turn": request.missing_fields,
    }
    gateway = build_gateway_client()
    if gateway:
        agent = build_agent(tools=[gateway])
        result = agent(
            "請根據以下接送任務資料判斷本輪、需要時呼叫工具，最後輸出 TaxiAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=TaxiAssessment,
        )
    else:
        agent = build_agent()
        result = agent(
            "目前沒有媒合工具，只能收集資料，不得編造司機或宣稱已預訂。輸出 TaxiAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=TaxiAssessment,
        )
    assessment = TaxiAssessment.model_validate(result.structured_output)
    return SpecialistResponse(
        task_id=request.task_id,
        agent="taxi-agent",
        status=TaskStatus(assessment.status),
        message=assessment.message,
        data={
            "service_type": "taxi_booking",
            "known_facts": assessment.known_facts,
            "missing_fields": assessment.missing_fields,
            "stage": assessment.stage,
            "driver_options": [option.model_dump(mode="json") for option in assessment.driver_options],
            "booking": assessment.booking.model_dump(mode="json") if assessment.booking else None,
        },
    )

"""Protocol-neutral pharmacy contact lookup workflow."""

import json

from agents.medical.agent import build_agent
from agents.medical.schemas import MedicalAssessment
from agents.medical.tools.gateway import build_gateway_client
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


def process_handoff(request: HandoffRequest) -> SpecialistResponse:
    instruction = {
        "task_id": request.task_id,
        "intent": request.intent,
        "latest_user_message": request.message,
        "known_facts": request.known_facts,
        "missing_fields_from_previous_turn": request.missing_fields,
    }
    gateway = build_gateway_client()
    if gateway:
        agent = build_agent(tools=[gateway])
        result = agent(
            "根據以下藥局聯絡資訊任務判斷本輪、需要時呼叫工具，最後輸出 MedicalAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=MedicalAssessment,
        )
    else:
        agent = build_agent()
        result = agent(
            "目前沒有查詢工具，只能收集 city、district，不得編造藥局或電話。輸出 MedicalAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=MedicalAssessment,
        )
    assessment = MedicalAssessment.model_validate(result.structured_output)
    return SpecialistResponse(
        task_id=request.task_id,
        agent="medical-agent",
        status=TaskStatus(assessment.status),
        message=assessment.message,
        data={
            "service_type": "pharmacist_contact",
            "known_facts": assessment.known_facts,
            "missing_fields": assessment.missing_fields,
            "stage": assessment.stage,
            "pharmacy_options": [option.model_dump(mode="json") for option in assessment.pharmacy_options],
        },
    )

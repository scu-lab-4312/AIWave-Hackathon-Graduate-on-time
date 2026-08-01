"""Protocol-neutral Repair Agent workflow."""

import json

from agents.repair.agent import build_agent
from agents.repair.schemas import RepairAssessment
from agents.repair.tools.gateway import build_gateway_client
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


def process_handoff(request: HandoffRequest) -> SpecialistResponse:
    instruction = {
        "task_id": request.task_id,
        "actor_id": request.actor_id,
        "intent": request.intent,
        "latest_user_message": request.message,
        "known_facts": request.known_facts,
        "missing_fields_from_previous_turn": request.missing_fields,
        "safety_alert": request.safety_alert,
    }
    gateway = build_gateway_client()
    if gateway:
        # Strands owns the MCP provider lifecycle when it is registered as a
        # tool provider. Starting the client here would start it a second time.
        agent = build_agent(request.task_id, request.actor_id, tools=[gateway])
        result = agent(
            "請根據以下任務資料進行本輪判斷、需要時呼叫工具，最後輸出 RepairAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=RepairAssessment,
        )
    else:
        agent = build_agent(request.task_id, request.actor_id)
        result = agent(
            "目前沒有可用的媒合工具。請只收集資料，不得宣稱已媒合或預訂。根據以下資料輸出 RepairAssessment：\n"
            + json.dumps(instruction, ensure_ascii=False),
            structured_output_model=RepairAssessment,
        )
    assessment = RepairAssessment.model_validate(result.structured_output)
    return SpecialistResponse(
        task_id=request.task_id,
        status=TaskStatus(assessment.status),
        message=assessment.message,
        data={
            "issue_type": assessment.issue_type,
            "urgency": assessment.urgency,
            "known_facts": assessment.known_facts,
            "missing_fields": assessment.missing_fields,
            "ready_for_matching": assessment.ready_for_matching,
            "stage": assessment.stage,
            "estimate": assessment.estimate.model_dump(mode="json") if assessment.estimate else None,
            "provider_options": [option.model_dump(mode="json") for option in assessment.provider_options],
            "booking": assessment.booking.model_dump(mode="json") if assessment.booking else None,
        },
    )

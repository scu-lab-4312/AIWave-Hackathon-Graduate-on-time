"""Black-box checks for the deployed AgentCore runtime."""

import json
import os
import uuid

import boto3
from botocore.config import Config


RUNTIME_ARN = os.getenv(
    "AGENT_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/orchestrator-B7uJuFGYRT",
)
MEMORY_ID = os.getenv("ORCHESTRATOR_MEMORY_ID", "orchestrator_mem-8Qfmrh3D5G")


def invoke(client, prompt: str, session_id: str) -> tuple[int, dict]:
    response = client.invoke_agent_runtime(
        agentRuntimeArn=RUNTIME_ARN,
        qualifier="DEFAULT",
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt, "actor_id": "remote-verifier"}).encode(),
    )
    body = json.loads(response["response"].read())
    return response["ResponseMetadata"]["HTTPStatusCode"], body


def main() -> None:
    client = boto3.client(
        "bedrock-agentcore",
        region_name="us-west-2",
        config=Config(read_timeout=300, connect_timeout=10),
    )
    print(f"runtime={RUNTIME_ARN}", flush=True)
    cases = [
        ("我家廚房水管一直漏水，已經關總水閥了", "repair"),
        ("我想找藥師的 LINE", "medical"),
        ("你好，這個平台怎麼使用？", "platform_help"),
        ("我想預約搬家服務", "unsupported_service"),
        ("家裡怪怪的", "unknown"),
    ]
    for prompt, expected_intent in cases:
        session_id = str(uuid.uuid4())
        print(f"invoking: {prompt}", flush=True)
        status, body = invoke(client, prompt, session_id)
        assert status == 200
        assert body["routing"]["intent"] == expected_intent, body
        print(json.dumps({"prompt": prompt, "status": status, "response": body}, ensure_ascii=False), flush=True)

    task_session = str(uuid.uuid4())
    _, first = invoke(client, "廚房水管每秒一滴，地點在台北市信義區", task_session)
    task_id = first["active_task"]["task_id"]
    assert first["specialist"]["status"] == "needs_input"
    assert first["specialist_backend"] == "agentcore", first
    assert first["specialist"]["data"]["stage"] == "awaiting_selection", first
    assert len(first["specialist"]["data"]["provider_options"]) == 3, first
    provider = first["specialist"]["data"]["provider_options"][0]
    slot = provider["available_slots"][0]
    _, second = invoke(
        client,
        f"我要選第一間「{provider['name']}」，slot_id: {slot['slot_id']}",
        task_session,
    )
    assert second["routing"]["sticky_task_id"] == task_id, second
    assert second["specialist"]["status"] == "completed", second
    assert second["specialist_backend"] == "agentcore", second
    assert second["specialist"]["data"]["stage"] == "booked", second
    assert second["active_task"] is None, second
    print(json.dumps({"task_session": task_session, "first": first, "second": second}, ensure_ascii=False), flush=True)

    medical_session = str(uuid.uuid4())
    medical_prompt = "我想找藥師的 LINE，不提供醫療資料"
    _, medical_first = invoke(client, medical_prompt, medical_session)
    medical_task_id = medical_first["active_task"]["task_id"]
    assert medical_first["routing"]["intent"] == "medical", medical_first
    assert medical_first["specialist_backend"] == "agentcore", medical_first
    assert medical_first["active_task"]["target_agent"] == "medical-agent", medical_first
    _, medical_second = invoke(client, "台北市信義區", medical_session)
    assert medical_second["routing"]["sticky_task_id"] == medical_task_id, medical_second
    assert medical_second["specialist_backend"] == "agentcore", medical_second
    assert medical_second["specialist"]["data"]["stage"] == "contacts_ready", medical_second
    assert len(medical_second["specialist"]["data"]["pharmacy_options"]) == 3, medical_second
    assert medical_second["active_task"] is None, medical_second
    print(
        json.dumps(
            {"medical_session": medical_session, "first": medical_first, "second": medical_second},
            ensure_ascii=False,
        ),
        flush=True,
    )
    memory = client.list_events(
        memoryId=MEMORY_ID,
        actorId="remote-verifier",
        sessionId=medical_session,
        includePayloads=True,
        maxResults=100,
    )
    serialized_events = json.dumps(memory.get("events", []), ensure_ascii=False, default=str)
    assert medical_prompt not in serialized_events, serialized_events
    assert "[medical service request redacted]" in serialized_events, serialized_events
    print(f"MEDICAL MEMORY REDACTION PASSED ({len(memory.get('events', []))} events)", flush=True)
    print("ALL REMOTE CHECKS PASSED", flush=True)


if __name__ == "__main__":
    main()

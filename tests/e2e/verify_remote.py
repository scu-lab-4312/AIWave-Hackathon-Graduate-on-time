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
    _, first = invoke(client, "廚房水管漏水", task_session)
    task_id = first["active_task"]["task_id"]
    assert first["specialist"]["status"] == "needs_input"
    _, second = invoke(client, "每秒一滴", task_session)
    assert second["routing"]["sticky_task_id"] == task_id, second
    assert second["specialist"]["status"] == "completed", second
    assert second["active_task"] is None, second
    print(json.dumps({"task_session": task_session, "first": first, "second": second}, ensure_ascii=False), flush=True)
    print("ALL REMOTE CHECKS PASSED", flush=True)


if __name__ == "__main__":
    main()

"""Real AWS transport for invoking a Medical AgentCore Runtime."""

import json

import boto3
from botocore.config import Config
from pydantic import ValidationError

from adapters.base import SpecialistClient
from shared.contracts import HandoffRequest, SpecialistResponse


class AgentCoreMedicalClient(SpecialistClient):
    def __init__(self, runtime_arn: str, region: str = "us-west-2", qualifier: str = "DEFAULT"):
        if not runtime_arn:
            raise ValueError("MEDICAL_AGENT_RUNTIME_ARN is required")
        self.runtime_arn = runtime_arn
        self.qualifier = qualifier
        self.client = boto3.client(
            "bedrock-agentcore",
            region_name=region,
            config=Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 2}),
        )

    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        response = self.client.invoke_agent_runtime(
            agentRuntimeArn=self.runtime_arn,
            qualifier=self.qualifier,
            runtimeSessionId=request.task_id,
            payload=request.model_dump_json().encode(),
        )
        raw = json.loads(response["response"].read())
        payload = raw.get("specialist", raw)
        try:
            return SpecialistResponse.model_validate(payload)
        except ValidationError as error:
            raise RuntimeError(f"Medical Agent returned an invalid contract: {error}") from error

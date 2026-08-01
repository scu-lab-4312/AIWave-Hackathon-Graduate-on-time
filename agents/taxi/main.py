"""HTTP Runtime entrypoint for the real Taxi Agent."""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents.taxi.workflow import process_handoff
from shared.contracts import HandoffRequest


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    request = HandoffRequest.model_validate(payload)
    return process_handoff(request).model_dump(mode="json")


if __name__ == "__main__":
    app.run()

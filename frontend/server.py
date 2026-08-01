"""Minimal web UI and SigV4-signed proxy for the deployed orchestrator."""

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import boto3
from botocore.config import Config


ROOT = Path(__file__).parent
RUNTIME_ARN = os.getenv(
    "AGENT_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/orchestrator-B7uJuFGYRT",
)
REGION = os.getenv("AWS_REGION", "us-west-2")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            prompt = str(request.get("prompt", "")).strip()
            session_id = str(request.get("session_id", "")).strip()
            actor_id = str(request.get("actor_id", "anonymous")).strip()
            if not prompt or len(session_id) < 33:
                raise ValueError("prompt 與有效的 session_id 為必填")

            client = boto3.client(
                "bedrock-agentcore",
                region_name=REGION,
                config=Config(read_timeout=300, connect_timeout=10),
            )
            response = client.invoke_agent_runtime(
                agentRuntimeArn=RUNTIME_ARN,
                qualifier="DEFAULT",
                runtimeSessionId=session_id,
                payload=json.dumps({"prompt": prompt, "actor_id": actor_id}).encode(),
            )
            body = json.loads(response["response"].read())
            self._json(200, body)
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
        except Exception as error:
            self.log_error("Agent invocation failed: %s", error)
            self._json(502, {"error": "Agent 暫時無法回應，請稍後再試。"})

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = int(os.getenv("PORT", "3000"))
    print(f"Orchestrator UI: http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

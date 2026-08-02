"""Minimal web UI with local and SigV4-signed AgentCore backends."""

import json
import logging
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import boto3
from botocore.config import Config


ROOT = Path(__file__).parent
RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN")
REGION = os.getenv("AWS_REGION", "us-west-2")
BACKEND_MODE = os.getenv("FRONTEND_AGENT_MODE", "auto").strip().lower()
VALID_BACKEND_MODES = {"auto", "agentcore", "local"}
logger = logging.getLogger("frontend.server")


def _invoke_remote(prompt: str, session_id: str, actor_id: str) -> dict:
    if not RUNTIME_ARN:
        raise RuntimeError("FRONTEND_AGENT_MODE=agentcore requires AGENT_RUNTIME_ARN")
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
    raw = response["response"].read()
    if not raw:
        raise RuntimeError("AgentCore orchestrator returned an empty response")
    body = json.loads(raw)
    body.setdefault("orchestrator_backend", "agentcore")
    return body


def _invoke_local(prompt: str, session_id: str, actor_id: str, backend: str) -> dict:
    from apps.orchestrator.main import process_turn

    body = process_turn(prompt, session_id, actor_id)
    body["orchestrator_backend"] = backend
    return body


def invoke_agent(prompt: str, session_id: str, actor_id: str) -> dict:
    """Use the configured backend, with a local fallback in auto mode."""
    if BACKEND_MODE not in VALID_BACKEND_MODES:
        raise RuntimeError(
            f"Unsupported FRONTEND_AGENT_MODE: {BACKEND_MODE}; "
            f"expected one of {sorted(VALID_BACKEND_MODES)}"
        )
    if BACKEND_MODE == "local" or (BACKEND_MODE == "auto" and not RUNTIME_ARN):
        return _invoke_local(prompt, session_id, actor_id, "local")
    if BACKEND_MODE == "agentcore":
        return _invoke_remote(prompt, session_id, actor_id)
    try:
        return _invoke_remote(prompt, session_id, actor_id)
    except Exception:
        logger.exception("AgentCore orchestrator failed; using local fallback")
        return _invoke_local(prompt, session_id, actor_id, "local-fallback")


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

            self._json(200, invoke_agent(prompt, session_id, actor_id))
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
        except Exception:
            # 記錄完整 traceback，方便從 log 確認 Load failed / 502 的實際根因。
            logger.exception("Agent invocation failed")
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
    print(f"Orchestrator UI: http://localhost:{port} (backend={BACKEND_MODE})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

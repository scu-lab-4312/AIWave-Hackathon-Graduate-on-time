"""Conversation transcript and sticky-task persistence."""

import os
import threading

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands import Agent
from strands.models import BedrockModel

from shared.contracts import ActiveTask
from shared.ids import safe_id


MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))
MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")
STATE_KEY = "active_task"
AGENT_ID = "orchestrator-state"

_local_states: dict[str, dict] = {}
_local_lock = threading.Lock()


def build_state_agent(session_id: str, actor_id: str) -> tuple[Agent | None, AgentCoreMemorySessionManager | None]:
    if not MEMORY_ID:
        return None, None
    config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=safe_id(session_id, "default-session"),
        actor_id=safe_id(actor_id, "anonymous"),
    )
    manager = AgentCoreMemorySessionManager(config, region_name=REGION)
    agent = Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        agent_id=AGENT_ID,
        callback_handler=None,
        session_manager=manager,
    )
    return agent, manager


def load_active_task(session_id: str, agent: Agent | None) -> ActiveTask | None:
    if agent:
        raw = agent.state.get(STATE_KEY)
    else:
        with _local_lock:
            raw = _local_states.get(session_id, {}).get(STATE_KEY)
    return ActiveTask.model_validate(raw) if raw else None


def save_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    active_task: ActiveTask | None,
    agent: Agent | None,
    manager: AgentCoreMemorySessionManager | None,
) -> None:
    raw_task = active_task.model_dump(mode="json") if active_task else None
    if agent and manager:
        manager.append_message({"role": "user", "content": [{"text": user_message}]}, agent)
        manager.append_message({"role": "assistant", "content": [{"text": assistant_message}]}, agent)
        agent.state.set(STATE_KEY, raw_task)
        manager.sync_agent(agent)
    else:
        with _local_lock:
            _local_states[session_id] = {STATE_KEY: raw_task}


def clear_local_states() -> None:
    """Test helper for the in-process fallback store."""
    with _local_lock:
        _local_states.clear()

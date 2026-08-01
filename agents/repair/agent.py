"""Construct the real Strands-based Repair Agent with task-scoped Memory."""

import os

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands import Agent
from strands.models import BedrockModel

from agents.repair.prompts import SYSTEM_PROMPT
from shared.ids import safe_id


REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))
MODEL_ID = os.getenv("REPAIR_AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
MEMORY_ID = os.getenv("MEMORY_REPAIR_AGENT_MEMORY_ID") or os.getenv("REPAIR_AGENT_MEMORY_ID")


def build_agent(task_id: str, actor_id: str, tools: list | None = None) -> Agent:
    session_manager = None
    if MEMORY_ID:
        config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            session_id=safe_id(task_id, "repair-task"),
            actor_id=safe_id(actor_id, "anonymous"),
        )
        session_manager = AgentCoreMemorySessionManager(config, region_name=REGION)
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        agent_id="repair-specialist",
        callback_handler=None,
        system_prompt=SYSTEM_PROMPT,
        session_manager=session_manager,
        tools=tools or [],
    )

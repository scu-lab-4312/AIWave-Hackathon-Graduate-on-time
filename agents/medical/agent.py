"""Construct the Strands-based pharmacy contact Agent."""

import os

from strands import Agent
from strands.models import BedrockModel

from agents.medical.prompts import SYSTEM_PROMPT


REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))
MODEL_ID = os.getenv("MEDICAL_AGENT_MODEL_ID", "us.anthropic.claude-sonnet-4-6")


def build_agent(tools: list | None = None) -> Agent:
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        agent_id="pharmacy-contact-specialist",
        callback_handler=None,
        system_prompt=SYSTEM_PROMPT,
        tools=tools or [],
    )

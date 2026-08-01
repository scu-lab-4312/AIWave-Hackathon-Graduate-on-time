"""Identifier helpers shared by runtimes."""

import re
import uuid


def safe_id(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "-", value or fallback)
    return cleaned[:100] or fallback


def new_task_id() -> str:
    return str(uuid.uuid4())

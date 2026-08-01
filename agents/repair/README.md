# Repair Agent

This package is the real Strands/Bedrock baseline for a separately deployed AgentCore Runtime.

- `main.py`: HTTP Runtime boundary.
- `workflow.py`: protocol-neutral handoff processing.
- `agent.py`: model and task-scoped Memory construction.
- `schemas.py`: structured model output.
- `prompts.py`: versioned domain behavior.
- `tools/`: real MCP/Gateway tools will be added after their APIs and authorization are selected.

It is not deployed yet. Until `REPAIR_AGENT_RUNTIME_ARN` is configured, the Orchestrator uses `adapters/fake_repair.py`.

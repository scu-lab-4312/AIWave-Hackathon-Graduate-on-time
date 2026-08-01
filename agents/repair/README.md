# Repair Agent

This package is the deployed Strands/Bedrock Repair Agent for a separate AgentCore Runtime.

- `main.py`: HTTP Runtime boundary.
- `workflow.py`: protocol-neutral handoff processing.
- `agent.py`: model and task-scoped Memory construction.
- `schemas.py`: structured model output.
- `prompts.py`: versioned domain behavior.
- `tools/`: SigV4 MCP client for the Repair AgentCore Gateway.

Provider master data comes from the read-only shared CMS table `hackathon.cms_homepage_service_type_10`. Estimate history, availability, services, and bookings live in `agent_repair_*` tables owned by this Agent. The fake adapter remains a no-side-effect fallback only.

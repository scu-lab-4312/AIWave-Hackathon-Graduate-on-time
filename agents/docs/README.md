# 專業 Agent 開發手冊

這個目錄是新增服務 Agent 的共同基底。目標是讓每個專業 Agent 都能獨立測試、部署、觀測與替換，同時遵守 `shared/contracts.py`。

## 文件順序

1. [新增服務檢查表](01-new-service-checklist.md)
2. [Amazon Bedrock AgentCore 開發流程](02-agentcore-development-flow.md)
3. [契約、測試與上線門檻](03-contract-testing-release.md)
4. [Repair Agent：AWS CLI 真實部署範本](04-repair-aws-cli-deployment.md)

## 架構原則

- 使用者只呼叫 Orchestrator。
- 專業 Agent 是獨立 Runtime，透過版本化契約收送資料。
- 真實 AgentCore Runtime 是主要路徑；fake 只能作為開發與無副作用備援。
- Orchestrator Memory 以 `conversation_id` 保存主對話；專業 Agent Memory 以 `task_id` 保存領域任務。
- Agent 只負責推理與協調；外部動作透過具明確 schema、權限與冪等性的工具執行。

## 官方基準資料

- [AgentCore CLI 入門](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Runtime service contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html)
- [A2A Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a.html)
- [InvokeAgentRuntime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)
- [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)

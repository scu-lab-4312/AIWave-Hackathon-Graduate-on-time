# Home Service Multi-Agent

AgentCore Runtime 提供有限意圖路由、可追蹤的專業任務，以及 AgentCore Memory 多輪狀態。

目前支援四種路由：`repair`、`platform_help`、`unsupported_service`、`unknown`。Orchestrator 與專業 Agent 透過 `shared/contracts.py` 溝通，並能在 `needs_input` 後以相同 `task_id` 接續下一輪。

## 專業 Agent backend

Repair Agent 的選擇順序：

- 設定 `REPAIR_AGENT_RUNTIME_ARN`：`auto` 模式使用真正的 AgentCore Runtime。
- 未設定 ARN：使用無外部副作用的 fake。
- 真實 Runtime 失敗且 `REPAIR_AGENT_FAKE_FALLBACK=true`：降級為 fake，response 會標示 `specialist_backend=fake-fallback`。

正式環境可明確設定：

```bash
REPAIR_AGENT_MODE=agentcore
REPAIR_AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...:runtime/...'
REPAIR_AGENT_FAKE_FALLBACK=true
```

新增專業服務前先閱讀 [agents/docs/README.md](agents/docs/README.md)。

## 啟動聊天前端

使用具備 `bedrock-agentcore:InvokeAgentRuntime` 權限的 AWS credentials：

```bash
.venv/bin/python frontend.py
```

開啟 <http://localhost:3000>。瀏覽器只呼叫本機 `/api/chat`，AWS credentials 不會送到前端。

若部署到不同 runtime，可設定：

```bash
AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...' .venv/bin/python frontend.py
```

## 黑箱驗證

```bash
.venv/bin/python -u verify_remote.py
```

## 本機測試

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 主要目錄

```text
apps/orchestrator/  # 路由、task state 與 specialist dispatch
agents/repair/      # 可獨立部署的真實 Repair Agent baseline
adapters/           # AgentCore transport 與 fake fallback
shared/             # 版本化跨 Agent 契約
agents/docs/        # 新服務 AgentCore 開發流程
tests/              # unit / contract / integration / e2e
infra/              # AgentCore 與 IAM 說明
frontend/           # UI 與簽章 proxy
```

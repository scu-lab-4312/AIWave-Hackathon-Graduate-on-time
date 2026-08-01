# Amazon Bedrock AgentCore 專業 Agent 開發流程

本專案目前的 Repair Agent 使用 HTTP contract baseline；正式多 Agent 發展目標是 A2A Runtime。A2A 提供 JSON-RPC 2.0、Agent Card discovery 與 AgentCore session isolation，適合 Agent 對 Agent；MCP/Gateway 則用於 Agent 對工具。

## 0. 工具版本

新服務使用新版 AgentCore CLI，不再以舊的 Python starter toolkit 建新專案：

```bash
npm install -g @aws/agentcore
agentcore --help
```

官方目前要求 Node.js 18+、Python 3.10+；Runtime 使用 ARM64。CLI 與參數仍可能更新，執行前以本機 `agentcore --help` 和官方文件為準。

## 1. 本機基線

在 monorepo 先完成：

- `shared/contracts.py` 可以驗證 request/response。
- `agents/<service>/workflow.py` 不依賴 transport。
- fake 與 real adapter 都實作 `SpecialistClient`。
- unit 與 contract tests 不需 AWS 即可執行。
- 所有寫入型工具都有 idempotency key，預設使用 `task_id`。

## 2. 建立 AgentCore 專案資源

在既有 AgentCore project 中可用互動式 `agentcore add agent` 新增 Agent；若要從獨立 A2A scaffold 開始，官方流程是：

```bash
agentcore create --protocol A2A
```

多 Agent project 亦可使用：

```bash
agentcore add agent --name RepairAgent --language Python --framework Strands --model-provider Bedrock
```

選擇：

- CodeZip：純 Python、快速部署的預設選項。
- Container：需要系統依賴、自訂執行環境或 A2A container contract 時使用。

A2A Runtime contract 為 `0.0.0.0:9000`、root POST、`/.well-known/agent-card.json`；使用 AgentCore SDK 的 `serve_a2a` 可處理必要 endpoint 與 header propagation。

## 3. Memory

專業 Agent 使用獨立 Memory：

```text
actor_id   = 已驗證的使用者 ID
session_id = task_id
```

新增 Memory：

```bash
agentcore add memory --name repair_agent_memory
```

需要跨案件偏好或摘要時才加入 SEMANTIC/SUMMARIZATION 等長期策略。只做單一案件多輪時，STM 足夠。

若領域不需要保存狀態，或資料最小化比延續性更重要，可以不替專業 Agent 建 Memory。此時由 Orchestrator 的 active task 只保存下一輪必需欄位；例如 Medical Agent 僅保存 `city`、`district`，使用者原始文字以 redacted placeholder 寫入 Orchestrator Memory。

部署後確認 execution role 對正確 Memory ARN 具有 `CreateEvent`、`ListEvents`、`ListSessions` 等實際使用權限；不要只確認 Memory 狀態為 ACTIVE。

## 4. 工具與 Gateway

工具依風險分階段加入：

1. 唯讀查詢，例如服務區域與師傅可用時間。
2. 可撤銷寫入，例如建立草稿服務單。
3. 高風險動作，例如確認預約、付款或取消訂單。

後端 API、Lambda 或 MCP server 可透過 AgentCore Gateway 暴露。每個工具都需要結構化 schema、最小 IAM/OAuth 權限、timeout、可重試分類、idempotency key，以及寫入前的明確使用者確認。

## 5. 本機與部署驗證

```bash
agentcore dev
agentcore deploy --dry-run
agentcore deploy
```

遠端驗證至少涵蓋：

- Agent Card 可取得（A2A）。
- `InvokeAgentRuntime` 權限正確。
- request/response 通過共用 schema。
- 相同 `task_id` 能恢復 Memory。
- timeout、AccessDenied、invalid response 能降級。
- fake fallback 不執行任何外部寫入。

SDK 呼叫 `InvokeAgentRuntime` 時需要 `bedrock-agentcore:InvokeAgentRuntime`；同一任務的多輪必須重用 session ID。若入口使用 OAuth，依官方說明需使用 HTTPS bearer-token 流程，而不是一般 AWS SDK SigV4 呼叫。

## 6. Orchestrator 接線

部署完成後設定：

```bash
<SERVICE>_AGENT_MODE=agentcore
<SERVICE>_AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...:runtime/...'
<SERVICE>_AGENT_QUALIFIER=DEFAULT
<SERVICE>_AGENT_FAKE_FALLBACK=true
```

Orchestrator execution role必須只被允許呼叫目標 Runtime ARN。觀察 `specialist_backend`：正式請求應為 `agentcore`，若出現 `fake-fallback` 必須在 logs/metrics 中可見。

## 7. 觀測與品質

上線前建立 dashboard 或告警：invocation latency、error rate、500、throttling、timeout、`needs_input` 平均輪數、fake fallback 次數、工具成功率、重試與 token usage。

AgentCore 的 runtime logs、metrics 與 traces 會進 CloudWatch；自訂 log 必須包含 `task_id`、`conversation_id`、agent name、contract version，但不可記錄不必要的個資或密鑰。

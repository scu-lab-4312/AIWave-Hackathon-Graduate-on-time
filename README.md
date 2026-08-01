# Home Service Multi-Agent

AgentCore Runtime 提供有限意圖路由、可追蹤的專業任務，以及 AgentCore Memory 多輪狀態。

目前支援六種路由：`repair`、`medical`、`taxi`、`platform_help`、`unsupported_service`、`unknown`。Orchestrator 與專業 Agent 透過 `shared/contracts.py` 溝通，並能在 `needs_input` 後以相同 `task_id` 接續下一輪。

## 專業 Agent backend

Repair、Medical 與 Taxi Agent 使用相同的 backend 選擇規則：

- 設定 `REPAIR_AGENT_RUNTIME_ARN`：`auto` 模式使用真正的 AgentCore Runtime。
- 未設定 ARN：使用無外部副作用的 fake。
- 真實 Runtime 失敗且 `REPAIR_AGENT_FAKE_FALLBACK=true`：降級為 fake，response 會標示 `specialist_backend=fake-fallback`。

正式環境可明確設定：

```bash
REPAIR_AGENT_MODE=agentcore
REPAIR_AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...:runtime/...'
REPAIR_AGENT_FAKE_FALLBACK=true

MEDICAL_AGENT_MODE=agentcore
MEDICAL_AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...:runtime/...'
MEDICAL_AGENT_FAKE_FALLBACK=true

TAXI_AGENT_MODE=agentcore
TAXI_AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...:runtime/...'
TAXI_AGENT_FAKE_FALLBACK=true
```

Medical Agent 只接收城市與行政區，從 RDS 取得三間藥局的公開電話；不接收或保存病名、症狀、藥名、處方或個人聯絡資料，也不建立預約。

Taxi Agent 從共享 CMS 取得三位司機，收集城市、行政區、目的地與特殊乘車需求；使用者選擇司機與時段後建立 `requested` 預訂，不編造車牌或宣稱已確認派車。

新增專業服務前先閱讀 [agents/docs/README.md](agents/docs/README.md)。

## 啟動聊天前端

本機開發不需要 AWS credentials；預設 `auto` 模式在未設定 `AGENT_RUNTIME_ARN` 時直接使用本機 orchestrator 與無外部副作用的 fake specialist：

```bash
.venv/bin/python frontend.py
```

開啟 <http://localhost:3000>。瀏覽器只呼叫本機 `/api/chat`。

若要使用已部署的 AgentCore orchestrator，請提供具備 `bedrock-agentcore:InvokeAgentRuntime` 權限的 AWS credentials，並明確設定：

```bash
FRONTEND_AGENT_MODE=agentcore \
AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...' \
.venv/bin/python frontend.py
```

也可使用 `FRONTEND_AGENT_MODE=local` 強制本機模式；此模式停用 AgentCore Memory，並強制使用無外部副作用的 fake specialist。`auto` 模式設定了 runtime 時會優先呼叫 AgentCore，只有在憑證無法取得、確認請求尚未送出時才降級至本機，避免重播結果不明的遠端操作。

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
agents/medical/     # 隱私最小化的真實 Medical Agent
agents/taxi/        # RDS-backed 接送媒合與預訂 Agent
adapters/           # AgentCore transport 與 fake fallback
shared/             # 版本化跨 Agent 契約
agents/docs/        # 新服務 AgentCore 開發流程
tests/              # unit / contract / integration / e2e
infra/              # AgentCore 與 IAM 說明
frontend/           # UI 與簽章 proxy
```

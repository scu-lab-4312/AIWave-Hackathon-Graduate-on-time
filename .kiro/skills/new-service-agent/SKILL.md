---
name: new-service-agent
description: 依 agents/docs 手冊生成一個新的專業服務 Agent（AgentCore Runtime + 契約 + fake/real adapter + 工具 + 測試 + 部署）。當使用者要「新增一個專業 agent / 服務 agent」「照 repair 的樣子做一個 XXX agent」「生成 cleaning / moving / pest 等專業 agent」時使用本 skill。
---

# 生成專業服務 Agent

本 skill 把 `agents/docs/` 的四份手冊收斂成一條可執行流程，用來生成一個能獨立測試、部署、觀測與替換的新專業服務 Agent，並嚴格遵守 `shared/contracts.py`。

## 權威來源（先讀，勿憑記憶）

生成前務必讀取並以下列檔案為準；本 skill 只是流程骨架，欄位與命名一律以真實程式碼為主：

- `agents/docs/README.md` — 架構原則與官方基準連結
- `agents/docs/01-new-service-checklist.md` — 目錄、契約、實作順序、環境變數
- `agents/docs/02-agentcore-development-flow.md` — AgentCore CLI、Memory、Gateway、驗證
- `agents/docs/03-contract-testing-release.md` — 測試金字塔與上線門檻
- `agents/docs/04-repair-aws-cli-deployment.md` — 已跑通的 AWS CLI 真實部署範本
- `shared/contracts.py` — `HandoffRequest`、`SpecialistResponse`、`ActiveTask`、`TaskStatus`、`CONTRACT_VERSION`
- 參考實作：`agents/repair/`、`adapters/base.py`、`adapters/fake_repair.py`、`adapters/agentcore_repair.py`、`apps/orchestrator/agent_registry.py`

## 使用前先問清楚（禁止略過）

在寫任何程式碼前，必須先與使用者確認業務邊界，未確認前**不得**把工具全部交給模型：

1. 服務名稱與 `service_id`（例如 `cleaning`）。
2. 支援與**不支援**的需求。
3. 判定 `completed` 所需的必要欄位（`missing_fields` 的來源）。
4. 安全與人工接手條件（對應 `safety_alert`）。
5. 可讀資料與可執行的外部動作，各動作的風險分級。
6. `completed` 的精確意義（尤其是否涉及預約 / 付款 / 寫入）。

若使用者尚未給出這些，先產生一份「業務邊界草稿」讓對方確認，再進入實作。

## 核心架構原則（不可違反）

- 使用者只呼叫 Orchestrator；專業 Agent 是獨立 Runtime，透過版本化契約收送資料。
- 真實 AgentCore Runtime 是主要路徑；fake 只作為開發與**無副作用**備援。
- Orchestrator Memory 以 `conversation_id` 保存；專業 Agent Memory 以 `task_id`（= `session_id`）保存。
- Agent 只負責推理與協調；外部動作透過具明確 schema、最小權限與冪等性的工具執行。
- Agent 輸出永遠是**提案**，實際寫入前必過確定性檢查與（高風險時）使用者確認。
- 專業 Agent **不得**把未執行的外部動作宣稱為成功；fake fallback 不得回報虛構的預約 / 價格 / 師傅。

## 產出的目錄骨架

以 `<service>` 代入實際服務名（下例 `cleaning`）：

```text
agents/<service>/
├── __init__.py
├── main.py          # BedrockAgentCoreApp entrypoint，驗證 HandoffRequest → 回 SpecialistResponse
├── agent.py         # 模型 / 推理設定
├── workflow.py      # process_handoff(request) -> SpecialistResponse，不依賴 transport
├── state.py         # <Service>TaskState，以 task_id 為主鍵
├── schemas.py       # 領域結構化輸出（pydantic）
├── prompts.py
├── requirements.txt
├── knowledge/
└── tools/
    └── __init__.py

adapters/agentcore_<service>.py   # 真實 AgentCore transport
adapters/fake_<service>.py        # 無副作用 fake
tests/contract/test_<service>_contract.py
tests/integration/test_<service>_handoff.py
```

## 實作順序（嚴格依序）

1. **契約優先**：優先沿用 `HandoffRequest` / `SpecialistResponse`；新增欄位必須向後相容，破壞性修改要升 `CONTRACT_VERSION`。`task_id` 在重試時不得改變。
2. `schemas.py` 與 `state.py`。
3. contract tests（同一 request 必須能驗證 fake 與真實 Runtime 的 response）。
4. fake adapter（實作 `SpecialistClient`，保證無副作用）。
5. 真實 Agent `workflow.py`。
6. Memory（STM 足夠即可，跨案件偏好才加 SEMANTIC/SUMMARIZATION）。
7. 真實工具與最小 IAM。
8. Orchestrator registry 接線。
9. 整合測試與遠端 E2E。

## 樣板：main.py

對齊 `agents/repair/main.py`：

```python
"""HTTP Runtime entrypoint for the real <Service> Agent baseline."""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents.<service>.workflow import process_handoff
from shared.contracts import HandoffRequest

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    request = HandoffRequest.model_validate(payload)
    return process_handoff(request).model_dump(mode="json")


if __name__ == "__main__":
    app.run()
```

## 樣板：state.py

以 `task_id` 為主鍵，只放領域欄位：

```python
"""<Service> task state owned by the specialist runtime."""

from typing import Any

from pydantic import BaseModel, Field


class <Service>TaskState(BaseModel):
    task_id: str
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    # 加入該服務特有欄位（例如 selected_provider_id、service_request_id）
```

## 樣板：fake adapter（無副作用）

對齊 `adapters/fake_repair.py`，重點是實作 `SpecialistClient.invoke`，只做問答收斂，不做任何外部寫入：

```python
"""Deterministic fake <Service> Agent used to validate the handoff contract."""

from adapters.base import SpecialistClient
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


class Fake<Service>Client(SpecialistClient):
    """Contract-compatible fallback; never performs external side effects."""

    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        missing = [f for f in self._required_fields(request.intent) if f not in request.known_facts]
        if missing:
            return SpecialistResponse(
                task_id=request.task_id,
                status=TaskStatus.NEEDS_INPUT,
                message=self._question_for(missing[0]),
                data={"known_facts": request.known_facts, "missing_fields": missing},
            )
        return SpecialistResponse(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            message="已收齊必要資訊。（fake：未執行任何外部動作）",
            data={"ready_for_matching": True, "known_facts": request.known_facts},
        )

    def _required_fields(self, intent: str) -> list[str]: ...
    def _question_for(self, field: str) -> str: ...
```

## 樣板：真實 adapter

對齊 `adapters/agentcore_repair.py`：以 `runtimeSessionId=request.task_id` 呼叫 `invoke_agent_runtime`，回應以 `SpecialistResponse.model_validate` 驗證，驗證失敗要拋出明確錯誤而非靜默降級。

## Orchestrator 接線

在 `apps/orchestrator/agent_registry.py` 新增 `<service>_registration()`，沿用 repair 的 `auto|agentcore|fake` 解析邏輯。環境變數慣例（見手冊 01）：

```text
<SERVICE>_AGENT_MODE=auto|agentcore|fake
<SERVICE>_AGENT_RUNTIME_ARN=arn:...
<SERVICE>_AGENT_QUALIFIER=DEFAULT
<SERVICE>_AGENT_FAKE_FALLBACK=true|false
<SERVICE>_AGENT_MODEL_ID=...
MEMORY_<SERVICE>_AGENT_MEMORY_ID=...
```

正式環境明確設為 `agentcore`。若流程含預約 / 付款 / 寫入，fake fallback 必須保持無副作用且清楚標示交易未完成。

## 工具分階段加入（依風險）

1. 唯讀查詢（服務區域、可用時間）。
2. 可撤銷寫入（建立草稿單）。
3. 高風險動作（確認預約、付款、取消）。

每個工具都需要：結構化 schema、最小 IAM/OAuth 權限、timeout、可重試分類、idempotency key（預設用 `task_id`），以及寫入前的明確使用者確認。後端 API / Lambda / MCP 透過 AgentCore Gateway 暴露。

## AgentCore CLI 快速指令（以本機 `agentcore --help` 為準）

```bash
npm install -g @aws/agentcore
agentcore add agent --name <Service>Agent --language Python --framework Strands --model-provider Bedrock
agentcore add memory --name <service>_agent_memory
agentcore dev
agentcore deploy --dry-run
agentcore deploy
```

需要 A2A 獨立 scaffold 時用 `agentcore create --protocol A2A`（contract：`0.0.0.0:9000`、root POST、`/.well-known/agent-card.json`）。真實 AWS CLI 部署（RDS/Lambda/Gateway/Runtime）完整範本見 `agents/docs/04-repair-aws-cli-deployment.md`；Runtime 跑 Linux ARM64，需以 `--python-platform aarch64-manylinux2014` 下載 wheels，不可直接打包 macOS venv。

## 測試金字塔

- **Unit**：路由與必要欄位判斷、state transition、safety rule、timeout/error mapping。
- **Contract**：同一 request 驗證 fake 與真實 response，並 `assert response.task_id == request.task_id`。
- **Integration**：Orchestrator → fake / local real specialist；specialist → mock tools。
- **Remote E2E**：Orchestrator Runtime → Specialist Runtime、同 task 兩輪 Memory、IAM 最小權限、CloudWatch 可依 task ID 找到完整 trace。

## 上線門檻（全數通過才算完成）

- 所有 contract tests 通過。
- 至少一條 `needs_input → completed` 遠端流程通過。
- 危險案例先輸出安全處置，不給高風險 DIY 指示。
- 寫入型工具具確認與冪等性。
- AgentCore 故障時不遺失 active task。
- fake fallback 不回報虛構結果。
- 已記錄 rollback 方式與前一個 Runtime qualifier/version。
- E2E 明確 `assert specialist_backend == "agentcore"`（少了 endpoint ARN 會 AccessDenied，但 fallback 開啟時表面仍回 200）。

## 觀測

上線前建立 dashboard / 告警：invocation latency、error rate、500、throttling、timeout、`needs_input` 平均輪數、fake fallback 次數、工具成功率、重試、token usage。自訂 log 必含 `task_id`、`conversation_id`、agent name、contract version，但**不得**記錄非必要個資或密鑰。

## 完成定義

新服務不是「模型能回答」就算完成。必須同時具備：契約、Memory、工具權限、錯誤處理、測試、觀測、部署與回滾方式。缺一不可。

## 產出後回報

完成後向使用者摘要：建立/修改了哪些檔案、契約是否有版本變動、目前處於實作順序的哪一步、還缺哪些門檻（尤其真實部署與 E2E），並列出下一步建議。

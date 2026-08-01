# 新增服務 Agent 檢查表

以下用 `cleaning` 作為新服務例子。

## 1. 定義業務邊界

先寫清楚：支援與不支援的需求、完成所需欄位、安全與人工接手條件、可讀資料、可執行動作，以及 `completed` 的精確意義。禁止在這些定義完成前直接把工具全部交給模型。

## 2. 建立目錄

```text
agents/cleaning/
├── __init__.py
├── main.py
├── agent.py
├── workflow.py
├── state.py
├── schemas.py
├── prompts.py
├── knowledge/
└── tools/
```

同步建立：

```text
adapters/agentcore_cleaning.py
adapters/fake_cleaning.py
tests/contract/test_cleaning_contract.py
tests/integration/test_cleaning_handoff.py
```

## 3. 先定義契約

- 優先沿用 `HandoffRequest` 與 `SpecialistResponse`。
- 新增欄位時必須向後相容；破壞性修改要升 `contract_version`。
- `task_id` 在重試時不得改變。
- 專業 Agent 不得把未執行的外部動作宣稱為成功。

## 4. 實作順序

1. schemas 與 state。
2. contract tests。
3. fake adapter。
4. 真實 Agent workflow。
5. Memory。
6. 真實工具與 IAM。
7. Orchestrator registry。
8. 整合與遠端 E2E。

## 5. 環境變數慣例

```text
<SERVICE>_AGENT_MODE=auto|agentcore|fake
<SERVICE>_AGENT_RUNTIME_ARN=arn:...
<SERVICE>_AGENT_QUALIFIER=DEFAULT
<SERVICE>_AGENT_FAKE_FALLBACK=true|false
<SERVICE>_AGENT_MODEL_ID=...
MEMORY_<SERVICE>_AGENT_MEMORY_ID=...
```

正式環境建議明確設為 `agentcore`；若流程包含預約、付款或寫入，fake fallback 必須保持無副作用並清楚標示未完成交易。

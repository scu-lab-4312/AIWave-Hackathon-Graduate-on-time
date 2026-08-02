# /api/chat 整合指南（給外部前端）

本文件說明如何讓「另一個前端」串接目前這套 AI Agent 流程。對外介面是 `frontend/server.py` 提供的 `POST /api/chat`。呼叫這個 endpoint 就會觸發完整的 orchestrator 路由、task state 與專業 Agent（repair / medical / taxi）流程，回傳與內建網頁前端相同的資料格式。

> 本文件描述的是目前程式碼的實際行為。文末「尚未內建、需自行處理」列出串接前必須注意的限制（CORS、認證等），這些目前程式碼還沒有實作。

## 端點

```
POST /api/chat
Content-Type: application/json
```

- 伺服器由 `frontend/server.py`（或 `python frontend.py`）啟動。
- 監聽 `0.0.0.0`，port 由環境變數 `PORT` 決定，預設 `3000`。
- 只支援 `POST /api/chat`；其他路徑會回 404，`GET` 則走靜態檔案服務（內建網頁 UI）。

## 請求格式

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `prompt` | string | 是 | 使用者輸入的訊息，去除前後空白後不可為空。 |
| `session_id` | string | 是 | 對話 session 識別碼，**長度必須 ≥ 33 字元**（建議用 UUID，例如 36 字元）。同一個對話請沿用同一個值，才能延續多輪 task state。 |
| `actor_id` | string | 否 | 使用者識別碼，未提供時預設為 `anonymous`。 |

範例：

```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "我家水管在漏水",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "actor_id": "user-123"
  }'
```

### 關於 `session_id`

- 長度不足 33 字元會被拒絕（回 400）。
- 同一位使用者的連續對話要送同一個 `session_id`，orchestrator 才能記得目前進行中的任務（例如維修估價後接續選擇時段）。
- 建議前端在瀏覽器 `sessionStorage` 產生一次 UUID 後重複使用。

## 回應格式

### 成功（HTTP 200）

回傳 orchestrator `process_turn` 的完整結果，外加後端來源標記。主要欄位：

| 欄位 | 說明 |
| --- | --- |
| `result` | 要顯示給使用者的文字回覆。**這是最基本要呈現的欄位。** |
| `session_id` | 本輪使用的 session id。 |
| `routing` | 路由決策細節（`intent`、`target_agent`、`action`、`reason` 等），除錯用。 |
| `specialist` | 專業 Agent 的完整回應，可能為 `null`（例如平台問答、未支援服務）。 |
| `specialist.data` | 結構化資料，前端用來渲染卡片（見下方）。 |
| `active_task` | 目前進行中的任務狀態，`null` 表示沒有待續任務。 |
| `specialist_backend` | 專業 Agent 實際使用的後端：`agentcore` / `fake` / `fake-fallback`。 |
| `orchestrator_backend` | orchestrator 後端：`local` / `local-fallback` / `agentcore`。 |
| `memory_enabled` | 是否啟用 AgentCore Memory。 |

`specialist.data` 依服務類型可能包含以下清單，供前端渲染選項卡：

- `estimate`：參考估價（`low`、`high`、`basis`、`sample_size`、`disclaimer`）。
- `provider_options`：維修廠商清單（含 `available_slots` 可選時段）。
- `driver_options`：接送司機清單（含 `available_slots`）。
- `pharmacy_options`：藥局聯絡清單（僅公開電話，不建立預約）。

最小可用的前端只需顯示 `result`；要做到跟內建 UI 一樣的卡片，再讀 `specialist.data`。可直接參考 `frontend/web/index.html` 裡 `renderOptions()` 的做法。

成功回應範例（節錄）：

```json
{
  "result": "我幫你找到附近三間水電師傅，也附上參考估價…",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "routing": { "intent": "repair", "target_agent": "repair-agent", "action": "dispatch" },
  "specialist": {
    "data": {
      "estimate": { "low": 800, "high": 2500, "basis": "近期同類案件", "sample_size": 42, "disclaimer": "僅供參考" },
      "provider_options": [ { "name": "…", "available_slots": [ { "slot_id": "…", "start_at": "…" } ] } ]
    }
  },
  "active_task": { "task_id": "…", "target_agent": "repair-agent" },
  "specialist_backend": "fake",
  "orchestrator_backend": "local"
}
```

### 錯誤

| HTTP 狀態 | 回應 | 情況 |
| --- | --- | --- |
| 400 | `{ "error": "..." }` | `prompt` 為空、`session_id` 長度不足、或 JSON 格式錯誤。 |
| 404 | 標準錯誤頁 | 路徑不是 `/api/chat`。 |
| 502 | `{ "error": "Agent 暫時無法回應，請稍後再試。" }` | Agent 呼叫失敗等伺服器端問題。 |

前端建議：非 200 時讀取 `error` 欄位顯示訊息，並保留重試機制。

## 多輪對話流程

1. 首次請求帶 `prompt` + 新產生的 `session_id`。
2. 若回應的 `active_task` 不為 `null`，代表任務尚未完成（例如需要補地區、需要選時段）。
3. 後續請求沿用同一個 `session_id`，orchestrator 會自動接續該任務。
4. 使用者說「取消／不用了」等字眼會結束目前任務。

範例：維修流程中，使用者從 `provider_options[i].available_slots[j]` 選定時段後，前端可送出一段包含 `slot_id` 的 `prompt`（參考 `index.html` 的 slot 按鈕做法）來完成預約。

## 啟動伺服器

本機開發（不需要 AWS 憑證，使用本機 orchestrator 與無副作用的 fake specialist）：

```bash
.venv/bin/python frontend.py
```

改用已部署的 AgentCore orchestrator（需要具 `bedrock-agentcore:InvokeAgentRuntime` 權限的 AWS 憑證）：

```bash
FRONTEND_AGENT_MODE=agentcore \
AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:...' \
.venv/bin/python frontend.py
```

`FRONTEND_AGENT_MODE` 可為 `auto`（預設）/ `agentcore` / `local`。詳見 `README.md`。

## 尚未內建、串接前需自行處理

以下項目目前程式碼**還沒有**實作，另一個前端要正式串接前必須留意：

- **CORS**：`/api/chat` 沒有回傳任何 CORS header，也沒有處理 `OPTIONS` preflight。若新前端是跑在不同網域／port 的瀏覽器頁面，瀏覽器會擋下請求。需要在伺服器加上 `Access-Control-Allow-Origin` 等 header 並處理 preflight，或讓新前端透過自己的後端代理呼叫。
- **認證／授權**：目前完全沒有驗證，且伺服器綁在 `0.0.0.0`，等於同網段任何人都能呼叫。對外開放前應加上 API key 或 token 驗證，並限制來源。
- **Rate limiting**：沒有流量限制，需要時請在前方（反向代理／API gateway）補上。
- **`session_id` 由呼叫端負責**：伺服器只驗證長度 ≥ 33，不會自動產生；請由前端穩定產生並重用。

若需要更完整的對外 API（認證、CORS、版本控管、OpenAPI 文件），建議另外建立獨立的 API 服務，而不是直接把這個 UI proxy 當成公開 API。

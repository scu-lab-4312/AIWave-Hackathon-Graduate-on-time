# Taxi Agent：共享 CMS 司機與 AgentCore 部署紀錄

本文件記錄 2026-08-02 已實際部署並通過兩輪黑箱測試的 Taxi 垂直切片。來源概念來自 `/Users/xxsdd092/Downloads/src/services/taxi_agent.py`，但正式版移除了 process memory session、寫死司機、隨機車牌與「已派車」假結果。

## 已部署資源

| 元件 | AWS 資源 |
| --- | --- |
| 司機主資料 | `hackathon.cms_homepage_service_type_13`（2000 筆，唯讀） |
| Lambda | `taxi-booking` |
| Gateway | `taxi-demo-gateway-un4vnat8uq` |
| Gateway target | `LTW1Q1EX4V` (`taxi-operations`) |
| Taxi Runtime | `taxi_specialist-mKAjnDD2q2`，v1 |
| Orchestrator | `orchestrator-B7uJuFGYRT`，v8 |
| Region / account | `us-west-2` / `377648263536` |

## 資料契約

共享 CMS 表的實際欄位映射如下：

| CMS 欄位 | Agent 欄位 | 用途 |
| --- | --- | --- |
| `id` | `driver_id` | 司機識別碼 |
| `name` | `fleet_name` | 車隊／服務名稱 |
| `driver` | `driver_name` | 司機姓名 |
| `reg_number` | `vehicle_reg_number` | 車牌，不可由模型產生 |
| `rate` | `rating` | 排序與呈現 |
| `county_name` | `city` | 城市媒合條件 |
| `phone` | `phone` | 使用者自行確認聯絡方式 |
| `description` | `description` | 服務說明 |

CMS 沒有行政區與精確地址欄位，所以搜尋只以 `pickup_city` 查詢。`pickup_district` 仍由對話收集並寫入預約請求，精確上車地址與特殊設備由使用者自行致電確認。

Taxi Agent 只擁有兩張輔助表：`agent_taxi_availability` 與 `agent_taxi_bookings`。初始化不得修改 CMS 表；預約狀態只建立為 `REQUESTED`，不得宣稱已確認或已派車。

## Lambda

來源在 `services/taxi_ops/`，Gateway 工具有：

- `get_taxi_options(task_id, city)`：回傳恰好三位司機，每位最多兩個示範時段。
- `create_taxi_booking(...)`：以 `task_id` 為冪等鍵，transaction 鎖定時段後建立 requested 預約。

Lambda 使用 RDS VPC security group，並透過 Secrets Manager VPC endpoint 讀取 `aiwave/hackathon/database-2`。執行角色只需該 secret 的 `GetSecretValue`；不要把 SecretString 寫入設定檔或日誌。

```bash
aws lambda update-function-code \
  --function-name taxi-booking \
  --zip-file fileb:///tmp/taxi-booking.zip \
  --region us-west-2

aws lambda invoke \
  --function-name taxi-booking \
  --cli-binary-format raw-in-base64-out \
  --payload '{"_tool_name":"initialize_taxi_support_data"}' \
  /tmp/taxi-init.json \
  --region us-west-2
```

初始化結果應顯示 `cms_drivers=2000`、`cms_table_modified=false`。直接查詢台北市應回三筆含真實 `driver_name`、`phone`、`vehicle_reg_number` 的資料。

## AgentCore Gateway

Gateway 使用 `AWS_IAM` inbound auth；execution role 只允許 `lambda:InvokeFunction` 到 `taxi-booking`。Target 定義在 `infra/agentcore/taxi-gateway-target.json`。

```bash
aws bedrock-agentcore-control create-gateway \
  --name taxi-demo-gateway \
  --role-arn arn:aws:iam::377648263536:role/taxi-demo-gateway-role \
  --protocol-type MCP \
  --authorizer-type AWS_IAM \
  --region us-west-2

aws bedrock-agentcore-control create-gateway-target \
  --cli-input-json file://infra/agentcore/taxi-gateway-target.json \
  --region us-west-2
```

Runtime role 的 `bedrock-agentcore:InvokeGateway` Resource 必須限制為：

```text
arn:aws:bedrock-agentcore:us-west-2:377648263536:gateway/taxi-demo-gateway-un4vnat8uq
```

## Taxi Runtime

Runtime 入口為 `agents/taxi/main.py`。Linux ARM64 artifact 必須包含 `agents/taxi`、`agents/__init__.py`、`shared` 與 requirements：

```bash
uv pip install \
  --target /tmp/taxi-agent-runtime \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.11 --only-binary=:all: \
  -r agents/taxi/requirements.txt

aws bedrock-agentcore-control create-agent-runtime \
  --agent-runtime-name taxi_specialist \
  --role-arn arn:aws:iam::377648263536:role/taxi-demo-runtime-role \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"HTTP"}' \
  --environment-variables '{"TAXI_GATEWAY_URL":"https://taxi-demo-gateway-un4vnat8uq.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp","TAXI_AGENT_MODEL_ID":"us.anthropic.claude-sonnet-4-6"}' \
  --region us-west-2
```

## 接回 Orchestrator

Orchestrator role 必須同時允許 Runtime ARN 與 DEFAULT endpoint ARN；少一個都可能觸發 fake fallback：

```text
arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/taxi_specialist-mKAjnDD2q2
arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/taxi_specialist-mKAjnDD2q2/runtime-endpoint/DEFAULT
```

Orchestrator 環境變數：

```text
TAXI_AGENT_MODE=agentcore
TAXI_AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/taxi_specialist-mKAjnDD2q2
TAXI_AGENT_FAKE_FALLBACK=true
```

## 上線門檻

1. Lambda 初始化不寫 CMS，查詢固定回三位真實司機。
2. 同一 `task_id` 重送預約回同一 booking code，`idempotent_replay=true`。
3. Taxi Runtime 第一輪為 `awaiting_selection`，第二輪為 `booked`，booking status 為 `requested`。
4. Orchestrator 回 `routing.intent=taxi`、`specialist_backend=agentcore`、`memory_enabled=true`。
5. 第二輪 `sticky_task_id` 等於第一輪 task ID，完成後 `active_task=null`。
6. 使用者畫面顯示三張司機卡片、真實車牌／電話與可選時段，且清楚提示特殊需求須自行致電確認。

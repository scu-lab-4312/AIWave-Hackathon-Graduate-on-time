# Medical Agent：隱私最小化 AWS CLI 部署紀錄

本文件記錄 2026-08-01 已實際部署並驗證的 Medical 垂直流程，可作為下一個唯讀查詢型專業 Agent 的基底。

## 1. 功能與資料邊界

流程只有：

```text
User
  -> Orchestrator medical route / sticky task
  -> Medical AgentCore Runtime
  -> Medical AgentCore Gateway (AWS_IAM, MCP)
  -> medical-db-query Lambda
  -> RDS MySQL medical_pharmacies
  -> 三間虛擬藥局、藥師姓名、虛擬 LINE ID
```

允許跨 Medical 邊界的資料只有 `task_id`、`city`、`district`。系統不詢問、不傳遞、不保存病名、症狀、藥名、劑量、處方、健保資料、電話、Email 或使用者完整地址；不做診斷、用藥建議或預約。

防線不是只靠 prompt：

1. Orchestrator 將原始訊息縮減為城市／行政區後才 handoff。
2. Medical active task 只保存 `city`、`district`。
3. Medical turn 寫入 Orchestrator Memory 時使用 redacted placeholder。
4. Gateway 只公開唯讀 `get_pharmacy_options`。
5. Lambda 拒絕任何額外工具欄位。
6. fake fallback 回 `failed`，不編造聯絡資料。

## 2. 已部署資源（us-west-2）

```text
Lambda:   arn:aws:lambda:us-west-2:377648263536:function:medical-db-query
Gateway:  arn:aws:bedrock-agentcore:us-west-2:377648263536:gateway/medical-demo-gateway-b3u2v4irhq
Target:   UTVWOUQ6WY (medical-pharmacist-contacts)
Runtime:  arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/medical_specialist-UvOi1ZGIfR
Orch:     arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/orchestrator-B7uJuFGYRT (v5)
RDS:      repair-demo-mysql / repair_demo / medical_pharmacies
```

RDS 與 Secret 沿用 Repair 基礎設施，但資料表使用 `medical_` 前綴，不修改 Repair 表。虛擬資料目前包含台北市、新北市、台中市共 12 間藥局。

## 3. Lambda 與 RDS

部署包需包含 `lambda_function.py`、`schema.sql` 與 PyMySQL：

```bash
UV_CACHE_DIR=/tmp/medical-uv-cache uv pip install \
  --target /tmp/medical-lambda-build \
  -r services/medical_ops/requirements.txt

aws lambda update-function-code \
  --function-name medical-db-query \
  --zip-file fileb:///tmp/medical-db-query.zip \
  --region us-west-2
```

Lambda role 最小新增權限是 RDS Secret 的 `secretsmanager:GetSecretValue` 與其 KMS key 的 `kms:Decrypt`。VPC SG 必須同時具備：

- Lambda SG -> RDS SG TCP 3306 egress，RDS SG <- Lambda SG ingress。
- Lambda SG -> Secrets Manager endpoint SG TCP 443 egress，endpoint SG <- Lambda SG ingress。

初始化與直呼驗證：

```bash
aws lambda invoke --function-name medical-db-query \
  --cli-binary-format raw-in-base64-out \
  --payload '{"_tool_name":"initialize_medical_demo_data"}' \
  /tmp/medical-init.json --region us-west-2

aws lambda invoke --function-name medical-db-query \
  --cli-binary-format raw-in-base64-out \
  --payload '{"_tool_name":"get_pharmacy_options","task_id":"verify","city":"台北市","district":"信義區"}' \
  /tmp/medical-options.json --region us-west-2
```

## 4. Gateway

Gateway execution role 只允許 `lambda:InvokeFunction` 到 `medical-db-query`。建立 AWS_IAM MCP Gateway 後，以 [medical-gateway-target.json](../../infra/agentcore/medical-gateway-target.json) 建立 target：

```bash
aws bedrock-agentcore-control create-gateway-target \
  --cli-input-json file://infra/agentcore/medical-gateway-target.json \
  --region us-west-2
```

AgentCore 的 inline tool schema 只接受 `type`、`properties`、`required`、`items`、`description`，不接受 JSON Schema 的 `additionalProperties`；額外欄位限制因此在 Lambda 再強制一次。

## 5. Runtime

CodeZip Runtime 是 Linux ARM64，必須下載 aarch64 manylinux wheels：

```bash
UV_CACHE_DIR=/tmp/medical-runtime-uv-cache uv pip install \
  --target /tmp/medical-runtime-build \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.11 --only-binary=:all: \
  -r agents/medical/requirements.txt
```

把 `agents/medical`、`agents/__init__.py`、`shared` 複製到 build root，再從 build root 執行 zip。務必用 `unzip -l` 確認同時有 entrypoint 與依賴；若不小心從 repo root 壓縮，Runtime 會在 30 秒初始化門檻失敗。

Runtime role 使用 [medical-runtime-policy.json](../../infra/iam/medical-runtime-policy.json)，只允許 Bedrock model、精確 Medical Gateway、logs 與 telemetry。Runtime 環境：

```text
MEDICAL_GATEWAY_URL=https://medical-demo-gateway-b3u2v4irhq.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
MEDICAL_AGENT_MODEL_ID=us.anthropic.claude-sonnet-4-6
```

Medical Runtime 不配置 AgentCore Memory。

## 6. 接回 Orchestrator

Orchestrator role 必須允許 Medical Runtime base ARN 與 DEFAULT endpoint ARN；範本見 [orchestrator-medical-invoke-policy.json](../../infra/iam/orchestrator-medical-invoke-policy.json)。更新 Runtime 時保留 Repair 與 Memory 環境，再加入：

```text
MEDICAL_AGENT_MODE=agentcore
MEDICAL_AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/medical_specialist-UvOi1ZGIfR
MEDICAL_AGENT_FAKE_FALLBACK=true
```

## 7. 必過驗證

1. unit／contract tests：路由、sticky task、輸入最小化、三間資料、拒絕額外欄位、fake 不編造。
2. Lambda direct invoke：回三間；傳 `medication` 等額外欄位則回 `ValueError`。
3. Gateway：`tools/list` 只有 `get_pharmacy_options`，`tools/call` 回三間。
4. Medical Runtime direct invoke：`agent=medical-agent`、`status=completed`、`stage=contacts_ready`、三個 LINE ID。
5. Orchestrator 兩輪：第一輪 `needs_input` 並保存 medical sticky task；第二輪相同 `task_id`、`specialist_backend=agentcore`、三間後 `active_task=null`。
6. 前端顯示三張藥局卡、藥師姓名、LINE ID、虛擬資料與隱私聲明。
7. 測試結束確認本機 port 3000 無 listener。

# Repair Agent：AWS CLI 真實部署範本

這份文件記錄本專案已實際跑通的垂直流程，作為下一個專業服務 Agent 的部署基底。所有 AWS 資源都以 AWS CLI 建立或更新；不依賴 Console 手動設定。

```text
Browser UI
  -> Orchestrator AgentCore Runtime（意圖、sticky task、Memory）
  -> Repair AgentCore Runtime（領域推理、選擇與預訂）
  -> AgentCore Gateway MCP（兩個具 schema 的工具）
  -> Lambda（查詢、估價、交易與冪等）
  -> private RDS for MySQL（虛擬廠商、案件、時段、預訂）
```

fake Repair adapter 只在 Runtime 失敗時提供無副作用回覆，不得寫入資料庫或宣稱預訂成功。正式流量以 response 的 `specialist_backend=agentcore` 為通過條件。

## 1. 本次已部署資源

區域為 `us-west-2`，帳號為 `377648263536`。

| 資源 | 識別碼 |
|---|---|
| RDS MySQL | `repair-demo-mysql` / DB `repair_demo` |
| Lambda | `repair-demo-operations` |
| Gateway | `repair-demo-gateway-o4idvsbeb7` |
| Gateway target | `BA95GV6EHN` (`repair-operations`) |
| Repair Runtime | `repair_specialist-WCdztwHnmX` |
| Orchestrator Runtime | `orchestrator-B7uJuFGYRT` |
| Orchestrator Memory | `orchestrator_mem-8Qfmrh3D5G` |

密碼由 RDS managed master password 存入 Secrets Manager；程式與文件不保存 secret value。RDS 不開 public access，Lambda 透過 security group 連線，Secrets Manager 透過 VPC endpoint 存取。

## 2. 資料與媒合規則

`providers` 不使用經緯度，核心欄位固定為：

```text
id, name, city, district, rating, completed_jobs, is_active
```

媒合先選同 `city + district`，不足時才使用同 `city` 其他行政區，排序再看 rating、completed jobs 與最早時段。每次必須回傳至少三家。估價取相同 issue type 與區域的歷史完工價第 25/75 百分位，資料不足依序退到同城市與全區；它只是參考範圍，不是報價。

資料表與 seed 位於：

- `services/repair_ops/schema.sql`
- `services/repair_ops/lambda_function.py`
- `services/repair_ops/gateway-tools.json`

## 3. RDS 與 Lambda

先建立 VPC security groups、Secrets Manager interface endpoint 與 DB subnet group，再建立 private MySQL：

```bash
aws rds create-db-instance \
  --db-instance-identifier repair-demo-mysql \
  --engine mysql --engine-version 8.0.42 \
  --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp2 \
  --db-name repair_demo --master-username admin \
  --manage-master-user-password \
  --db-subnet-group-name repair-demo-subnets \
  --vpc-security-group-ids "$REPAIR_RDS_SG" \
  --no-publicly-accessible --no-multi-az \
  --backup-retention-period 0 --no-deletion-protection \
  --region us-west-2
```

Lambda role 需要 `AWSLambdaVPCAccessExecutionRole`、目標 RDS secret 的 `secretsmanager:GetSecretValue` 與其 KMS key 的 `kms:Decrypt`。建立函式時傳入 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_SECRET_ARN`，並使用 Lambda security group：

```bash
aws lambda create-function \
  --function-name repair-demo-operations \
  --runtime python3.12 --handler lambda_function.lambda_handler \
  --role "$REPAIR_LAMBDA_ROLE_ARN" \
  --zip-file fileb:///tmp/repair_ops_lambda.zip \
  --timeout 30 --memory-size 256 \
  --vpc-config "SubnetIds=$REPAIR_SUBNETS,SecurityGroupIds=$REPAIR_LAMBDA_SG" \
  --environment "Variables={DB_HOST=$REPAIR_DB_HOST,DB_PORT=3306,DB_NAME=repair_demo,DB_SECRET_ARN=$REPAIR_DB_SECRET_ARN}" \
  --region us-west-2
```

初始化只用虛擬資料：

```bash
aws lambda invoke \
  --function-name repair-demo-operations \
  --cli-binary-format raw-in-base64-out \
  --payload '{"_tool_name":"initialize_demo_data"}' \
  /tmp/repair-seed-response.json \
  --region us-west-2
```

## 4. AgentCore Gateway

Gateway 使用 `AWS_IAM` inbound auth；execution role 只允許 `lambda:InvokeFunction` 到 `repair-demo-operations`。工具定義有：

- `get_repair_options`：唯讀查詢三家廠商與估價。
- `create_repair_booking`：使用 `task_id` 作 idempotency key，在 transaction 中鎖定時段、建立 booking、把時段改為 `BOOKED`。

```bash
aws bedrock-agentcore-control create-gateway \
  --name repair-demo-gateway \
  --role-arn "$REPAIR_GATEWAY_ROLE_ARN" \
  --protocol-type MCP \
  --protocol-configuration 'mcp={supportedVersions=[2025-03-26],instructions="Collect issue type city and district; book only after explicit selection."}' \
  --authorizer-type AWS_IAM \
  --region us-west-2

aws bedrock-agentcore-control create-gateway-target \
  --cli-input-json file://infra/agentcore/repair-gateway-target.json \
  --region us-west-2
```

Repair Runtime role 需要 `bedrock-agentcore:InvokeGateway` 到精確 Gateway ARN；Gateway role 負責呼叫 Lambda。

## 5. 用 AWS CLI 部署 Repair Runtime

Direct code deployment 執行於 Linux ARM64，不能直接把 macOS virtualenv 打包。以下以 uv 下載 aarch64 manylinux wheels：

```bash
mkdir -p /tmp/repair-agent-runtime-build
UV_CACHE_DIR=/tmp/repair-uv-cache uv pip install \
  --target /tmp/repair-agent-runtime-build \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.11 --only-binary=:all: \
  -r agents/repair/requirements.txt
```

把 `agents/repair`、`agents/__init__.py` 與 `shared` 複製到 build root，zip 後上傳 S3。Runtime entry point 是 `agents/repair/main.py`：

```bash
aws s3 cp /tmp/repair-agent-runtime.zip \
  "s3://$REPAIR_ARTIFACT_BUCKET/repair-specialist/deployment.zip" \
  --region us-west-2

aws bedrock-agentcore-control create-agent-runtime \
  --agent-runtime-name repair_specialist \
  --agent-runtime-artifact "{\"codeConfiguration\":{\"code\":{\"s3\":{\"bucket\":\"$REPAIR_ARTIFACT_BUCKET\",\"prefix\":\"repair-specialist/deployment.zip\"}},\"runtime\":\"PYTHON_3_11\",\"entryPoint\":[\"agents/repair/main.py\"]}}" \
  --role-arn "$REPAIR_RUNTIME_ROLE_ARN" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --protocol-configuration '{"serverProtocol":"HTTP"}' \
  --environment-variables "{\"REPAIR_GATEWAY_URL\":\"$REPAIR_GATEWAY_URL\",\"REPAIR_AGENT_MODEL_ID\":\"us.anthropic.claude-sonnet-4-6\"}" \
  --region us-west-2
```

更新既有 Runtime 時使用相同 artifact 結構呼叫 `update-agent-runtime --agent-runtime-id ...`。Runtime role 最少需要 Bedrock model invocation、Gateway invocation、CloudWatch Logs/X-Ray；範本在 `infra/iam/repair-runtime-policy.json`。

## 6. 接回 Orchestrator

Orchestrator execution role 的 `InvokeAgentRuntime` resource 必須同時包含 Runtime ARN 與 DEFAULT endpoint ARN：

```text
arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME_ID
arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME_ID/runtime-endpoint/DEFAULT
```

少了 endpoint ARN 會得到 AccessDenied，若 fallback 開啟則表面仍回 200；因此 E2E 一定要 assert `specialist_backend == "agentcore"`。

更新 Orchestrator 時保留 Memory env，並加入：

```text
REPAIR_AGENT_MODE=agentcore
REPAIR_AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:377648263536:runtime/repair_specialist-WCdztwHnmX
REPAIR_AGENT_FAKE_FALLBACK=true
BEDROCK_AGENTCORE_MEMORY_ID=orchestrator_mem-8Qfmrh3D5G
```

## 7. 必過驗證

1. 直接 invoke Lambda：三家 options、區域排序、估價 sample size。
2. 經 Gateway MCP 呼叫 `tools/list` 與 `tools/call`。
3. 直接 invoke Repair Runtime：`stage=awaiting_selection`，再用同 task 選廠商與時段，得到 booking code。
4. 經 Orchestrator Runtime：`routing.intent=repair`、`specialist_backend=agentcore`、`memory_enabled=true`、`active_task` 保存 estimate/options。
5. 同一 Orchestrator session 第二輪：`sticky_task_id` 不變、`stage=booked`、`active_task=null`。
6. 重送同一 `task_id`：booking code 不變，`idempotent_replay=true`。
7. 前端必須顯示估價卡與恰好三張廠商卡；按鈕送回 provider/slot 選擇。
8. 測試結束確認 demo server port 已關閉：`lsof -nP -iTCP:3000 -sTCP:LISTEN` 無輸出。

本次 2026-08-01 遠端 E2E 已通過：Orchestrator v3 → Repair v3 → Gateway → Lambda → RDS，完成預訂並回傳 booking code；Memory 與 sticky task 同時驗證成功。

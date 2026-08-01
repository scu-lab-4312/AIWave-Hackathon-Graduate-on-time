# Medical Agent

這個 Agent 的範圍刻意很小：只依 `city`、`district` 查詢 `hackathon.cms_homepage_service_type_12`，回傳至少三間藥局的名稱、地址與公開電話，之後由使用者自行聯絡藥局。

它不處理診斷、症狀、藥名、劑量、處方內容、健保資料或預約。Medical Runtime 不配置 Memory；Orchestrator 只把城市與行政區送入 handoff，原始 Medical turn 以 redacted placeholder 寫入 Memory。Lambda 也會拒絕 `task_id`、`city`、`district` 以外的工具參數。

## 結構

```text
agents/medical/
  main.py              # AgentCore HTTP entrypoint
  agent.py             # Strands + Bedrock model
  prompts.py           # 隱私與功能邊界
  schemas.py           # MedicalAssessment / PharmacyOption
  workflow.py          # HandoffRequest -> SpecialistResponse
  tools/gateway.py     # SigV4 MCP Gateway client
services/medical_ops/
  lambda_function.py   # RDS 唯讀查詢
  schema.sql           # 既有 CMS table 欄位契約
  gateway-tools.json   # 唯一的唯讀工具
```

環境變數：

```text
MEDICAL_GATEWAY_URL=https://<gateway-id>.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
MEDICAL_AGENT_MODEL_ID=us.anthropic.claude-sonnet-4-6
```

完整 AWS CLI 部署與驗證紀錄見 [05-medical-aws-cli-deployment.md](../docs/05-medical-aws-cli-deployment.md)。

# 契約、測試與上線門檻

## 測試金字塔

### Unit

- 路由與必要欄位判斷。
- state transition。
- safety rule。
- timeout/error mapping。

### Contract

同一組 request 必須能驗證 fake 與真實 Runtime response：

```python
response = client.invoke(request)
SpecialistResponse.model_validate(response)
assert response.task_id == request.task_id
```

### Integration

- Orchestrator → fake specialist。
- Orchestrator → local real specialist。
- specialist → mock tools。

### Remote E2E

- Orchestrator Runtime → Specialist Runtime。
- 相同 task 的兩輪 Memory。
- IAM 最小權限。
- CloudWatch 中可依 task ID 找到完整 trace。

## 發布門檻

- 所有 contract tests 通過。
- 至少一條 `needs_input → completed` 遠端流程通過。
- 危險案例先輸出安全處置，不提供高風險 DIY 指示。
- 寫入型工具具確認與冪等性。
- AgentCore 故障時不遺失 active task。
- fake fallback 不回報虛構的預約、價格或師傅。
- rollback 方式與前一個 Runtime qualifier/version 已記錄。

## 新服務完成定義

一個新服務不是「模型可以回答」就算完成；必須同時具備契約、Memory、工具權限、錯誤處理、測試、觀測、部署與回滾方式。

# Taxi Agent

這是獨立部署的 AgentCore Taxi 專業 Agent。它保留同伴 `taxi_agent.py` 的多輪需求收集概念，但移除記憶體 session、寫死司機、隨機車牌與假確認結果。

司機主資料唯讀查詢 `hackathon.cms_homepage_service_type_13`；可選時段與預訂存放在 Taxi Agent 擁有的 `agent_taxi_*` 表。Orchestrator 保存 sticky task，真實 Runtime 失敗時 fake fallback 只回失敗，不編造司機或預訂。

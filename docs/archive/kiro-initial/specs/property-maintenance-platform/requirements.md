# 需求文件

## 簡介

本文件定義「AI 驅動的多服務生活代辦平台」的需求。平台連結住戶端（OPEN POINT APP，React Native）與各類服務提供者端（Web Dashboard），透過 AI 完成需求識別、服務媒合、履約追蹤、驗收與付款流程。

平台採「一服務一工作流」架構：每個服務擁有各自獨立的工作流，由一個輕量意圖路由器判斷該啟動哪一條工作流，服務註冊表將服務識別碼映射至對應工作流，跨服務共用能力以巢狀工作流形式被各服務呼叫。

平台的商業模式依賴平台抽成，因此必須以「延後揭露」原則保護交易雙方的聯絡資訊：媒合階段完全匿名，雙方確認後才依宣告的揭露政策交換最小必要欄位。

### 契約引用

本文件不重複定義平台契約。通用對外狀態集合與語意、合法狀態轉換邊、狀態映射規則、Service Manifest 結構、Router 契約、請求信封結構、共用能力清單、不得交由 AI 判斷的決策、Observability 規範與路由品質指標，皆以下列契約檔案為唯一定義來源：

#[[file:../../steering/service-workflow-contract.md]]

本文件僅描述**可測試的驗收標準**，包含三類：對上述契約的符合性條文、跨服務不變式，以及水電維修垂直的服務專屬需求。凡文中出現「契約定義的」字樣，即指向上述契約檔案的對應章節。

### 範圍

- 第一部分為服務無關的平台核心需求，適用於所有已註冊服務。
- 第二部分為第一個服務垂直「水電維修」（service_id = repair_maintenance）的服務專屬需求。
- 第二個服務（AI 預約藥局領藥）不在本次開發範圍，但第一部分的需求必須能在不修改平台核心程式碼的前提下容納該服務。

本文件描述可觀察行為與約束，不描述實作方式。技術架構（Lambda、Bedrock Agents、DynamoDB、RDS、S3、Step Functions 等）將於設計階段定義。

## 名詞定義

### 平台核心

- **Platform**：整個多服務生活代辦平台，包含住戶端、服務提供者端、平台核心與各服務工作流。
- **Resident_App**：住戶端行動應用程式（OPEN POINT APP 內的服務模組）。
- **Resident**：使用平台發起服務請求的一方。
- **Service_Provider**：接受並履行服務請求的一方（水電維修服務中為商家）。
- **Service_Workflow**：單一服務的專屬工作流，輸入為 Service_Request、輸出為 Service_Result。
- **Router**：意圖路由器，接收住戶多模態輸入並輸出 Routing_Result，本身不含任何服務專屬條件判斷邏輯。
- **Routing_Result**：路由結果物件，內容包含 candidates 陣列（每筆含 service_id 與信心值）、初步擷取的 slots、media_refs 與 trace_id。
- **Service_Registry**：服務註冊表，保存所有已註冊服務的 Service_Manifest，並提供候選服務清單給 Router 與 Platform。
- **Service_Manifest**：服務的宣告式描述文件，欄位集合與語意依契約定義。
- **Universal_State**：通用對外狀態，取值集合、語意與正常／例外分類依契約定義。
- **Universal_State_Machine**：管理 Service_Request 之 Universal_State 轉換、合法轉換邊檢查與逾時行為的狀態機。
- **Internal_State**：單一 Service_Workflow 內部定義的狀態，透過 Service_Manifest 的 state_mapping 對應至 Universal_State。
- **Terminal_State**：契約中標記為終態的 Universal_State，即 cancelled、refunded 與 failed。paid 不屬於 Terminal_State。
- **Service_Request**：服務請求信封，所有 Service_Workflow 的標準輸入格式，固定欄位集合依契約定義。
- **Service_Result**：服務結果信封，所有 Service_Workflow 的標準輸出格式，內容為 Service_Request 的固定欄位、最終 Universal_State 與服務專屬結果內容。
- **Envelope_Serializer**：將 Service_Request 與 Service_Result 序列化為 JSON 文件的元件。
- **Envelope_Parser**：將 JSON 文件解析為 Service_Request 與 Service_Result 的元件。
- **Request_Group**：請求群組，當 Routing_Result 的 candidates 有 2 筆或以上達到門檻時建立，彙總所屬各 Service_Request 的 Universal_State。
- **Shared_Capability**：跨服務共用能力，以巢狀工作流形式被各 Service_Workflow 呼叫，包含 Privacy_Gate、Masking_Service、Memory_Service、Payment_Service、Verification_Service、Media_Store 與 Audit_Log。
- **Disclosure_Policy**：揭露政策，於 Service_Manifest 中宣告住戶與 Service_Provider 於各揭露階段各自可取得的欄位集合與揭露方向。
- **Privacy_Gate**：雙向資訊揭露閘門，依 Disclosure_Policy 以確定性程式控制雙方欄位的揭露時機與範圍。
- **Masking_Service**：自動脫敏共用能力，對內容執行 PII 識別、脫敏與脫敏結果驗證。
- **PII_Class**：個資分級，取值為 general 或 sensitive_health。
- **Memory_Service**：Agent 記憶共用能力，管理跨 session 的住戶偏好記憶。
- **Payment_Service**：付款共用能力，處理付款、退款與交易唯一性約束。
- **Verification_Service**：影像驗證共用能力，依 Service_Manifest 宣告的 verification_strategy 比對 Baseline_Media 與 Result_Media。
- **Verification_Report**：驗證報告，由 Verification_Service 產生，內容包含比對結論、已完成項目清單、待確認項目清單與建議結果。
- **Baseline_Media**：基準影像，服務執行前的影像證據。
- **Result_Media**：結果影像，服務執行後的影像證據。
- **Media_Store**：媒體儲存共用能力，保存影像、住戶上傳檔案與 Verification_Report。
- **Audit_Log**：審計日誌共用能力，記錄狀態轉換、個資存取、揭露與金流操作。
- **PII**：個人可識別資訊，包含姓名、電話、地址、身分證號與 Email。
- **Full_Contact_Info**：住戶完整姓名、完整電話與完整地址。
- **District**：台灣行政區（例如「台北市信義區」）。
- **Adjacent_District**：與指定 District 相鄰的行政區，由平台維護的相鄰關係資料定義。
- **Golden_Routing_Set**：路由黃金測試集，每筆包含情境輸入與期望命中的 service_id 集合。
- **Test_Suite**：平台的自動化測試套件，包含單元測試、整合測試與性質測試。

### 水電維修垂直（service_id = repair_maintenance）

- **Recognition_Service**：維修需求多模態識別服務，處理照片、語音與文字輸入。
- **Structured_Request**：維修結構化需求物件，內容包含維修類別、緊急度、預估工時、需求描述與 District，於 Service_Request 中作為 extracted_slots 的內容。
- **Intake_Agent**：報修 AI Agent，以多輪對話收集維修需求並產生 Structured_Request。
- **Inspection_Agent**：驗收 AI Agent，解讀 Verification_Report、產生 Acceptance_Report 並回應住戶的品質詢問。
- **Pricing_Service**：行情防坑服務，依歷史報價產生價格區間並評估報價合理性。
- **Matching_Service**：智慧撮合服務，依服務區域、評價分數與完成率推薦商家。
- **Quote_Service**：報價服務，管理商家報價的建立、盲標隔離與比較。
- **Vendor_Dashboard**：商家端 Web 後台。
- **Masked_Order_View**：僅含脫敏後資料的請求視圖，用於報價階段提供給商家。
- **Acceptance_Report**：驗收報告，由 Inspection_Agent 依 Verification_Report 產生，內容包含比對結論、已完成項目清單、待確認項目清單與建議驗收結果。

---

## 第一部分：平台核心（服務無關）

本部分需求適用於所有已註冊服務，不得包含任何服務專屬邏輯。

### 需求 1：住戶最小化註冊

**使用者故事：** 作為住戶，我希望只提供最少的個人資料就能開始使用平台服務，這樣我可以降低個資外洩的顧慮並快速完成請求。

#### 驗收標準

1. WHEN 住戶提交註冊資料且該資料的姓名去除前後空白後長度為 1 至 50 個字元、性別為 male、female 或 other 之一、District 存在於平台維護的台灣行政區清單，THE Platform SHALL 建立住戶帳號並於 2 秒內回傳全平台唯一的住戶識別碼
2. IF 住戶提交的註冊資料缺少姓名、性別或 District 之任一欄位，或姓名去除前後空白後長度為 0，THEN THE Platform SHALL 拒絕註冊並回傳指出缺少欄位名稱的錯誤訊息
3. IF 住戶提交的姓名去除前後空白後長度超過 50 個字元，或性別不為 male、female、other 之一，THEN THE Platform SHALL 拒絕註冊並回傳指出違規欄位名稱與該欄位允許值範圍的驗證錯誤
4. IF 住戶提交的 District 不存在於平台維護的台灣行政區清單，THEN THE Platform SHALL 拒絕註冊並回傳指出該 District 值無效的行政區錯誤
5. IF 註冊請求所屬的 OPEN POINT APP 帳號已存在對應的住戶帳號，THEN THE Platform SHALL 不建立新的住戶帳號並回傳既有住戶識別碼與帳號已存在提示
6. IF 註冊請求被拒絕，THEN THE Platform SHALL 不建立住戶帳號且不保存該請求提交的姓名、性別與 District
7. THE Platform SHALL 允許電話與地址欄位為空的住戶帳號建立服務請求並完成媒合，且不因缺少電話或地址而中止該流程
8. WHEN 住戶帳號建立完成，THE Platform SHALL 以 AES-256-GCM 加密後儲存住戶姓名與性別，且不以明文形式保存該兩個欄位
9. WHERE 住戶選擇補充電話或地址，THE Platform SHALL 以 AES-256-GCM 加密後儲存所提供的電話與地址，並允許住戶在僅補充其中一個欄位的情況下完成該次補充

### 需求 2：Service Registry 註冊與 Manifest 驗證

**使用者故事：** 作為平台開發者，我希望新增服務只需提交一份通過驗證的宣告檔，這樣我不需要修改 Router 或平台核心程式碼。

#### 驗收標準

1. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證該 Service_Manifest 的 state_mapping 為全函數，即該服務宣告的每一個 Internal_State 恰好對應一個 Universal_State
2. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證契約定義的每一個通用正常狀態至少被該服務的一個 Internal_State 對應
3. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 required_slots 至少包含 1 個 slot 名稱
4. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 state_machine_arn 所指的工作流存在且可被 Platform 啟動
5. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 intent_examples 至少包含 3 筆且 not_this_service 至少包含 3 筆
6. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 min_confidence 為 0 至 1 之間（含端點）的數值
7. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 pii_class 為 general 或 sensitive_health 之一
8. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證 state_timeouts 對契約定義的每一個通用正常狀態宣告逾時秒數與逾時行為，且逾時秒數為大於 0 的整數
9. WHEN Service_Registry 收到服務註冊請求，THE Service_Registry SHALL 驗證該 service_id 未被任何已註冊服務使用
10. IF 服務註冊請求未通過需求 2 第 1 條至第 9 條的任一項驗證，THEN THE Service_Registry SHALL 拒絕該請求、回傳列出所有未通過項目名稱與各自違規欄位路徑的驗證錯誤，且不將該服務寫入 Service_Registry
11. WHEN Service_Manifest 通過需求 2 第 1 條至第 9 條的全部驗證，THE Service_Registry SHALL 寫入該服務並使該服務於 3 秒內出現在提供給 Router 的候選服務清單中
12. WHEN 已註冊服務的 Service_Manifest 被更新，THE Service_Registry SHALL 對更新後的內容重新執行需求 2 第 1 條至第 8 條的驗證
13. IF Service_Manifest 更新內容未通過驗證，THEN THE Service_Registry SHALL 拒絕該更新並保留更新前的 Service_Manifest
14. WHEN Service_Manifest 更新通過驗證，THE Service_Registry SHALL 對該更新完成後啟動的 Service_Request 套用更新後的宣告值，並對更新前已啟動且尚未進入 Terminal_State 的 Service_Request 維持其啟動時的宣告值
15. THE Service_Registry SHALL 排除 is_active 為 false 的服務，使該服務不出現於提供給 Router 的候選服務清單
16. THE Service_Registry SHALL 允許將已註冊服務的 is_active 設為 false 而不刪除該 Service_Manifest
17. THE Service_Registry SHALL 使任一角色皆無法將 Service_Manifest 寫入 Service_Registry 而繞過需求 2 第 1 條至第 9 條的驗證

### 需求 3：意圖路由與分派

**使用者故事：** 作為住戶，我希望用一句話描述需求就被導向正確的服務，這樣我不需要先在 APP 裡找到對應的功能入口。

#### 驗收標準

1. WHEN Router 收到住戶的照片、語音、文字中任一種或多種輸入，THE Router SHALL 產生一份 Routing_Result，內容包含 candidates、初步擷取的 slots、media_refs 與 trace_id
2. THE Router SHALL 使 Routing_Result 的 candidates 為陣列型別，且在僅命中一個服務時該陣列長度為 1
3. THE Router SHALL 使 candidates 中每一筆的信心值為 0 至 1 之間（含端點）的數值
4. WHEN Router 收到住戶輸入，THE Router SHALL 自接收完成起 3 秒內回傳 Routing_Result 或錯誤回應
5. THE Router SHALL 僅從 Service_Registry 取得候選服務清單與各服務的 intent_examples、not_this_service 與 min_confidence，且不包含以 service_id 為條件的判斷邏輯
6. THE Router SHALL 使 candidates 不包含 Service_Registry 中 is_active 為 false 的 service_id
7. IF candidates 中所有 service_id 的信心值皆低於各自於 Service_Manifest 宣告的 min_confidence，THEN THE Router SHALL 不啟動任何 Service_Workflow，並向住戶回傳澄清問題以確認服務意圖
8. WHEN candidates 中恰有 1 筆的信心值達到或超過其 min_confidence，THE Platform SHALL 建立一筆 Service_Request 並啟動該 service_id 對應 state_machine_arn 的 Service_Workflow
9. WHEN candidates 中有 2 筆或以上的信心值達到或超過各自的 min_confidence，THE Platform SHALL 建立一個 Request_Group、為每筆達到門檻的 service_id 各建立一筆 Service_Request，並平行啟動各自的 Service_Workflow
10. THE Platform SHALL 使 Request_Group 的對外狀態為所屬各 Service_Request 之 Universal_State 的彙總，並在所屬全部 Service_Request 皆處於 Terminal_State 時將該 Request_Group 標記為已結束
11. WHEN Platform 依 Routing_Result 啟動 Service_Workflow，THE Platform SHALL 將該 Routing_Result 的 trace_id 寫入所建立的每一筆 Service_Request
12. THE Router SHALL 僅將住戶輸入內容視為待分類資料，且不因該內容中出現的指令性文字而變更所選 service_id、所給信心值或所套用的 min_confidence 門檻
13. IF 住戶輸入所擷取的 slots 未包含該 service_id 於 Service_Manifest 宣告的全部 required_slots，THEN THE Platform SHALL 啟動該 Service_Workflow 並由該工作流針對缺少的 required_slots 向住戶追問
14. IF Router 因 AI 推論服務不可用或超過 3 秒時間上限而無法產生 Routing_Result，THEN THE Router SHALL 回傳可重試的路由失敗錯誤、不啟動任何 Service_Workflow，並保留住戶已提交的輸入內容至少 30 分鐘供重試

### 需求 4：通用狀態機符合性

**使用者故事：** 作為住戶端開發者，我希望所有服務對外只呈現同一組狀態且狀態流轉受確定性檢查約束，這樣新增服務時 APP 不需要修改介面。

#### 驗收標準

1. IF 收到的 Universal_State 轉換請求所指定的原狀態與新狀態組合不屬於契約定義的合法轉換邊，THEN THE Universal_State_Machine SHALL 拒絕該請求、回傳指出原狀態與新狀態的非法轉換錯誤，並保持該 Service_Request 的 Universal_State 不變
2. WHEN Service_Request 的 Internal_State 變更且依 state_mapping 計算所得的 Universal_State 與變更前不同，THE Universal_State_Machine SHALL 對該對通用狀態執行一次合法轉換邊檢查，並僅在檢查通過時同時變更 Internal_State 與 Universal_State
3. WHEN Service_Request 的 Internal_State 變更且依 state_mapping 計算所得的 Universal_State 與變更前相同，THE Universal_State_Machine SHALL 不執行合法轉換邊檢查、允許該 Internal_State 變更，並寫入一筆內部狀態變更紀錄至 Audit_Log
4. WHEN Service_Request 的 Universal_State 變更，THE Universal_State_Machine SHALL 寫入一筆狀態變更紀錄至 Audit_Log，內容包含 request_id、service_id、原 Universal_State、新 Universal_State、對應 Internal_State、觸發者識別碼、trace_id 與變更時間
5. WHERE Service_Request 的 Universal_State 為 created 或 matching，THE Universal_State_Machine SHALL 接受住戶提出的取消請求並將 Universal_State 設為 cancelled
6. IF 住戶在 Service_Request 的 Universal_State 為 confirmed 或其後續狀態時提出取消請求，THEN THE Universal_State_Machine SHALL 拒絕該請求並回傳需透過爭議流程處理的訊息
7. IF 收到以 Terminal_State 為原狀態的 Universal_State 轉換請求且該轉換不屬於契約明列的合法轉換邊，THEN THE Universal_State_Machine SHALL 拒絕該請求並保持 Universal_State 不變
8. THE Universal_State_Machine SHALL 依該服務 Service_Manifest 宣告的 state_timeouts 對每一個 Universal_State 套用逾時秒數
9. IF Service_Request 於某一 Universal_State 停留的時間達到該服務為該狀態宣告的逾時秒數，THEN THE Universal_State_Machine SHALL 執行該狀態宣告的逾時行為並寫入一筆逾時紀錄至 Audit_Log
10. WHEN Service_Request 的 Universal_State 變更，THE Platform SHALL 向該請求的住戶推送狀態變更通知
11. WHILE Service_Request 的 Universal_State 不為 Terminal_State，THE Platform SHALL 使該請求的 Universal_State 與狀態變更紀錄可被該請求的住戶查詢
12. THE Platform SHALL 僅向 Resident_App 與 Service_Provider 端揭露 Universal_State，並使 Internal_State 僅供該 Service_Workflow 內部與 Audit_Log 使用
13. THE Universal_State_Machine SHALL 使轉換合法性判定僅依原狀態、新狀態與觸發者角色決定，且不因住戶或 Service_Provider 提交的文字內容而變更判定結果

### 需求 5：請求信封序列化與解析

**使用者故事：** 作為系統整合者，我希望所有服務工作流使用同一種輸入與輸出信封且序列化行為可預測，這樣平台核心不需要為每個服務撰寫轉換邏輯。

#### 驗收標準

1. THE Envelope_Serializer SHALL 將 Service_Request 與 Service_Result 序列化為 UTF-8 編碼的 JSON 文件
2. WHEN 提供符合契約定義之信封結構的 JSON 文件，THE Envelope_Parser SHALL 解析該文件並產生對應的 Service_Request 或 Service_Result
3. FOR ALL 有效的 Service_Request，先以 Envelope_Serializer 序列化再以 Envelope_Parser 解析所得的物件 SHALL 與原物件的所有欄位值相等，其中相等判定為：字串欄位以 Unicode 碼點序列逐一相等（含中文字元與全形標點）、數值欄位在該欄位宣告精度下相等、null 與空字串不視為相等
4. FOR ALL 可被 Envelope_Parser 成功解析的 JSON 文件，解析後再以 Envelope_Serializer 序列化所得的 JSON 文件 SHALL 與原文件語義等價，其中語義等價判定為：鍵集合相同且每個鍵對應的值相等，欄位順序、縮排與空白字元不影響等價判定
5. IF 提供的 JSON 文件缺少契約定義的必填欄位或欄位型別不符，THEN THE Envelope_Parser SHALL 回傳列出所有違規欄位路徑與各自違規原因的解析錯誤，且不產生任何部分解析結果
6. IF 提供的 JSON 文件包含契約未定義的欄位，THEN THE Envelope_Parser SHALL 忽略該欄位、完成解析，且不回傳錯誤
7. IF 提供的 JSON 文件的 envelope_version 不在 Platform 支援的版本清單內，THEN THE Envelope_Parser SHALL 拒絕該文件並回傳指出版本欄位路徑與該不支援版本值的解析錯誤
8. THE Envelope_Parser SHALL 使欄位值為 null 與欄位值為空字串的解析結果可被區別
9. FOR ALL 有效的 Service_Request，值為 null 的欄位在序列化與解析的往返轉換後 SHALL 仍為 null，值為空字串的欄位在往返轉換後 SHALL 仍為空字串
10. THE Platform SHALL 使 Service_Request 的 extracted_slots 為自由結構欄位，其內容由對應的 Service_Workflow 依 Service_Manifest 的 required_slots 與 optional_slots 驗證

### 需求 6：雙向資訊揭露閘門

**使用者故事：** 作為住戶與 Service_Provider，我希望雙方的聯絡資訊只在確認合作後才依需要交換，這樣任一方都不會在確認前被取得個資。

#### 驗收標準

1. WHILE Service_Request 的 Universal_State 早於 confirmed，THE Privacy_Gate SHALL 拒絕任何 Service_Provider 對該請求 Full_Contact_Info 的讀取請求並回傳權限不足錯誤
2. WHILE Service_Request 的 Universal_State 早於 confirmed，THE Privacy_Gate SHALL 僅向 Service_Provider 提供該服務 Disclosure_Policy 宣告的確認前欄位集合，且不提供該集合以外的欄位
3. WHEN Service_Request 的 Universal_State 轉為 confirmed，THE Privacy_Gate SHALL 依該服務 Service_Manifest 的 disclosure_policy 向住戶提供住戶方應取得的欄位集合，並向已鎖定的 Service_Provider 提供 Service_Provider 方應取得的欄位集合
4. THE Privacy_Gate SHALL 使每次揭露的欄位集合等於 Disclosure_Policy 為該接收方宣告的欄位集合，且不包含該集合以外的欄位
5. THE Privacy_Gate SHALL 依 Disclosure_Policy 宣告的揭露方向執行揭露，並支援單向揭露與雙向揭露兩種宣告
6. THE Privacy_Gate SHALL 僅對已鎖定的 Service_Provider 執行 confirmed 階段的揭露
7. WHILE Service_Request 的 Universal_State 為 confirmed 或其後續狀態，THE Privacy_Gate SHALL 拒絕未被鎖定的 Service_Provider 對該請求任何視圖與任何欄位的讀取請求並回傳權限不足錯誤
8. WHEN Privacy_Gate 執行任一次揭露，THE Audit_Log SHALL 記錄請求者識別碼、請求者角色、request_id、service_id、揭露欄位清單、來源位址、trace_id 與揭露時間
9. THE Privacy_Gate SHALL 以確定性程式判定是否揭露與揭露哪些欄位，且不因住戶或 Service_Provider 提交的文字內容、對話歷史或 AI 產出的建議而變更揭露時機與欄位集合
10. THE Privacy_Gate SHALL 依 Service_Manifest 宣告的 disclosure_policy 執行揭露，且不包含以 service_id 為條件的判斷邏輯

### 需求 7：自動脫敏

**使用者故事：** 作為住戶，我希望我的個資在進入 AI 記憶與 Service_Provider 視圖前被自動脫敏，這樣即使資料被存取也不會暴露我的身分。

#### 驗收標準

1. WHEN Masking_Service 收到含文字內容的脫敏請求，THE Masking_Service SHALL 識別該內容中的姓名、電話、地址、身分證號與 Email
2. WHEN Masking_Service 對姓名執行脫敏，THE Masking_Service SHALL 保留姓氏並以性別稱謂取代名字（例如「王小明」輸出「王先生」）
3. WHEN Masking_Service 對電話執行脫敏，THE Masking_Service SHALL 保留末三碼並以遮罩字元取代其餘數字（例如「0912-345-678」輸出「09XX-XXX-678」）
4. WHEN Masking_Service 對地址執行脫敏，THE Masking_Service SHALL 保留行政區與路名並移除門牌號碼與樓層（例如「台北市信義區松仁路100號5樓」輸出「信義區松仁路一帶」）
5. WHEN Masking_Service 對身分證號執行脫敏，THE Masking_Service SHALL 保留首二碼與末二碼並以遮罩字元取代其餘字元（例如「A123456789」輸出「A1XXXXXX89」）
6. WHEN Masking_Service 對 Email 執行脫敏，THE Masking_Service SHALL 保留本地部分的首字元與末字元及完整網域，並以遮罩字元取代本地部分的其餘字元（例如「john.doe@example.com」輸出「j***e@example.com」）
7. WHEN Masking_Service 完成脫敏規則套用，THE Masking_Service SHALL 對脫敏結果再次執行 PII 識別以驗證該結果
8. IF 需求 7 第 7 條的驗證發現脫敏結果仍含未脫敏的 PII，THEN THE Masking_Service SHALL 對該 PII 執行完全遮罩並寫入一筆強化脫敏事件至 Audit_Log
9. FOR ALL Masking_Service 的輸出，該輸出 SHALL 排除完整電話號碼、完整地址與完整身分證號
10. FOR ALL 輸入文字，THE Masking_Service SHALL 使相同輸入產生相同輸出，且對輸出再次套用脫敏所得結果與單次套用的結果相等
11. WHERE 服務的 pii_class 為 general，THE Masking_Service SHALL 套用需求 7 第 2 條至第 6 條的標準脫敏規則
12. WHERE 服務的 pii_class 為 sensitive_health，THE Masking_Service SHALL 於標準脫敏規則之外額外移除輸出內容中可反推特定健康狀況的內容，包含病名、藥品名稱、劑量與科別
13. THE Masking_Service SHALL 依 Service_Manifest 宣告的 pii_class 選擇脫敏規則集，且不包含以 service_id 為條件的判斷邏輯

### 需求 8：Agent 記憶

**使用者故事：** 作為住戶，我希望 AI 記得我過去的偏好，這樣我不需要每次重複說明相同資訊。

#### 驗收標準

1. WHEN 服務的對話 session 結束，THE Memory_Service SHALL 將該住戶於該服務的偏好摘要寫入對應的 Agent 記憶
2. THE Memory_Service SHALL 在寫入 Agent 記憶前對記憶內容呼叫 Masking_Service 執行脫敏，且不提供繞過脫敏的寫入路徑
3. FOR ALL Agent 記憶項目，該項目的內容 SHALL 排除完整地址、完整電話號碼與完整身分證號
4. WHEN 住戶開啟新的對話 session，THE Platform SHALL 讀取該住戶於該服務的 Agent 記憶並套用於對話回應
5. THE Memory_Service SHALL 於寫入後 90 天刪除需求收集類 Agent 記憶項目
6. THE Memory_Service SHALL 於寫入後 365 天刪除驗收類 Agent 記憶項目
7. WHEN 住戶請求刪除個人記憶，THE Memory_Service SHALL 刪除該住戶於所有服務的全部 Agent 記憶項目並回傳刪除確認

### 需求 9：付款與爭議

**使用者故事：** 作為住戶，我希望服務完成後一鍵完成付款，並在品質有問題時能提出爭議，這樣我的權益有保障。

#### 驗收標準

1. THE Payment_Service SHALL 依 Service_Manifest 宣告的付款觸發時機建立付款交易，且不包含以 service_id 為條件的判斷邏輯
2. WHEN 住戶在 Resident_App 於 Service_Request 的 Universal_State 為 completed 時確認付款且付款交易成功，THE Payment_Service SHALL 依成交金額建立付款交易並將 Universal_State 設為 paid
3. IF 付款交易失敗，THEN THE Payment_Service SHALL 保持該 Service_Request 的 Universal_State 為 completed 並回傳含可重試失敗原因的回應
4. FOR ALL Service_Request，THE Payment_Service SHALL 使該請求的成功付款交易數量不超過 1 筆
5. IF 住戶在 Service_Request 的 Universal_State 為 awaiting_confirm 時提交爭議，THEN THE Universal_State_Machine SHALL 將 Universal_State 設為 disputed 並通知該請求的 Service_Provider 與平台客服
6. IF 住戶在 Service_Request 的 Universal_State 為 confirmed、in_progress、completed 或 paid 時提交爭議，THEN THE Universal_State_Machine SHALL 將 Universal_State 設為 disputed 並通知該請求的 Service_Provider 與平台客服
7. WHILE Service_Request 的 Universal_State 為 disputed，THE Platform SHALL 收集住戶爭議理由、Service_Provider 說明與補充影像並產生爭議摘要
8. WHEN 平台客服裁定爭議結果為重新履約，THE Universal_State_Machine SHALL 將該 Service_Request 的 Universal_State 設為 in_progress
9. WHEN 平台客服裁定爭議結果為爭議不成立，THE Universal_State_Machine SHALL 將該 Service_Request 的 Universal_State 設為 completed
10. WHEN 平台客服裁定爭議結果為退款且該 Service_Request 已存在成功付款交易，THE Payment_Service SHALL 建立退款交易並在退款成功後將 Universal_State 設為 refunded
11. WHEN 付款交易或退款交易的狀態變更，THE Audit_Log SHALL 記錄 request_id、交易識別碼、金額、操作者識別碼、trace_id 與變更時間
12. THE Payment_Service SHALL 以確定性程式判定是否建立付款交易與退款交易，且該判定不因 AI 產出的建議或住戶輸入的文字內容而略過住戶確認步驟
13. WHERE Service_Manifest 的 human_checkpoint_required 為 true，THE Platform SHALL 在該服務宣告的檢核點暫停該 Service_Workflow 直到取得人工核可結果

### 需求 10：影像驗證

**使用者故事：** 作為住戶，我希望不必到場也能確認服務完成品質，這樣我可以遠端完成確認。

#### 驗收標準

1. THE Verification_Service SHALL 依 Service_Manifest 宣告的 verification_strategy 選擇比對方式，且不包含以 service_id 為條件的判斷邏輯
2. WHERE Service_Manifest 的 verification_strategy 為 baseline_vs_result_image，WHEN 該 Service_Request 的 Result_Media 已上傳，THE Verification_Service SHALL 比對該請求的 Baseline_Media 與 Result_Media 並產生 Verification_Report
3. THE Verification_Service SHALL 使 Verification_Report 包含比對結論、已完成項目清單、待確認項目清單與建議確認結果
4. IF verification_strategy 為 baseline_vs_result_image 且該 Service_Request 缺少 Baseline_Media 或 Result_Media，THEN THE Verification_Service SHALL 中止比對並回傳要求缺少影像的一方補件的結果
5. WHERE Service_Manifest 的 verification_strategy 為 none，THE Verification_Service SHALL 跳過影像比對並將驗證結果標記為不適用，且不因缺少影像而使 Service_Workflow 失敗
6. WHEN Verification_Service 產生 Verification_Report，THE Media_Store SHALL 保存該報告並與對應的 Service_Request 關聯
7. WHEN Verification_Service 完成比對，THE Verification_Service SHALL 將比對結果回傳給呼叫端 Service_Workflow 並寫入一筆驗證事件至 Audit_Log

### 需求 11：媒體儲存與生命週期

**使用者故事：** 作為平台經營者，我希望影像依個資分級自動套用不同的保留政策，這樣我可以同時控制儲存成本與符合敏感資料規範。

#### 驗收標準

1. WHEN 住戶或 Service_Provider 上傳影像，THE Media_Store SHALL 依 request_id 與 Baseline_Media 或 Result_Media 分類保存該影像並回傳影像存取識別碼
2. WHERE 服務的 pii_class 為 general，THE Media_Store SHALL 於影像建立後 30 天將該影像轉換為低頻存取儲存層級，並於影像建立後 365 天刪除該影像
3. WHERE 服務的 pii_class 為 sensitive_health，THE Media_Store SHALL 於該 Service_Request 的 Universal_State 進入 completed 後 30 天刪除該影像
4. THE Media_Store SHALL 於未關聯任何 Service_Request 的上傳檔案建立後 7 天刪除該檔案
5. IF 未經授權的請求者請求讀取影像，THEN THE Media_Store SHALL 拒絕該請求並回傳權限不足錯誤
6. WHEN 已授權的請求者請求讀取影像，THE Media_Store SHALL 回傳有效期不超過 3600 秒的臨時存取連結
7. THE Media_Store SHALL 依 Service_Manifest 宣告的 pii_class 決定保留政策，且不包含以 service_id 為條件的判斷邏輯

### 需求 12：安全性與稽核

**使用者故事：** 作為平台經營者，我希望個資受加密保護且所有存取皆可追溯，這樣平台能符合法規並在事件發生時完成調查。

#### 驗收標準

1. THE Platform SHALL 以 AES-256-GCM 加密儲存住戶姓名、電話、地址、身分證號與 Email
2. THE Platform SHALL 由金鑰管理服務保管個資加密金鑰，且不將金鑰內容寫入程式碼、設定檔或日誌
3. WHEN 任何角色讀取解密後的 PII，THE Audit_Log SHALL 記錄請求者識別碼、request_id、欄位清單、來源位址、trace_id 與存取時間
4. THE Audit_Log SHALL 保留紀錄至少 365 天
5. IF API 請求未附帶有效的存取憑證，THEN THE Platform SHALL 拒絕該請求並回傳 401 狀態碼
6. IF 已認證的請求者對不屬於該請求者的 Service_Request 執行操作，THEN THE Platform SHALL 拒絕該請求並回傳 403 狀態碼
7. THE Platform SHALL 使錯誤回應內容排除 PII、堆疊追蹤與內部資源識別資訊
8. WHEN 住戶請求匯出個人資料，THE Platform SHALL 於 30 天內提供該住戶跨所有服務的完整個人資料副本
9. WHEN 住戶請求刪除帳號，THE Platform SHALL 刪除或匿名化該住戶的 PII 並保留不含 PII 的匿名交易統計紀錄
10. THE Platform SHALL 對所有外部 API 端點僅接受 HTTPS 連線
11. THE Platform SHALL 使每一項 Shared_Capability 以巢狀工作流呼叫方式被各 Service_Workflow 使用，且各 Service_Workflow 不包含 Shared_Capability 的重複實作

### 需求 13：跨服務不變式

**使用者故事：** 作為開發團隊成員，我希望平台契約的關鍵約束以可執行性質驗證，這樣新增服務時不會破壞既有保證。

本需求的每一條驗收標準對任意已註冊服務的 Service_Manifest 與任意合法事件序列皆成立。

#### 驗收標準

1. FOR ALL Service_Request 與任意時刻，THE Platform SHALL 使該請求恰好處於一個 Universal_State
2. FOR ALL 已執行的 Universal_State 轉換，THE Universal_State_Machine SHALL 使該轉換為契約定義的合法轉換邊之一，並對不屬於合法轉換邊的請求予以拒絕且保持原 Universal_State 不變
3. FOR ALL 已註冊服務，THE Service_Registry SHALL 使該服務的 state_mapping 為全函數，且契約定義的每一個通用正常狀態至少被該服務的一個 Internal_State 對應
4. FOR ALL 處於 Terminal_State 的 Service_Request，THE Universal_State_Machine SHALL 使不存在任何可成功執行的後續 Universal_State 轉換
5. FOR ALL 已執行的 Universal_State 轉換與 Internal_State 轉換，THE Audit_Log SHALL 存在一筆對應該轉換的審計紀錄
6. FOR ALL Universal_State 早於 confirmed 的 Service_Request，THE Privacy_Gate SHALL 拒絕任何 Service_Provider 對該請求住戶 Full_Contact_Info 的讀取請求
7. FOR ALL 寫入 Agent 記憶的內容，THE Memory_Service SHALL 使該內容不含完整電話號碼、完整地址與完整身分證號
8. FOR ALL Service_Request，THE Payment_Service SHALL 使成功付款交易數量不超過 1 筆
9. FOR ALL 以相同請求識別碼重複送達的操作請求，THE Platform SHALL 回傳首次處理結果且不重複執行該操作

### 需求 14：效能、可靠性與可觀測性

**使用者故事：** 作為住戶與 Service_Provider，我希望平台回應快速且穩定，並在失敗時能被追蹤，這樣緊急需求能及時處理。

#### 驗收標準

1. WHEN Platform 收到 API 請求，THE Platform SHALL 於 2 秒內回傳回應，AI 推論端點不受此條約束
2. WHEN Router 收到住戶輸入，THE Router SHALL 於 3 秒內回傳 Routing_Result 或錯誤回應
3. THE Platform SHALL 在每個日曆月維持 99.9% 或以上的 API 可用性
4. IF 對下游服務的呼叫因暫時性錯誤失敗，THEN THE Platform SHALL 以指數退避方式重試最多 3 次
5. IF 重試次數達上限後呼叫仍失敗，THEN THE Platform SHALL 記錄錯誤並回傳含錯誤代碼的失敗回應
6. IF AI 推論請求超過該端點的時間上限，THEN THE Platform SHALL 中止該請求並回傳逾時錯誤代碼
7. IF Shared_Capability 的巢狀工作流執行失敗，THEN THE Platform SHALL 向呼叫端 Service_Workflow 回傳含錯誤類別、request_id 與 trace_id 的可辨識錯誤結果，且不將該次失敗視為成功
8. THE Platform SHALL 使同一 Routing_Result 所衍生的 Service_Request、Service_Workflow 執行、Lambda 呼叫、Step Functions 執行與 AI 推論呼叫皆傳遞同一 trace_id
9. THE Platform SHALL 使每一條 Service_Workflow 產出名稱為 StateTransitionCount、StateTimeoutCount 與 WorkflowFailureCount 的三個 metric，且每一個 metric 皆以 service_id 作為維度
10. WHEN 同一操作請求以相同請求識別碼重複送達，THE Platform SHALL 回傳首次處理結果且不重複執行該操作

### 需求 15：測試與品質

**使用者故事：** 作為開發團隊成員，我希望平台具備足夠的自動化測試與路由品質量測，這樣變更與新增服務都可以安全地上線。

#### 驗收標準

1. THE Test_Suite SHALL 使整體自動化測試的行覆蓋率達到 90% 或以上
2. THE Test_Suite SHALL 使脫敏、加密、資訊揭露、Universal_State 轉換與 Service_Manifest 驗證邏輯的行覆蓋率達到 100%
3. WHEN Test_Suite 執行涉及雲端服務的測試，THE Test_Suite SHALL 以本地模擬服務取代真實雲端服務呼叫
4. WHEN Test_Suite 執行完畢，THE Test_Suite SHALL 產出覆蓋率報告
5. IF 整體行覆蓋率低於 90%，THEN THE Test_Suite SHALL 以失敗狀態結束並回報實際覆蓋率
6. THE Test_Suite SHALL 對需求 13 所列的 9 條不變式各執行一項性質測試，且該測試對任意合法 Service_Manifest 與任意合法事件序列成立
7. THE Platform SHALL 維護 Golden_Routing_Set，該資料集的每一筆包含情境輸入與期望命中的 service_id 集合
8. WHEN Test_Suite 對 Golden_Routing_Set 執行路由評估，THE Test_Suite SHALL 計算 Recall@3，即期望命中的 service_id 出現於 Routing_Result 前 3 筆 candidates 的比率
9. WHEN Test_Suite 對 Golden_Routing_Set 執行路由評估，THE Test_Suite SHALL 計算 Precision，即 candidates 中屬於期望集合的 service_id 佔全部回傳 service_id 的比率
10. WHEN Test_Suite 對 Golden_Routing_Set 執行路由評估，THE Test_Suite SHALL 計算 Slot completeness，即該服務 required_slots 中被擷取或被追問的 slot 佔全部 required_slots 的比率
11. IF Recall@3 低於 0.9、Precision 低於 0.9 或 Slot completeness 低於 1.0，THEN THE Test_Suite SHALL 以失敗狀態結束並回報未達標的指標名稱與實際值
12. WHEN 新服務註冊至 Service_Registry，THE Test_Suite SHALL 要求 Golden_Routing_Set 包含該 service_id 的正面案例與負面案例各至少 3 筆
13. WHEN 新服務註冊至 Service_Registry，THE Test_Suite SHALL 對 Golden_Routing_Set 中既有服務的案例重新執行路由評估，並在任一既有案例的期望 service_id 不再出現於 Routing_Result 前 3 筆 candidates 時以失敗狀態結束

---

## 第二部分：水電維修垂直（service_id = repair_maintenance）

本部分全部需求僅適用於 service_id = repair_maintenance。

### 需求 16：維修需求多模態識別（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望用照片、語音或文字任意組合描述維修問題，這樣我不需要具備維修專業知識也能說清楚需求。

#### 驗收標準

1. WHEN Recognition_Service 收到包含照片、語音、文字中任一種或多種輸入且所有輸入皆通過格式、數量與大小檢查的需求識別請求，THE Recognition_Service SHALL 產生一份 Structured_Request，內容包含維修類別、緊急度、預估工時與需求描述
2. THE Recognition_Service SHALL 將維修類別設定為平台維修類別清單中的一項或 unknown
3. THE Recognition_Service SHALL 將緊急度設定為 low、medium、high 或 emergency 之一
4. THE Recognition_Service SHALL 將預估工時設定為 0.5 至 40 之間（含端點）且為 0.5 倍數的數值，單位為小時
5. WHEN Recognition_Service 接收完整輸入內容，THE Recognition_Service SHALL 自接收完成起 5 秒內回傳 Structured_Request 或錯誤回應
6. IF 需求識別請求不包含照片、語音、文字中的任何一種輸入，或所含輸入皆為空內容（文字僅含空白字元、檔案大小為 0 位元組），THEN THE Recognition_Service SHALL 拒絕該請求、回傳輸入不足錯誤，且不產生 Structured_Request
7. IF 請求中任一照片檔案格式不在 JPEG、PNG、HEIC 之列，或任一語音檔案格式不在 M4A、MP3、WAV 之列，THEN THE Recognition_Service SHALL 拒絕整個請求、回傳指出違規檔案與允許格式清單的不支援格式錯誤，且不產生 Structured_Request
8. IF 請求中單一上傳檔案大小超過 10 MB，或請求中所有上傳檔案總大小超過 30 MB，THEN THE Recognition_Service SHALL 拒絕整個請求、回傳指出違規檔案與大小上限的檔案過大錯誤，且不產生 Structured_Request
9. IF 請求中照片數量超過 5 張、語音總長度超過 120 秒或文字長度超過 1000 個字元，THEN THE Recognition_Service SHALL 拒絕整個請求、回傳指出超限項目與該項目上限值的輸入超限錯誤，且不產生 Structured_Request
10. WHEN 需求識別請求同時包含照片、語音、文字中的兩種或以上輸入，THE Recognition_Service SHALL 合併全部輸入內容產生單一 Structured_Request，並於不同輸入所得的維修類別或緊急度不一致時以文字輸入的判定為準且在回傳結果中標記衝突欄位名稱
11. IF Recognition_Service 無法從輸入判定維修類別，THEN THE Recognition_Service SHALL 回傳維修類別為 unknown、緊急度為 medium 的 Structured_Request、將該 Structured_Request 標記為待補齊、移交 Intake_Agent 針對維修類別、緊急度與預估工時進行追問，且不建立 Service_Request
12. IF AI 推論服務不可用或單次推論超過 5 秒時間上限，THEN THE Recognition_Service SHALL 回傳標記為 AI 服務降級的 Structured_Request、移交 Intake_Agent 以追問方式收集維修類別、緊急度與預估工時，並保留住戶已上傳的輸入內容至少 30 分鐘供重試

### 需求 17：報修 Agent 多輪對話（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望透過對話補齊維修需求細節，這樣我可以在不填表單的情況下完成報修。

#### 驗收標準

1. WHEN 住戶開啟報修對話且該住戶目前沒有狀態為進行中的報修對話 session，THE Intake_Agent SHALL 建立狀態為進行中的對話 session 並於 3 秒內回傳該 session 的識別碼
2. IF 住戶在已有一個狀態為進行中的報修對話 session 時開啟新的報修對話，THEN THE Intake_Agent SHALL 不建立新 session，並回傳既有 session 識別碼與該 session 已收集的 Structured_Request 內容
3. WHILE 報修對話 session 處於進行中狀態且 Structured_Request 的維修類別、緊急度、預估工時或 District 中存在未確定欄位，THE Intake_Agent SHALL 於每輪回應中針對未確定欄位提出至多 3 個追問問題，且不建立 Service_Request
4. WHEN Structured_Request 的維修類別屬於平台維修類別清單且不為 unknown、緊急度為 low、medium、high 或 emergency 之一、預估工時為 0.5 至 40 之間且為 0.5 倍數的數值、District 屬於平台維護的行政區清單，且住戶確認送出，THE Intake_Agent SHALL 建立一筆 Service_Request、將 Internal_State 設為 pending_quotes、將該 session 狀態設為已完成並回傳 request_id
5. WHEN 住戶在同一進行中的報修對話 session 中傳送變更先前已確定欄位的訊息，THE Intake_Agent SHALL 以最新答覆取代該欄位值並就取代後的欄位值向住戶請求確認
6. IF 住戶在報修對話 session 中連續 30 分鐘未傳送訊息，THEN THE Intake_Agent SHALL 將該 session 狀態設為已過期、保留已收集的 Structured_Request 內容 7 天供住戶恢復，並於保留期滿後刪除該內容
7. WHEN 住戶在 session 狀態設為已過期後 7 天內請求恢復該 session，THE Intake_Agent SHALL 將該 session 狀態設回進行中，並以保留的 Structured_Request 內容續行追問
8. IF 同一報修對話 session 的追問輪數達到 20 輪且仍存在未確定欄位，THEN THE Intake_Agent SHALL 停止提出追問，並向住戶提供以目前已收集內容送出與結束該 session 兩個選項
9. WHEN Intake_Agent 產生對話回應，THE Platform SHALL 將住戶訊息與該回應各寫入一筆對話歷史紀錄，內容包含 session 識別碼、發送者角色、訊息內容與寫入時間，且該紀錄可依時間先後順序查詢

### 需求 18：行情價格區間與防坑標記（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望在收到報價前先知道合理價格範圍，這樣我可以避免被超收費用。

#### 驗收標準

1. WHEN Structured_Request 的維修類別與 District 已確定，THE Pricing_Service SHALL 依該維修類別與該 District 在最近 365 天內的歷史報價紀錄產生價格區間，內容包含下限值、上限值與中位數
2. THE Pricing_Service SHALL 使價格區間的下限值小於或等於中位數，且中位數小於或等於上限值
3. THE Pricing_Service SHALL 使價格區間的下限值、上限值與中位數的幣別為新台幣、精度為整數元，且數值為 1 至 9999999 之間（含端點）
4. WHEN 住戶查詢價格區間，THE Pricing_Service SHALL 於 2 秒內回傳含下限值、上限值、中位數、樣本筆數、資料時間窗與資料來源標記的結果
5. WHEN Pricing_Service 計算價格區間且樣本筆數足以修剪，THE Pricing_Service SHALL 先自樣本中修剪最低 5% 與最高 5% 的離群報價再計算下限值、上限值與中位數
6. IF 樣本筆數不足以修剪最低 5% 與最高 5%，THEN THE Pricing_Service SHALL 不執行修剪並以全部樣本計算下限值、上限值與中位數
7. IF 指定維修類別與 District 在最近 365 天內的歷史報價紀錄少於 5 筆，THEN THE Pricing_Service SHALL 以該維修類別在全體 District 最近 365 天的歷史報價產生價格區間，並將資料來源標記為擴大範圍
8. IF 擴大至全體 District 後可用的歷史報價紀錄仍少於 5 筆，THEN THE Pricing_Service SHALL 不產生價格區間、回傳無行情資料標記，且不對任何報價套用高於行情或低於行情標記
9. WHEN 商家提交的報價金額嚴格大於價格區間上限值，THE Pricing_Service SHALL 在住戶端的該筆報價上標記為高於行情並附上該金額與上限值的差額
10. WHEN 商家提交的報價金額嚴格小於價格區間下限值，THE Pricing_Service SHALL 在住戶端的該筆報價上標記為低於行情
11. WHEN 商家提交的報價金額等於價格區間下限值或上限值，THE Pricing_Service SHALL 將該筆報價標記為符合行情
12. WHEN Service_Request 的 Universal_State 轉為 paid，THE Pricing_Service SHALL 於 60 秒內將該請求的維修類別、District 與成交金額寫入歷史報價紀錄，且該紀錄排除住戶識別碼與所有 PII
13. FOR ALL 歷史報價樣本集合，若將集合中每一筆金額替換為不小於原值的金額，THE Pricing_Service SHALL 使所產生的下限值、上限值與中位數皆不小於替換前的對應值

### 需求 19：商家智慧撮合（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望系統自動推薦合適的商家，這樣我可以取得多方報價並做出選擇。

#### 驗收標準

1. WHEN Internal_State 轉為 pending_quotes，THE Matching_Service SHALL 依商家服務區域、商家評價分數與商家完成率計算推薦分數並產生推薦商家清單
2. THE Matching_Service SHALL 使推薦商家清單至少包含 3 家商家
3. IF 該 Service_Request 的 District 內符合維修類別且處於啟用狀態的商家少於 3 家，THEN THE Matching_Service SHALL 將搜尋範圍擴大至該 District 的 Adjacent_District 以補足至 3 家
4. IF 擴大至 Adjacent_District 後符合條件的商家仍少於 3 家，THEN THE Matching_Service SHALL 回傳所有符合條件的商家並在結果中標記商家數量不足
5. WHEN Matching_Service 收到撮合請求，THE Matching_Service SHALL 於 3 秒內回傳推薦商家清單
6. THE Matching_Service SHALL 使推薦商家清單排除處於停用狀態的商家
7. WHEN 推薦商家清單產生完成，THE Platform SHALL 向清單中每一家商家的 Vendor_Dashboard 發送報價邀請通知
8. THE Matching_Service SHALL 以確定性演算法計算推薦分數，並使該分數的計算輸入僅包含服務區域、評價分數與完成率

### 需求 20：盲標報價與匿名保護（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為平台經營者，我希望商家在報價階段看不到住戶聯絡資訊與其他商家報價，這樣可以防止私下接單與圍標。

#### 驗收標準

1. WHILE Service_Request 的 Universal_State 為 created 或 matching，THE Privacy_Gate SHALL 僅提供 Masked_Order_View 給商家，該視圖包含 District、脫敏後需求描述、維修類別、緊急度與預估工時
2. WHILE Service_Request 的 Universal_State 為 created 或 matching，THE Quote_Service SHALL 僅允許商家讀取該商家自己提交的報價
3. IF 商家請求讀取其他商家在同一 Service_Request 上的報價，THEN THE Quote_Service SHALL 拒絕該請求並回傳權限不足錯誤
4. WHEN 商家提交包含金額、可到場時間與工作說明的報價，THE Quote_Service SHALL 儲存該報價並將 Internal_State 設為 quotes_received
5. IF 商家對同一 Service_Request 重複提交報價，THEN THE Quote_Service SHALL 以最新報價取代先前報價並記錄該報價的修改次數
6. WHEN 商家提交的報價內容包含電話號碼、Email 或社群帳號，THE Quote_Service SHALL 呼叫 Masking_Service 對該內容執行脫敏後再顯示給住戶，並將該事件寫入 Audit_Log
7. WHILE Internal_State 為 quotes_received，THE Platform SHALL 向住戶顯示全部已收到的報價金額與 Pricing_Service 產生的行情標記

### 需求 21：住戶選擇與商家確認（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望在比較報價後選定商家並取得商家確認，這樣雙方在開始施工前已達成合意。

#### 驗收標準

1. WHEN 住戶從報價清單中選定一家商家，THE Platform SHALL 將 Internal_State 設為 vendor_selected 並保持 Universal_State 為 matching
2. IF 住戶在該 Service_Request 收到的報價少於 3 筆時選定商家，THEN THE Platform SHALL 顯示報價數量不足提示，並在住戶再次確認後接受該選擇
3. WHEN 被選定商家確認接單，THE Platform SHALL 將 Internal_State 設為 vendor_confirmed，且該變更使 Universal_State 轉為 confirmed
4. IF 被選定商家在收到選定通知後 24 小時內未確認接單，THEN THE Platform SHALL 將 Internal_State 退回 quotes_received、保持 Universal_State 為 matching、寫入一筆內部狀態變更紀錄至 Audit_Log，並通知住戶重新選擇

### 需求 22：未中選商家通知（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為商家，我希望在請求成交後收到通知，這樣我不會繼續等待已無機會的報價。

#### 驗收標準

1. WHEN Service_Request 的 Universal_State 轉為 confirmed，THE Platform SHALL 通知該請求其餘已報價商家該請求已成交
2. THE Platform SHALL 使需求 22 第 1 條的通知內容排除中選商家的識別資訊與中選報價金額
3. WHILE Service_Request 的 Universal_State 為 confirmed 或其後續狀態，THE Platform SHALL 拒絕未中選商家對該請求任何視圖的讀取請求並回傳權限不足錯誤
4. WHEN Service_Request 的 Universal_State 轉為 paid，THE Platform SHALL 保留該請求的維修類別、District、成交金額與預估工時的匿名統計紀錄
5. THE Platform SHALL 使需求 22 第 4 條的匿名統計紀錄排除住戶識別碼與所有 PII

### 需求 23：施工與遠端驗收（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為住戶，我希望不必到場也能確認維修完成品質，這樣我可以遠端完成驗收。

#### 驗收標準

1. WHEN 被選定商家宣告開始施工且 Internal_State 為 vendor_confirmed，THE Platform SHALL 將 Internal_State 設為 in_progress
2. WHEN 商家上傳完工照片且 Internal_State 為 in_progress，THE Platform SHALL 將該批照片註冊為 Result_Media、將 Internal_State 設為 awaiting_acceptance（Universal_State 轉為 awaiting_confirm），並以該請求的 Baseline_Media 與 Result_Media 呼叫 Verification_Service 執行 baseline_vs_result_image 比對
3. WHEN Verification_Service 回傳 Verification_Report，THE Inspection_Agent SHALL 依該報告產生 Acceptance_Report，內容包含比對結論、已完成項目清單、待確認項目清單與建議驗收結果
4. IF Verification_Service 回傳缺少 Baseline_Media 或 Result_Media 的中止結果，THEN THE Platform SHALL 通知缺少影像的一方補件並保持 Internal_State 為 awaiting_acceptance
5. WHEN 住戶就驗收品質向 Inspection_Agent 提問，THE Inspection_Agent SHALL 依 Acceptance_Report 與 Verification_Report 的比對結果回覆該提問
6. WHEN 住戶確認驗收通過，THE Platform SHALL 將 Internal_State 設為 completed
7. WHEN Internal_State 轉為 completed，THE Platform SHALL 向 Resident_App 推送一鍵付款通知
8. IF Service_Request 於 Universal_State awaiting_confirm 停留達 7 天且住戶未提交驗收結果，THEN THE Platform SHALL 將 Internal_State 設為 completed 並通知住戶已自動驗收

### 需求 24：商家後台（僅適用於 service_id = repair_maintenance）

**使用者故事：** 作為商家，我希望在後台看到可報價訂單與進行中訂單，這樣我可以管理業務。

#### 驗收標準

1. WHEN 商家登入 Vendor_Dashboard，THE Vendor_Dashboard SHALL 顯示該商家的待報價請求清單、進行中請求清單與已完成請求清單
2. THE Vendor_Dashboard SHALL 對待報價請求僅顯示 Masked_Order_View 的欄位
3. WHEN 商家的服務區域或服務類別更新，THE Matching_Service SHALL 在該更新完成後的撮合中套用更新後的服務區域與服務類別
4. WHEN Service_Request 的 Universal_State 轉為 paid，THE Platform SHALL 依該請求的驗收結果與履約時程更新該商家的評價分數與完成率
5. WHEN 商家上傳完工照片，THE Vendor_Dashboard SHALL 顯示上傳結果與 Acceptance_Report 的產生狀態
6. IF 商家提交完工時該請求的完工照片數量少於 1 張，THEN THE Vendor_Dashboard SHALL 拒絕該提交並回傳需上傳完工照片的錯誤訊息

---

## 附錄 A：repair_maintenance Manifest 宣告值

下列為 service_id 為 repair_maintenance 的 Service_Manifest 完整宣告值，欄位語意依契約定義。此宣告為需求層級的契約值，不含實作細節。

```yaml
service_id: repair_maintenance
display_name: 水電維修
is_active: true
state_machine_arn: "<repair-maintenance-workflow-arn>"

intent_examples:
  - 家裡水管漏水，地板都濕了
  - 浴室的燈不會亮，開關按了沒反應
  - 馬桶堵住沖不下去
  - 廚房水龍頭關不緊一直滴水
  - 插座沒電，跳電之後就不能用了
not_this_service:
  - 我想預約去藥局拿慢性病處方藥
  - 我要查我的訂單付款紀錄
  - 幫我叫車去醫院
  - 我想找人打掃家裡

required_slots: [repair_category, urgency, estimated_hours, district]
optional_slots: [preferred_time_window, description, photos, voice_note]

state_mapping:
  pending_quotes: created
  quotes_received: matching
  vendor_selected: matching
  vendor_confirmed: confirmed
  in_progress: in_progress
  awaiting_acceptance: awaiting_confirm
  completed: completed
  paid: paid
  cancelled: cancelled
  disputed: disputed
  refunded: refunded
  failed: failed

state_timeouts:
  created: { seconds: 1800, on_timeout: transition_to_failed }
  matching: { seconds: 86400, on_timeout: return_to_matching_and_notify }
  confirmed: { seconds: 259200, on_timeout: notify_both_parties_stay_confirmed }
  in_progress: { seconds: 604800, on_timeout: notify_platform_support_stay_in_progress }
  awaiting_confirm: { seconds: 604800, on_timeout: auto_complete }
  completed: { seconds: 604800, on_timeout: notify_resident_payment_pending }
  paid: { seconds: 604800, on_timeout: no_action }

matching_strategy: competitive_bidding
pricing_strategy: market_range_bidding
verification_strategy: baseline_vs_result_image

disclosure_policy:
  direction: provider_receives_resident_contact
  before_confirmed:
    to_provider: [district, masked_description, repair_category, urgency, estimated_hours]
    to_resident: [provider_display_name, provider_rating, provider_completion_rate, quote_amount, available_time]
  on_confirmed:
    to_provider: [resident_full_name, resident_phone, resident_address]
    to_resident: [provider_name, provider_phone]

pii_class: general
human_checkpoint_required: false
min_confidence: 0.75
```

### 附錄 A 補充說明

- `state_timeouts.matching` 的 86400 秒對應需求 21 第 4 條的商家 24 小時未確認退回規則。
- `state_timeouts.awaiting_confirm` 的 604800 秒對應需求 23 第 8 條的 7 天自動驗收規則。
- `pii_class` 為 general，因此媒體保留政策採需求 11 第 2 條的 30 天轉低頻存取與 365 天刪除。
- `verification_strategy` 為 baseline_vs_result_image，因此需求 10 第 2 條的比對流程適用，修前照片為 Baseline_Media、修後照片為 Result_Media。
- `min_confidence` 為 0.75，因此 Router 對該服務的信心值低於 0.75 時依需求 3 第 7 條轉為澄清對話。

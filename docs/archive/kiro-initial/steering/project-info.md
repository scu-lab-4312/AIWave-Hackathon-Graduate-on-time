# 專案資訊

## 專案概述

這是一個 Python 團隊協作專案，重視程式碼品質、測試覆蓋率、安全性和效能。

## 技術棧

### 核心技術
- **語言**: Python 3.x
- **雲端平台**: AWS
- **測試框架**: pytest
- **程式碼品質工具**: black, isort, mypy, pylint/ruff

### AWS 服務
本專案使用以下 AWS 服務：
- **S3**: 物件儲存
- **DynamoDB**: NoSQL 資料庫
- **Secrets Manager**: 敏感資料管理
- **Lambda**: 無伺服器運算（視需求）
- **其他服務**: 根據專案需求使用

## 專案結構

推薦的目錄結構：

```
project/
├── .kiro/                  # Kiro 配置
│   ├── hooks/             # Agent hooks
│   └── steering/          # 編碼規範和指南
├── src/                   # 原始碼
│   ├── models/           # 資料模型
│   ├── services/         # 業務邏輯
│   ├── repositories/     # 資料存取層
│   ├── api/             # API endpoints
│   └── utils/           # 工具函數
├── tests/                # 測試檔案
│   ├── unit/            # 單元測試
│   ├── integration/     # 整合測試
│   └── aws/             # AWS 相關測試
├── config/               # 配置檔案
├── scripts/              # 部署和維護腳本
├── .env.example         # 環境變數範本
├── .gitignore           # Git 忽略清單
├── requirements.txt     # Python 依賴
└── README.md            # 專案說明
```

## 開發流程

### 1. 本地開發設定
```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安裝依賴
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 複製環境變數範本
cp .env.example .env
# 編輯 .env 填入實際的配置

# 執行測試確認環境正常
pytest
```

### 2. 開發新功能
1. 建立新分支: `git checkout -b feature/功能名稱`
2. **先寫測試**（TDD 方式）
3. 實作功能
4. 確保測試通過: `pytest`
5. 檢查程式碼品質:
   ```bash
   black .
   isort .
   mypy src/
   pylint src/
   ```
6. 提交變更: `git commit -m "feat: 功能描述"`
7. 推送並建立 PR

### 3. Code Review 檢查項目
- [ ] 所有測試通過
- [ ] 測試覆蓋率達標（≥80%）
- [ ] 遵循編碼規範
- [ ] 有適當的錯誤處理
- [ ] 敏感資料不硬編碼
- [ ] AWS 操作有完整錯誤處理
- [ ] 有必要的註解和 docstring

## 重要原則

### 開發優先順序
1. **可讀性** - 程式碼要讓團隊成員容易理解
2. **效能** - 在不犧牲可讀性的前提下優化
3. **簡潔性** - 避免過度設計

### 測試要求
- 每個功能都必須有測試
- 新功能使用 TDD 開發
- Bug 修復先寫測試重現問題
- 最低測試覆蓋率 80%

### 安全性
- 絕不硬編碼敏感資料
- 所有輸入都要驗證
- 使用參數化查詢防止 SQL injection
- AWS 資源使用最小權限原則

### AWS 使用
- 優先使用 AWS CLI 進行資源管理
- 所有 AWS 操作都要有錯誤處理
- 敏感資料使用 Secrets Manager
- 開發時使用 moto/localstack 測試

## 常用指令

### 測試
```bash
# 執行所有測試
pytest

# 執行特定測試
pytest tests/unit/test_services/

# 顯示覆蓋率
pytest --cov=src --cov-report=html

# 只執行失敗的測試
pytest --lf
```

### 程式碼品質
```bash
# 格式化程式碼
black .
isort .

# 型別檢查
mypy src/

# 程式碼檢查
pylint src/
# 或
ruff check .
```

### AWS CLI
```bash
# 檢查當前身份
aws sts get-caller-identity

# 列出 S3 buckets
aws s3 ls

# 取得 secret
aws secretsmanager get-secret-value --secret-id my-secret
```

## 團隊協作

### Git 提交訊息規範
使用 Conventional Commits 格式：
- `feat:` 新功能
- `fix:` Bug 修復
- `docs:` 文件更新
- `style:` 程式碼格式調整（不影響功能）
- `refactor:` 重構
- `test:` 測試相關
- `chore:` 建置工具或輔助工具變更

範例：
```
feat: 新增用戶註冊功能

- 實作用戶註冊 API
- 新增 email 驗證
- 包含完整的單元測試和整合測試

Closes #123
```

### 分支策略
- `main`: 生產環境分支（受保護）
- `develop`: 開發分支
- `feature/*`: 功能開發分支
- `bugfix/*`: Bug 修復分支
- `hotfix/*`: 緊急修復分支

## 環境變數

### 必要的環境變數
```bash
# 資料庫
DATABASE_URL=postgresql://user:pass@host/db

# 安全性
SECRET_KEY=your-secret-key-32-chars-min
JWT_SECRET=your-jwt-secret-32-chars-min

# AWS
AWS_REGION=ap-northeast-1
AWS_ACCESS_KEY_ID=your-key  # 或使用 IAM role
AWS_SECRET_ACCESS_KEY=your-secret  # 或使用 IAM role

# 環境識別
ENVIRONMENT=development  # development, staging, production
DEBUG=false  # 生產環境必須為 false
```

## 相關文件

專案的詳細規範請參考 `.kiro/steering/` 目錄：
- `coding-standards.md` - Python 編碼規範
- `testing-requirements.md` - 測試要求和最佳實踐
- `aws-guidelines.md` - AWS 使用指南
- `security-guidelines.md` - 安全性規範

## 聯絡資訊

- **技術文件**: 查看 `.kiro/steering/` 中的各項指南
- **問題回報**: 使用 GitHub Issues
- **團隊討論**: [填入你的團隊溝通管道]

## 參考資源

### Python 相關
- [Python 官方文檔](https://docs.python.org/3/)
- [PEP 8 風格指南](https://pep8.org/)
- [pytest 文檔](https://docs.pytest.org/)

### AWS 相關
- [AWS CLI 文檔](https://docs.aws.amazon.com/cli/)
- [Boto3 文檔](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [AWS 最佳實踐](https://aws.amazon.com/architecture/well-architected/)

### 安全性
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python 安全性最佳實踐](https://python.readthedocs.io/en/latest/library/security_warnings.html)

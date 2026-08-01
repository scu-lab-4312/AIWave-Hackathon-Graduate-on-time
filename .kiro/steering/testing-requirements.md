# 測試要求

## 核心原則

**每個功能都必須有測試** - 沒有例外

- 新功能：在實作前先寫測試（TDD 優先）
- Bug 修復：先寫重現 bug 的測試，再修復
- 重構：確保所有測試通過後才能合併

## 測試覆蓋率要求

### 最低標準
- **整體覆蓋率**: ≥ 80%
- **新增程式碼**: ≥ 90%
- **關鍵業務邏輯**: 100%
- **AWS 整合功能**: ≥ 85%

### 關鍵業務邏輯包含
- 認證和授權
- 金流處理
- 資料驗證
- AWS 資源操作
- 資料庫事務

## 測試類型

### 1. 單元測試 (Unit Tests)
**目的**: 測試單一函數或類別的行為

```python
# tests/test_services/test_user_service.py
import pytest
from src.services.user_service import UserService
from src.models.user import User

class TestUserService:
    """測試用戶服務的所有功能。"""
    
    def test_create_user_success(self):
        """測試成功建立用戶。"""
        # Arrange - 準備測試資料
        service = UserService()
        user_data = {
            "username": "testuser",
            "email": "test@example.com"
        }
        
        # Act - 執行要測試的功能
        result = service.create_user(user_data)
        
        # Assert - 驗證結果
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert result.id is not None
    
    def test_create_user_duplicate_email_raises_error(self):
        """測試重複 email 應該拋出錯誤。"""
        service = UserService()
        user_data = {"username": "user1", "email": "same@example.com"}
        
        service.create_user(user_data)
        
        # 應該拋出 DuplicateEmailError
        with pytest.raises(DuplicateEmailError) as exc_info:
            service.create_user(user_data)
        
        assert "email already exists" in str(exc_info.value).lower()
```

### 2. 整合測試 (Integration Tests)
**目的**: 測試多個元件之間的互動

```python
# tests/integration/test_user_flow.py
import pytest
from tests.fixtures import test_database, test_aws_client

@pytest.mark.integration
class TestUserRegistrationFlow:
    """測試完整的用戶註冊流程。"""
    
    def test_complete_registration_flow(self, test_database, test_aws_client):
        """測試從註冊到發送歡迎郵件的完整流程。"""
        # 1. 註冊用戶
        response = client.post("/api/users/register", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "SecurePass123!"
        })
        assert response.status_code == 201
        user_id = response.json()["user_id"]
        
        # 2. 驗證資料庫中的用戶
        user = test_database.query(User).filter_by(id=user_id).first()
        assert user is not None
        assert user.email_verified is False
        
        # 3. 驗證發送了驗證郵件（檢查 SES）
        sent_emails = test_aws_client.get_sent_emails()
        assert len(sent_emails) == 1
        assert sent_emails[0]["to"] == "new@example.com"
        assert "驗證" in sent_emails[0]["subject"]
```

### 3. AWS 整合測試
**使用 moto 或 localstack 進行本地測試**

```python
# tests/test_aws/test_s3_service.py
import pytest
from moto import mock_s3
import boto3
from src.services.s3_service import S3Service

@mock_s3
class TestS3Service:
    """測試 S3 服務功能。"""
    
    def test_upload_file_to_s3(self):
        """測試上傳檔案到 S3。"""
        # 建立 mock S3 bucket
        s3_client = boto3.client("s3", region_name="ap-northeast-1")
        s3_client.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"}
        )
        
        # 測試上傳
        service = S3Service(bucket_name="test-bucket")
        result = service.upload_file(
            file_content=b"test content",
            file_name="test.txt"
        )
        
        assert result["success"] is True
        assert "test.txt" in result["s3_url"]
        
        # 驗證檔案確實存在
        obj = s3_client.get_object(Bucket="test-bucket", Key="test.txt")
        assert obj["Body"].read() == b"test content"
    
    def test_upload_file_handles_permission_error(self):
        """測試處理 S3 權限錯誤。"""
        # 不建立 bucket，模擬權限錯誤
        service = S3Service(bucket_name="nonexistent-bucket")
        
        with pytest.raises(S3PermissionError):
            service.upload_file(b"content", "test.txt")
```

## 測試命名規範

### 函數命名
```python
# 格式: test_<功能>_<情境>_<預期結果>

def test_calculate_discount_with_valid_coupon_returns_discounted_price():
    """使用有效優惠券應該返回折扣後價格。"""
    pass

def test_authenticate_user_with_invalid_password_raises_auth_error():
    """使用錯誤密碼應該拋出認證錯誤。"""
    pass

def test_fetch_user_data_when_user_not_found_returns_none():
    """當用戶不存在時應該返回 None。"""
    pass
```

### 類別命名
```python
# 格式: Test<要測試的類別或模組名稱>

class TestUserService:
    """測試 UserService 的所有功能。"""
    pass

class TestPaymentProcessor:
    """測試付款處理器。"""
    pass
```

## Fixtures 和 Mocking

### 使用 pytest fixtures
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.base import Base

@pytest.fixture
def test_database():
    """建立測試用的記憶體資料庫。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture
def mock_aws_client():
    """Mock AWS 客戶端。"""
    with mock_aws():
        yield boto3.client("s3")
```

### Mocking 外部依賴
```python
from unittest.mock import patch, MagicMock

def test_send_notification_calls_sns(mock_sns_client):
    """測試發送通知會呼叫 SNS。"""
    with patch("boto3.client") as mock_boto:
        mock_sns = MagicMock()
        mock_boto.return_value = mock_sns
        
        service = NotificationService()
        service.send_notification("test message")
        
        # 驗證呼叫了正確的 SNS API
        mock_sns.publish.assert_called_once()
        call_args = mock_sns.publish.call_args
        assert call_args[1]["Message"] == "test message"
```

## 測試組織結構

```
tests/
├── conftest.py              # 共用 fixtures
├── unit/                    # 單元測試
│   ├── test_services/
│   ├── test_models/
│   └── test_utils/
├── integration/             # 整合測試
│   ├── test_api/
│   └── test_workflows/
├── aws/                     # AWS 相關測試
│   ├── test_s3_service.py
│   ├── test_dynamodb_service.py
│   └── test_lambda_handlers.py
└── fixtures/                # 測試資料
    ├── sample_users.json
    └── mock_responses.py
```

## 執行測試

### 本地開發
```bash
# 執行所有測試
pytest

# 執行特定檔案
pytest tests/unit/test_services/test_user_service.py

# 執行特定測試
pytest tests/unit/test_services/test_user_service.py::TestUserService::test_create_user_success

# 顯示覆蓋率報告
pytest --cov=src --cov-report=html

# 只執行單元測試（快速）
pytest tests/unit/

# 執行整合測試（較慢）
pytest tests/integration/ -v
```

### CI/CD Pipeline
```bash
# 執行所有測試並產生報告
pytest --cov=src --cov-report=xml --cov-report=term -v

# 檢查覆蓋率是否達標
pytest --cov=src --cov-fail-under=80
```

## 測試最佳實踐

### ✅ DO
1. **測試應該獨立**: 每個測試不應該依賴其他測試的結果
2. **使用描述性名稱**: 測試名稱應該清楚說明測試什麼
3. **AAA 模式**: Arrange（準備）、Act（執行）、Assert（驗證）
4. **一個測試一個斷言概念**: 測試一個具體的行為或情境
5. **測試邊界條件**: 空值、最大值、最小值、錯誤輸入
6. **Mock 外部服務**: 不要在測試中呼叫真實的 AWS 服務或外部 API

### ❌ DON'T
1. **不要測試實作細節**: 測試行為而非內部實作
2. **不要忽略失敗的測試**: 修復或更新測試，不要註解掉
3. **不要過度 Mock**: 只 Mock 外部依賴，不要 Mock 自己的程式碼
4. **不要寫脆弱的測試**: 避免依賴特定的執行順序或時間
5. **不要跳過測試**: 使用 `@pytest.mark.skip` 需要有正當理由並註明

## 範例：完整的測試檔案

```python
# tests/unit/test_services/test_payment_service.py
"""測試付款服務的所有功能。

這個模組測試付款處理的核心邏輯，包含：
- 付款驗證
- 金額計算
- 交易記錄
- 錯誤處理
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
from src.services.payment_service import PaymentService
from src.models.payment import Payment, PaymentStatus
from src.exceptions import InvalidAmountError, PaymentProcessingError

class TestPaymentService:
    """測試 PaymentService 類別。"""
    
    @pytest.fixture
    def payment_service(self, test_database):
        """建立測試用的付款服務實例。"""
        return PaymentService(db_session=test_database)
    
    @pytest.fixture
    def valid_payment_data(self):
        """準備有效的付款資料。"""
        return {
            "amount": Decimal("100.00"),
            "currency": "TWD",
            "user_id": "user123",
            "description": "測試付款"
        }
    
    def test_process_payment_success(self, payment_service, valid_payment_data):
        """測試成功處理付款。"""
        # Act
        result = payment_service.process_payment(valid_payment_data)
        
        # Assert
        assert result.status == PaymentStatus.COMPLETED
        assert result.amount == Decimal("100.00")
        assert result.transaction_id is not None
    
    def test_process_payment_with_negative_amount_raises_error(
        self, payment_service, valid_payment_data
    ):
        """測試負數金額應該拋出錯誤。"""
        valid_payment_data["amount"] = Decimal("-10.00")
        
        with pytest.raises(InvalidAmountError) as exc_info:
            payment_service.process_payment(valid_payment_data)
        
        assert "金額必須大於零" in str(exc_info.value)
    
    @pytest.mark.parametrize("amount,expected_fee", [
        (Decimal("100.00"), Decimal("3.00")),    # 3% 手續費
        (Decimal("1000.00"), Decimal("30.00")),
        (Decimal("50.00"), Decimal("1.50")),
    ])
    def test_calculate_transaction_fee(
        self, payment_service, amount, expected_fee
    ):
        """測試計算交易手續費。"""
        fee = payment_service.calculate_transaction_fee(amount)
        assert fee == expected_fee
    
    @patch("src.services.payment_service.payment_gateway")
    def test_process_payment_handles_gateway_failure(
        self, mock_gateway, payment_service, valid_payment_data
    ):
        """測試處理付款閘道失敗的情況。"""
        # Arrange - 模擬閘道失敗
        mock_gateway.charge.side_effect = Exception("Gateway timeout")
        
        # Act & Assert
        with pytest.raises(PaymentProcessingError) as exc_info:
            payment_service.process_payment(valid_payment_data)
        
        assert "付款閘道錯誤" in str(exc_info.value)
        
        # 驗證付款狀態被標記為失敗
        payment = payment_service.get_payment(exc_info.value.payment_id)
        assert payment.status == PaymentStatus.FAILED
```

## PR 檢查清單

提交 PR 前確認：
- [ ] 所有新增的函數都有對應的測試
- [ ] 測試覆蓋率達到要求（≥80%）
- [ ] 所有測試都通過（`pytest` 無失敗）
- [ ] AWS 相關功能使用 moto/localstack 測試
- [ ] 沒有被跳過的測試（除非有正當理由）
- [ ] 測試命名清楚且有 docstring
- [ ] 使用適當的 fixtures 和 mocking

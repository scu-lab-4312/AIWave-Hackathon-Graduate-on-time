# Python 編碼規範

## 基本原則

**優先順序：** 可讀性 > 效能 > 簡潔性

- 程式碼應該讓團隊成員一眼就能理解
- 只在瓶頸處優化效能，並加上註解說明原因
- 避免過度抽象和炫技

## 命名規範

### 變數和函數
```python
# ✅ 好的命名 - 清楚表達意圖
user_authentication_result = authenticate_user(username, password)
is_valid_email = validate_email_format(email)

# ❌ 避免縮寫和不清楚的命名
res = auth(u, p)
valid = check(e)
```

### 類別和模組
```python
# 類別：PascalCase
class UserAuthenticationService:
    pass

# 模組和檔案：snake_case
# user_authentication_service.py
```

### 常數
```python
# 全大寫加底線
MAX_RETRY_ATTEMPTS = 3
AWS_DEFAULT_REGION = "ap-northeast-1"
```

## 程式碼風格

### 使用 Type Hints
```python
# ✅ 所有函數都要有型別標註
def calculate_total_price(
    items: list[dict[str, Any]],
    discount_rate: float = 0.0
) -> Decimal:
    """計算總價格，考慮折扣。
    
    Args:
        items: 商品清單，每個商品包含 price 和 quantity
        discount_rate: 折扣率，範圍 0.0-1.0
        
    Returns:
        計算後的總價格
        
    Raises:
        ValueError: 當折扣率不在有效範圍時
    """
    if not 0.0 <= discount_rate <= 1.0:
        raise ValueError(f"折扣率必須在 0-1 之間: {discount_rate}")
    
    total = sum(
        Decimal(str(item["price"])) * item["quantity"]
        for item in items
    )
    return total * (Decimal("1.0") - Decimal(str(discount_rate)))
```

### Docstring 規範
- 所有 public 函數和類別都要有 docstring
- 使用 Google style docstring
- 中文或英文皆可，但同一個檔案要統一
- 必須包含：功能說明、參數、回傳值、可能的例外

### 錯誤處理
```python
# ✅ 具體的例外處理
try:
    user_data = fetch_user_from_database(user_id)
except DatabaseConnectionError as e:
    logger.error(f"資料庫連線失敗: {e}", exc_info=True)
    raise ServiceUnavailableError("暫時無法取得用戶資料") from e
except UserNotFoundError:
    logger.warning(f"找不到用戶: {user_id}")
    return None

# ❌ 避免捕捉所有例外
try:
    do_something()
except Exception:  # 太廣泛
    pass
```

### 日誌記錄
```python
import logging

logger = logging.getLogger(__name__)

# 使用適當的日誌級別
logger.debug("詳細的除錯資訊")  # 開發時使用
logger.info("正常的操作資訊")   # 重要的業務流程
logger.warning("警告但不影響運作")  # 需要注意的情況
logger.error("錯誤需要處理", exc_info=True)  # 錯誤要包含 stack trace
logger.critical("嚴重錯誤導致系統無法運作")  # 系統級問題
```

## 效能最佳化原則

### 1. 先保證正確性和可讀性
```python
# ✅ 清楚但可能不是最快
def find_active_users(users: list[User]) -> list[User]:
    """找出所有活躍用戶。"""
    return [user for user in users if user.is_active]

# 如果效能確實成為瓶頸，再優化並加註解
def find_active_users_optimized(users: list[User]) -> list[User]:
    """找出所有活躍用戶。
    
    效能優化：使用 filter + tuple 避免建立中間 list
    基準測試顯示在 100K+ 用戶時有 30% 效能提升
    """
    return list(filter(lambda u: u.is_active, users))
```

### 2. 使用適當的資料結構
```python
# ✅ 需要快速查找時使用 set 或 dict
valid_user_ids = set(user_ids)  # O(1) lookup
if user_id in valid_user_ids:
    process_user(user_id)

# ❌ 在大型 list 中查找
if user_id in user_ids_list:  # O(n) lookup
    process_user(user_id)
```

### 3. 避免不必要的資料庫查詢
```python
# ✅ 使用 batch 查詢
user_ids = [order.user_id for order in orders]
users = User.objects.filter(id__in=user_ids)  # 一次查詢
user_map = {user.id: user for user in users}

# ❌ N+1 查詢問題
for order in orders:
    user = User.objects.get(id=order.user_id)  # N 次查詢
```

## 程式碼組織

### 檔案結構
```
project/
├── src/
│   ├── models/          # 資料模型
│   ├── services/        # 業務邏輯
│   ├── repositories/    # 資料存取層
│   ├── api/            # API endpoints
│   └── utils/          # 工具函數
├── tests/              # 測試檔案（鏡像 src 結構）
├── config/             # 配置檔案
└── scripts/            # 部署和維護腳本
```

### Import 順序
```python
# 1. 標準庫
import os
import sys
from datetime import datetime
from typing import Any, Optional

# 2. 第三方套件
import boto3
import pytest
from fastapi import FastAPI

# 3. 本地模組
from src.models.user import User
from src.services.auth import AuthService
```

## 工具要求

### 必須使用的工具
- **Black**: 程式碼格式化
- **isort**: import 排序
- **mypy**: 型別檢查
- **pylint** 或 **ruff**: 程式碼檢查
- **pytest**: 測試框架

### Pre-commit Hook
專案應該要有 `.pre-commit-config.yaml` 確保程式碼品質。

## 注意事項

1. **每個 PR 都要經過 code review**
2. **不要提交未格式化的程式碼**（使用 black 和 isort）
3. **不要忽略 type checker 的警告**
4. **效能優化要有數據支持**（benchmark 結果）
5. **複雜的邏輯要有註解說明為什麼這樣做**

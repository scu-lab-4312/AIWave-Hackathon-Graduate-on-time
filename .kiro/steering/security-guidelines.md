# 安全性指南

## 核心原則

**安全性是每個人的責任** - 不是可選項

- 預設安全：所有功能從最嚴格的安全設定開始
- 深度防禦：多層次的安全控制
- 最小權限：只給予完成任務所需的最小權限
- 審計追蹤：記錄所有關鍵操作

## 敏感資料處理

### 1. 絕對不要硬編碼敏感資料

```python
# ❌ 絕對禁止
API_KEY = "sk-1234567890abcdef"
DATABASE_PASSWORD = "MyPassword123"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# ✅ 正確做法 - 使用環境變數
import os

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY 環境變數未設定")

# ✅ 正確做法 - 使用 AWS Secrets Manager
from src.services.secrets_service import SecretsService

secrets = SecretsService()
db_credentials = secrets.get_secret("prod/database/credentials")
DATABASE_PASSWORD = db_credentials["password"]
```

### 2. 環境變數管理

```python
# config/settings.py
"""應用程式配置管理。

所有敏感配置都應該透過環境變數載入，絕不硬編碼。
"""
import os
from typing import Optional

class Settings:
    """應用程式設定類別。"""
    
    # 資料庫設定
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")
    
    # AWS 設定
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-1")
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    # API Keys
    THIRD_PARTY_API_KEY: str = os.getenv("THIRD_PARTY_API_KEY", "")
    
    # 安全性設定
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    
    # 環境識別
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    @classmethod
    def validate(cls) -> None:
        """驗證必要的環境變數是否設定。
        
        Raises:
            ValueError: 當必要的環境變數缺失時
        """
        required_vars = {
            "DATABASE_URL": cls.DATABASE_URL,
            "SECRET_KEY": cls.SECRET_KEY,
            "JWT_SECRET": cls.JWT_SECRET,
        }
        
        missing_vars = [
            var_name for var_name, value in required_vars.items() 
            if not value
        ]
        
        if missing_vars:
            raise ValueError(
                f"缺少必要的環境變數: {', '.join(missing_vars)}"
            )
        
        # 生產環境的額外檢查
        if cls.ENVIRONMENT == "production":
            if cls.DEBUG:
                raise ValueError("生產環境不能啟用 DEBUG 模式")
            if len(cls.SECRET_KEY) < 32:
                raise ValueError("生產環境的 SECRET_KEY 長度必須 >= 32")

# 應用程式啟動時驗證設定
settings = Settings()
settings.validate()
```

### 3. .env 檔案管理

```bash
# .env.example - 提交到 git，作為範本
DATABASE_URL=postgresql://user:password@localhost/dbname
SECRET_KEY=your-secret-key-here
AWS_REGION=ap-northeast-1
THIRD_PARTY_API_KEY=your-api-key

# .env - 不要提交到 git！加入 .gitignore
DATABASE_URL=postgresql://realuser:realpass@prod-db.example.com/prod
SECRET_KEY=actual-secret-key-32-chars-long
AWS_REGION=ap-northeast-1
THIRD_PARTY_API_KEY=sk-real-api-key-here
```

```python
# .gitignore
.env
.env.local
.env.*.local
*.pem
*.key
credentials.json
secrets/
```

## 認證與授權

### 1. 密碼處理

```python
import hashlib
import secrets
from typing import Tuple

class PasswordService:
    """密碼加密和驗證服務。"""
    
    @staticmethod
    def hash_password(password: str) -> Tuple[str, str]:
        """使用 PBKDF2 加密密碼。
        
        Args:
            password: 明文密碼
            
        Returns:
            (salt, hashed_password) 元組
        """
        # 產生隨機 salt
        salt = secrets.token_hex(32)
        
        # 使用 PBKDF2 加密（100,000 次迭代）
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        ).hex()
        
        return salt, password_hash
    
    @staticmethod
    def verify_password(
        password: str,
        salt: str,
        stored_hash: str
    ) -> bool:
        """驗證密碼是否正確。
        
        Args:
            password: 要驗證的明文密碼
            salt: 儲存的 salt
            stored_hash: 儲存的密碼 hash
            
        Returns:
            密碼是否正確
        """
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        ).hex()
        
        # 使用 constant-time 比較防止時序攻擊
        return secrets.compare_digest(password_hash, stored_hash)
    
    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, str]:
        """驗證密碼強度。
        
        Args:
            password: 要驗證的密碼
            
        Returns:
            (is_valid, error_message) 元組
        """
        if len(password) < 12:
            return False, "密碼長度必須至少 12 個字元"
        
        if not any(c.isupper() for c in password):
            return False, "密碼必須包含至少一個大寫字母"
        
        if not any(c.islower() for c in password):
            return False, "密碼必須包含至少一個小寫字母"
        
        if not any(c.isdigit() for c in password):
            return False, "密碼必須包含至少一個數字"
        
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in password):
            return False, "密碼必須包含至少一個特殊字元"
        
        return True, ""
```

### 2. JWT Token 處理

```python
import jwt
from datetime import datetime, timedelta
from typing import Dict, Optional

class JWTService:
    """JWT token 管理服務。"""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """初始化 JWT 服務。
        
        Args:
            secret_key: JWT 簽名密鑰（至少 32 字元）
            algorithm: 加密演算法，預設 HS256
        """
        if len(secret_key) < 32:
            raise ValueError("JWT secret key 長度必須至少 32 字元")
        
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def create_access_token(
        self,
        user_id: str,
        expires_in_minutes: int = 60
    ) -> str:
        """建立存取 token。
        
        Args:
            user_id: 用戶 ID
            expires_in_minutes: token 有效期限（分鐘）
            
        Returns:
            JWT token 字串
        """
        now = datetime.utcnow()
        payload = {
            "user_id": user_id,
            "iat": now,  # issued at
            "exp": now + timedelta(minutes=expires_in_minutes),  # expiry
            "type": "access"
        }
        
        token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        return token
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """驗證並解析 token。
        
        Args:
            token: JWT token 字串
            
        Returns:
            解析後的 payload，如果無效則返回 None
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token 已過期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"無效的 token: {e}")
            return None
```

### 3. API 存取控制

```python
from functools import wraps
from flask import request, jsonify

def require_authentication(f):
    """裝飾器：要求請求必須經過認證。"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 從 header 取得 token
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            return jsonify({"error": "缺少認證 token"}), 401
        
        try:
            # Bearer token 格式
            token_type, token = auth_header.split(" ")
            if token_type.lower() != "bearer":
                return jsonify({"error": "不支援的認證類型"}), 401
            
            # 驗證 token
            jwt_service = JWTService(settings.JWT_SECRET)
            payload = jwt_service.verify_token(token)
            
            if not payload:
                return jsonify({"error": "無效或過期的 token"}), 401
            
            # 將用戶資訊加入 request context
            request.current_user_id = payload["user_id"]
            
        except Exception as e:
            logger.error(f"認證失敗: {e}")
            return jsonify({"error": "認證失敗"}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_role(required_role: str):
    """裝飾器：要求請求者擁有特定角色。"""
    def decorator(f):
        @wraps(f)
        @require_authentication
        def decorated_function(*args, **kwargs):
            user_id = request.current_user_id
            
            # 檢查用戶角色
            user_service = UserService()
            user_roles = user_service.get_user_roles(user_id)
            
            if required_role not in user_roles:
                return jsonify({
                    "error": f"需要 {required_role} 權限"
                }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

# 使用範例
@app.route("/api/admin/users")
@require_role("admin")
def list_all_users():
    """列出所有用戶（需要 admin 角色）。"""
    pass
```

## 輸入驗證

### 1. 防止 SQL Injection

```python
from sqlalchemy import text

# ❌ 危險：字串拼接會導致 SQL injection
def get_user_unsafe(user_id: str):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    # 攻擊者可以輸入: ' OR '1'='1
    return db.execute(query)

# ✅ 安全：使用參數化查詢
def get_user_safe(user_id: str):
    query = text("SELECT * FROM users WHERE id = :user_id")
    return db.execute(query, {"user_id": user_id})

# ✅ 更好：使用 ORM
def get_user_orm(user_id: str):
    return User.query.filter_by(id=user_id).first()
```

### 2. 輸入清理和驗證

```python
from typing import Any, Optional
import re
from html import escape

class InputValidator:
    """輸入驗證工具類別。"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """驗證 email 格式。"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """清理 HTML 特殊字元，防止 XSS。"""
        return escape(text)
    
    @staticmethod
    def validate_integer(
        value: Any,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None
    ) -> Tuple[bool, Optional[int], str]:
        """驗證整數值和範圍。
        
        Returns:
            (is_valid, parsed_value, error_message) 元組
        """
        try:
            parsed = int(value)
        except (ValueError, TypeError):
            return False, None, f"無效的整數: {value}"
        
        if min_value is not None and parsed < min_value:
            return False, None, f"值必須 >= {min_value}"
        
        if max_value is not None and parsed > max_value:
            return False, None, f"值必須 <= {max_value}"
        
        return True, parsed, ""
    
    @staticmethod
    def validate_string_length(
        text: str,
        min_length: int = 0,
        max_length: int = 1000
    ) -> Tuple[bool, str]:
        """驗證字串長度。
        
        Returns:
            (is_valid, error_message) 元組
        """
        length = len(text)
        
        if length < min_length:
            return False, f"長度必須至少 {min_length} 字元"
        
        if length > max_length:
            return False, f"長度不能超過 {max_length} 字元"
        
        return True, ""

# 使用範例
def create_user(username: str, email: str, age: str):
    """建立用戶，包含完整的輸入驗證。"""
    validator = InputValidator()
    
    # 驗證 username
    is_valid, error = validator.validate_string_length(
        username, min_length=3, max_length=50
    )
    if not is_valid:
        raise ValidationError(f"用戶名稱無效: {error}")
    
    # 清理 username（防止 XSS）
    username = validator.sanitize_html(username)
    
    # 驗證 email
    if not validator.validate_email(email):
        raise ValidationError("無效的 email 格式")
    
    # 驗證 age
    is_valid, age_value, error = validator.validate_integer(
        age, min_value=0, max_value=150
    )
    if not is_valid:
        raise ValidationError(f"年齡無效: {error}")
    
    # 繼續建立用戶...
```

### 3. 防止路徑遍歷攻擊

```python
import os
from pathlib import Path

def safe_file_access(user_filename: str, base_directory: str) -> Path:
    """安全地存取用戶指定的檔案，防止路徑遍歷攻擊。
    
    Args:
        user_filename: 用戶提供的檔案名稱
        base_directory: 允許存取的基礎目錄
        
    Returns:
        安全的檔案路徑
        
    Raises:
        SecurityError: 當檔案路徑不安全時
    """
    # 正規化路徑
    base_path = Path(base_directory).resolve()
    requested_path = (base_path / user_filename).resolve()
    
    # 檢查是否在允許的目錄內
    if not str(requested_path).startswith(str(base_path)):
        raise SecurityError(
            f"不允許存取此路徑: {user_filename}"
        )
    
    return requested_path

# 使用範例
try:
    # ❌ 攻擊者可能輸入: ../../etc/passwd
    file_path = safe_file_access(
        user_input_filename,
        "/var/app/uploads"
    )
    with open(file_path, "r") as f:
        content = f.read()
except SecurityError as e:
    logger.warning(f"檢測到路徑遍歷攻擊嘗試: {e}")
    return {"error": "無效的檔案路徑"}, 400
```

## 資料加密

### 1. 敏感資料加密

```python
from cryptography.fernet import Fernet
import base64

class EncryptionService:
    """資料加密服務。"""
    
    def __init__(self, encryption_key: str):
        """初始化加密服務。
        
        Args:
            encryption_key: 32 字元的 base64 編碼密鑰
        """
        self.cipher = Fernet(encryption_key.encode())
    
    def encrypt(self, plaintext: str) -> str:
        """加密字串。
        
        Args:
            plaintext: 明文
            
        Returns:
            加密後的 base64 字串
        """
        encrypted = self.cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """解密字串。
        
        Args:
            ciphertext: 加密的 base64 字串
            
        Returns:
            解密後的明文
        """
        encrypted = base64.b64decode(ciphertext.encode())
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()
    
    @staticmethod
    def generate_key() -> str:
        """產生新的加密密鑰。"""
        return Fernet.generate_key().decode()

# 使用範例
encryption_service = EncryptionService(
    os.getenv("ENCRYPTION_KEY")
)

# 加密敏感資料再存入資料庫
encrypted_ssn = encryption_service.encrypt(user_ssn)
user.encrypted_ssn = encrypted_ssn
db.session.commit()

# 需要時再解密
decrypted_ssn = encryption_service.decrypt(user.encrypted_ssn)
```

## 安全性記錄和監控

### 1. 記錄安全事件

```python
import logging
from datetime import datetime

# 專門的安全事件 logger
security_logger = logging.getLogger("security")

class SecurityAudit:
    """安全審計工具。"""
    
    @staticmethod
    def log_login_attempt(
        username: str,
        success: bool,
        ip_address: str,
        user_agent: str
    ):
        """記錄登入嘗試。"""
        security_logger.info(
            "登入嘗試",
            extra={
                "event_type": "login_attempt",
                "username": username,
                "success": success,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def log_permission_denied(
        user_id: str,
        resource: str,
        action: str,
        reason: str
    ):
        """記錄權限被拒絕。"""
        security_logger.warning(
            "權限被拒絕",
            extra={
                "event_type": "permission_denied",
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def log_suspicious_activity(
        user_id: str,
        activity_type: str,
        details: dict
    ):
        """記錄可疑活動。"""
        security_logger.error(
            "檢測到可疑活動",
            extra={
                "event_type": "suspicious_activity",
                "user_id": user_id,
                "activity_type": activity_type,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
```

### 2. 速率限制

```python
from functools import wraps
from flask import request
from datetime import datetime, timedelta
from collections import defaultdict

class RateLimiter:
    """簡單的記憶體內速率限制器。"""
    
    def __init__(self):
        """初始化速率限制器。"""
        self.requests = defaultdict(list)
    
    def is_allowed(
        self,
        key: str,
        max_requests: int,
        time_window_seconds: int
    ) -> bool:
        """檢查是否允許請求。
        
        Args:
            key: 識別符（如 IP 位址或用戶 ID）
            max_requests: 時間窗口內允許的最大請求數
            time_window_seconds: 時間窗口（秒）
            
        Returns:
            是否允許此請求
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=time_window_seconds)
        
        # 清理過期的請求記錄
        self.requests[key] = [
            timestamp for timestamp in self.requests[key]
            if timestamp > cutoff
        ]
        
        # 檢查是否超過限制
        if len(self.requests[key]) >= max_requests:
            return False
        
        # 記錄此次請求
        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter()

def rate_limit(max_requests: int = 100, time_window: int = 60):
    """裝飾器：限制請求頻率。
    
    Args:
        max_requests: 時間窗口內允許的最大請求數
        time_window: 時間窗口（秒）
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 使用 IP 位址作為識別符
            client_ip = request.remote_addr
            
            if not rate_limiter.is_allowed(
                client_ip, max_requests, time_window
            ):
                return jsonify({
                    "error": "請求過於頻繁，請稍後再試"
                }), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# 使用範例
@app.route("/api/login", methods=["POST"])
@rate_limit(max_requests=5, time_window=60)  # 每分鐘最多 5 次
def login():
    """登入 API（有速率限制）。"""
    pass
```

## 安全檢查清單

### 開發階段
- [ ] 所有敏感資料使用環境變數，絕不硬編碼
- [ ] .env 檔案加入 .gitignore
- [ ] 所有密碼使用強雜湊演算法（PBKDF2, bcrypt, argon2）
- [ ] 實作輸入驗證和清理
- [ ] 使用參數化查詢，防止 SQL injection
- [ ] API endpoints 有適當的認證和授權
- [ ] 敏感操作有審計日誌

### 測試階段
- [ ] 測試各種惡意輸入（SQL injection, XSS, 路徑遍歷）
- [ ] 測試認證和授權機制
- [ ] 測試速率限制是否有效
- [ ] 檢查錯誤訊息不洩漏敏感資訊

### 部署前
- [ ] 生產環境關閉 DEBUG 模式
- [ ] 檢查所有環境變數是否正確設定
- [ ] AWS IAM 權限遵循最小權限原則
- [ ] 啟用 HTTPS，禁用 HTTP
- [ ] 設定適當的 CORS 政策
- [ ] 啟用安全 headers（CSP, HSTS, X-Frame-Options）
- [ ] 資料庫連線使用 SSL/TLS

### 持續監控
- [ ] 定期檢查安全日誌
- [ ] 監控異常的登入嘗試
- [ ] 追蹤 API 錯誤率和異常模式
- [ ] 定期更新依賴套件（安全性修補）
- [ ] 定期審查 IAM 權限和存取金鑰

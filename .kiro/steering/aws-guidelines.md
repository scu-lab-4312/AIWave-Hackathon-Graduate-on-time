# AWS 使用指南

## 核心原則

- **使用 AWS CLI 進行資源管理和部署**
- **所有 AWS 操作都要有錯誤處理**
- **使用 IAM 最小權限原則**
- **敏感資料使用 AWS Secrets Manager 或 Parameter Store**

## AWS CLI 基本使用

### 配置檢查
```bash
# 檢查當前配置
aws configure list

# 檢查當前身份
aws sts get-caller-identity

# 設定預設 region
export AWS_DEFAULT_REGION=ap-northeast-1
```

### 常用指令模式
```bash
# 使用 --profile 指定不同環境
aws s3 ls --profile production

# 使用 --output 控制輸出格式
aws ec2 describe-instances --output json
aws ec2 describe-instances --output table

# 使用 --query 過濾結果（JMESPath）
aws s3api list-buckets --query "Buckets[?contains(Name, 'prod')].Name"
```

## Python 中使用 Boto3

### 客戶端初始化
```python
import boto3
from botocore.exceptions import ClientError, BotoCoreError
import logging

logger = logging.getLogger(__name__)

class AWSClientFactory:
    """AWS 客戶端工廠，統一管理 AWS 服務連線。"""
    
    def __init__(self, region_name: str = "ap-northeast-1"):
        """初始化 AWS 客戶端工廠。
        
        Args:
            region_name: AWS region，預設為 ap-northeast-1（東京）
        """
        self.region_name = region_name
        self._session = boto3.Session(region_name=region_name)
    
    def get_s3_client(self):
        """取得 S3 客戶端。"""
        return self._session.client("s3")
    
    def get_dynamodb_resource(self):
        """取得 DynamoDB 資源。"""
        return self._session.resource("dynamodb")
    
    def get_secrets_manager_client(self):
        """取得 Secrets Manager 客戶端。"""
        return self._session.client("secretsmanager")
```

### 錯誤處理模式
```python
from botocore.exceptions import ClientError
from typing import Optional

def upload_file_to_s3(
    bucket_name: str,
    file_path: str,
    object_key: str,
    metadata: Optional[dict] = None
) -> dict[str, Any]:
    """上傳檔案到 S3，包含完整錯誤處理。
    
    Args:
        bucket_name: S3 bucket 名稱
        file_path: 本地檔案路徑
        object_key: S3 物件鍵（檔案在 S3 的路徑）
        metadata: 可選的檔案 metadata
        
    Returns:
        包含上傳結果的字典
        
    Raises:
        S3UploadError: 當上傳失敗時
        FileNotFoundError: 當本地檔案不存在時
    """
    s3_client = boto3.client("s3")
    
    try:
        # 檢查檔案是否存在
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"檔案不存在: {file_path}")
        
        # 準備上傳參數
        extra_args = {}
        if metadata:
            extra_args["Metadata"] = metadata
        
        # 上傳檔案
        s3_client.upload_file(
            Filename=file_path,
            Bucket=bucket_name,
            Key=object_key,
            ExtraArgs=extra_args
        )
        
        logger.info(
            f"成功上傳檔案到 S3: s3://{bucket_name}/{object_key}"
        )
        
        return {
            "success": True,
            "bucket": bucket_name,
            "key": object_key,
            "url": f"s3://{bucket_name}/{object_key}"
        }
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        
        logger.error(
            f"S3 上傳失敗: {error_code} - {error_message}",
            exc_info=True,
            extra={
                "bucket": bucket_name,
                "key": object_key,
                "error_code": error_code
            }
        )
        
        # 根據錯誤類型提供更具體的錯誤訊息
        if error_code == "NoSuchBucket":
            raise S3UploadError(f"Bucket 不存在: {bucket_name}") from e
        elif error_code == "AccessDenied":
            raise S3UploadError(
                f"沒有權限上傳到 bucket: {bucket_name}"
            ) from e
        else:
            raise S3UploadError(f"上傳失敗: {error_message}") from e
            
    except Exception as e:
        logger.error(f"未預期的錯誤: {e}", exc_info=True)
        raise S3UploadError(f"上傳過程發生錯誤: {str(e)}") from e
```

## 常用 AWS 服務模式

### S3 - 物件儲存
```python
class S3Service:
    """S3 服務封裝。"""
    
    def __init__(self, bucket_name: str):
        """初始化 S3 服務。
        
        Args:
            bucket_name: 要操作的 S3 bucket 名稱
        """
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3")
    
    def list_objects(self, prefix: str = "") -> list[dict]:
        """列出 bucket 中的物件。
        
        Args:
            prefix: 物件鍵前綴，用於過濾
            
        Returns:
            物件列表
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if "Contents" not in response:
                return []
            
            return [
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"]
                }
                for obj in response["Contents"]
            ]
            
        except ClientError as e:
            logger.error(f"列出物件失敗: {e}")
            raise
    
    def generate_presigned_url(
        self,
        object_key: str,
        expiration: int = 3600
    ) -> str:
        """產生預簽名 URL 用於臨時存取。
        
        Args:
            object_key: S3 物件鍵
            expiration: URL 有效時間（秒），預設 1 小時
            
        Returns:
            預簽名 URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key
                },
                ExpiresIn=expiration
            )
            return url
            
        except ClientError as e:
            logger.error(f"產生預簽名 URL 失敗: {e}")
            raise
```

### DynamoDB - NoSQL 資料庫
```python
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

class DynamoDBService:
    """DynamoDB 服務封裝。"""
    
    def __init__(self, table_name: str):
        """初始化 DynamoDB 服務。
        
        Args:
            table_name: DynamoDB 表格名稱
        """
        self.table_name = table_name
        dynamodb = boto3.resource("dynamodb")
        self.table = dynamodb.Table(table_name)
    
    def put_item(self, item: dict) -> dict:
        """新增或更新項目。
        
        Args:
            item: 要存入的資料（注意：數字要用 Decimal）
            
        Returns:
            操作結果
        """
        try:
            # 將 float 轉換為 Decimal（DynamoDB 要求）
            item = self._convert_floats_to_decimal(item)
            
            response = self.table.put_item(Item=item)
            
            logger.info(f"成功寫入 DynamoDB: {self.table_name}")
            return {"success": True, "response": response}
            
        except ClientError as e:
            logger.error(f"寫入 DynamoDB 失敗: {e}", exc_info=True)
            raise
    
    def query_by_partition_key(
        self,
        partition_key_name: str,
        partition_key_value: Any,
        limit: Optional[int] = None
    ) -> list[dict]:
        """使用 partition key 查詢。
        
        Args:
            partition_key_name: partition key 欄位名稱
            partition_key_value: partition key 值
            limit: 限制返回數量
            
        Returns:
            查詢結果列表
        """
        try:
            query_params = {
                "KeyConditionExpression": Key(partition_key_name).eq(
                    partition_key_value
                )
            }
            
            if limit:
                query_params["Limit"] = limit
            
            response = self.table.query(**query_params)
            
            # 將 Decimal 轉回 float 方便使用
            items = self._convert_decimals_to_float(response["Items"])
            
            return items
            
        except ClientError as e:
            logger.error(f"查詢 DynamoDB 失敗: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _convert_floats_to_decimal(obj: Any) -> Any:
        """遞迴轉換 float 為 Decimal。"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: DynamoDBService._convert_floats_to_decimal(v) 
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBService._convert_floats_to_decimal(item) 
                    for item in obj]
        return obj
    
    @staticmethod
    def _convert_decimals_to_float(obj: Any) -> Any:
        """遞迴轉換 Decimal 為 float。"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: DynamoDBService._convert_decimals_to_float(v) 
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBService._convert_decimals_to_float(item) 
                    for item in obj]
        return obj
```

### Secrets Manager - 敏感資料管理
```python
import json

class SecretsService:
    """AWS Secrets Manager 服務封裝。"""
    
    def __init__(self):
        """初始化 Secrets Manager 客戶端。"""
        self.client = boto3.client("secretsmanager")
    
    def get_secret(self, secret_name: str) -> dict:
        """取得 secret 值。
        
        Args:
            secret_name: Secret 名稱
            
        Returns:
            Secret 內容（自動解析 JSON）
            
        Raises:
            SecretNotFoundError: 當 secret 不存在時
        """
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            
            # Secret 可能是字串或二進位
            if "SecretString" in response:
                secret = response["SecretString"]
                # 嘗試解析為 JSON
                try:
                    return json.loads(secret)
                except json.JSONDecodeError:
                    return {"value": secret}
            else:
                # 二進位 secret
                return {"value": response["SecretBinary"]}
                
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            
            if error_code == "ResourceNotFoundException":
                logger.error(f"Secret 不存在: {secret_name}")
                raise SecretNotFoundError(
                    f"找不到 secret: {secret_name}"
                ) from e
            else:
                logger.error(f"取得 secret 失敗: {e}", exc_info=True)
                raise
    
    def create_secret(
        self,
        secret_name: str,
        secret_value: dict,
        description: str = ""
    ) -> str:
        """建立新的 secret。
        
        Args:
            secret_name: Secret 名稱
            secret_value: Secret 值（會自動轉為 JSON）
            description: Secret 描述
            
        Returns:
            Secret ARN
        """
        try:
            response = self.client.create_secret(
                Name=secret_name,
                Description=description,
                SecretString=json.dumps(secret_value)
            )
            
            logger.info(f"成功建立 secret: {secret_name}")
            return response["ARN"]
            
        except ClientError as e:
            logger.error(f"建立 secret 失敗: {e}", exc_info=True)
            raise
```

## AWS CLI 常用操作

### S3 操作
```bash
# 列出所有 buckets
aws s3 ls

# 列出 bucket 內容
aws s3 ls s3://my-bucket/path/

# 上傳檔案
aws s3 cp local-file.txt s3://my-bucket/remote-file.txt

# 下載檔案
aws s3 cp s3://my-bucket/remote-file.txt local-file.txt

# 同步目錄（類似 rsync）
aws s3 sync ./local-dir s3://my-bucket/remote-dir

# 刪除檔案
aws s3 rm s3://my-bucket/file.txt

# 設定檔案為公開讀取
aws s3api put-object-acl \
  --bucket my-bucket \
  --key file.txt \
  --acl public-read
```

### DynamoDB 操作
```bash
# 列出所有表格
aws dynamodb list-tables

# 描述表格
aws dynamodb describe-table --table-name MyTable

# 取得項目
aws dynamodb get-item \
  --table-name MyTable \
  --key '{"id": {"S": "123"}}'

# 新增項目
aws dynamodb put-item \
  --table-name MyTable \
  --item '{"id": {"S": "123"}, "name": {"S": "Test"}}'

# 掃描表格（小心：會讀取所有資料）
aws dynamodb scan --table-name MyTable --max-items 10
```

### Secrets Manager 操作
```bash
# 取得 secret 值
aws secretsmanager get-secret-value --secret-id my-secret

# 建立 secret
aws secretsmanager create-secret \
  --name my-secret \
  --secret-string '{"username":"admin","password":"secret123"}'

# 更新 secret
aws secretsmanager update-secret \
  --secret-id my-secret \
  --secret-string '{"username":"admin","password":"newpass456"}'

# 列出所有 secrets
aws secretsmanager list-secrets
```

### Lambda 操作
```bash
# 列出所有 Lambda 函數
aws lambda list-functions

# 調用 Lambda 函數
aws lambda invoke \
  --function-name my-function \
  --payload '{"key": "value"}' \
  response.json

# 更新函數程式碼（從 S3）
aws lambda update-function-code \
  --function-name my-function \
  --s3-bucket my-bucket \
  --s3-key lambda-code.zip
```

## 最佳實踐

### 1. 使用環境變數管理配置
```python
import os

# ✅ 好的做法
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE_NAME")

# ❌ 避免硬編碼
S3_BUCKET = "my-production-bucket"  # 不要這樣做
```

### 2. 實作重試機制
```python
from botocore.config import Config
from botocore.exceptions import ClientError
import time

# 設定自動重試
config = Config(
    retries={
        "max_attempts": 3,
        "mode": "adaptive"  # 自適應重試模式
    }
)

s3_client = boto3.client("s3", config=config)

# 或手動實作重試邏輯
def retry_on_throttle(func, max_retries=3, backoff_factor=2):
    """處理 AWS 限流的重試裝飾器。"""
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                if attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(
                        f"遇到限流，等待 {wait_time} 秒後重試..."
                    )
                    time.sleep(wait_time)
                else:
                    raise
            else:
                raise
```

### 3. 使用分頁處理大量資料
```python
def list_all_objects(bucket_name: str, prefix: str = "") -> list[dict]:
    """列出所有物件，自動處理分頁。"""
    s3_client = boto3.client("s3")
    paginator = s3_client.get_paginator("list_objects_v2")
    
    all_objects = []
    
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        if "Contents" in page:
            all_objects.extend(page["Contents"])
    
    return all_objects
```

### 4. 記錄 AWS API 呼叫
```python
import boto3
import logging

# 啟用 boto3 debug logging（開發時使用）
boto3.set_stream_logger("boto3.resources", logging.DEBUG)

# 生產環境記錄關鍵操作
logger.info(
    "執行 S3 操作",
    extra={
        "operation": "put_object",
        "bucket": bucket_name,
        "key": object_key,
        "size_bytes": file_size
    }
)
```

## 安全性檢查清單

- [ ] 不要在程式碼中硬編碼 AWS credentials
- [ ] 使用 IAM roles 而非長期 credentials（特別是 EC2/Lambda）
- [ ] 敏感資料使用 Secrets Manager 或 Parameter Store
- [ ] S3 bucket 預設不公開，需要公開時要明確設定
- [ ] DynamoDB 查詢使用 partition key 避免全表掃描
- [ ] 啟用 CloudTrail 記錄所有 API 呼叫
- [ ] 定期檢查 IAM 權限，遵循最小權限原則
- [ ] 使用 VPC endpoints 減少公網暴露

"""AgentCore Gateway Lambda target for privacy-minimized pharmacy lookup."""

import json
import logging
import os
from decimal import Decimal

import boto3
import pymysql


logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "hackathon")
SECRET_ARN = os.environ.get("DB_SECRET_ARN")
_secret_cache = None


def _credentials() -> dict:
    global _secret_cache
    if _secret_cache is None:
        if not SECRET_ARN:
            raise RuntimeError("DB_SECRET_ARN is not configured")
        value = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_ARN)
        _secret_cache = json.loads(value["SecretString"])
    return _secret_cache


def connection():
    secret = _credentials()
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=secret["username"],
        password=secret["password"],
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
        autocommit=False,
    )


def _tool_name(event: dict, context) -> str:
    direct_name = event.pop("_tool_name", None)
    if direct_name:
        return direct_name
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    original = custom.get("bedrockAgentCoreToolName", "")
    return original.split("___", 1)[-1]


def get_pharmacy_options(event: dict) -> dict:
    unexpected = sorted(set(event) - {"task_id", "city", "district"})
    if unexpected:
        raise ValueError(f"unsupported fields: {', '.join(unexpected)}")
    required = ("task_id", "city", "district")
    missing = [field for field in required if not str(event.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    city = str(event["city"]).strip()
    district = str(event["district"]).strip()
    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id AS pharmacy_id,
                       name,
                       rate AS rating,
                       county_name AS city,
                       district_name AS district,
                       address,
                       phone
                FROM cms_homepage_service_type_12
                WHERE county_name=%s
                  AND phone IS NOT NULL
                  AND TRIM(phone) <> ''
                ORDER BY CASE WHEN district_name=%s THEN 0 ELSE 1 END,
                         rate DESC, id ASC
                LIMIT 3
                """,
                (city, district),
            )
            rows = cursor.fetchall()

    if len(rows) < 3:
        raise RuntimeError(f"{city}目前可提供的虛擬藥局聯絡資料不足三間")
    options = [
        {
            "option_id": f"pharmacy-{row['pharmacy_id']}",
            "pharmacy_id": row["pharmacy_id"],
            "name": row["name"],
            "city": row["city"],
            "district": row["district"],
            "address": row["address"],
            "rating": float(row["rating"]) if isinstance(row["rating"], Decimal) else row["rating"],
            "phone": row["phone"],
        }
        for row in rows
    ]
    return {
        "task_id": event["task_id"],
        "data_notice": "以下為黑客松資料庫中的藥局示範資料。",
        "privacy_notice": "本服務只依地區查詢，不接收或保存任何醫療資訊；請自行致電藥局確認。",
        "options": options,
    }


def lambda_handler(event, context):
    try:
        tool_name = _tool_name(event, context)
        if tool_name == "get_pharmacy_options":
            return get_pharmacy_options(event)
        raise ValueError(f"unknown tool: {tool_name}")
    except Exception as error:
        logger.exception("Medical operation failed")
        return {"error": {"type": type(error).__name__, "message": str(error)}}

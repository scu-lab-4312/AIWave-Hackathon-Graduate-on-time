"""AgentCore Gateway Lambda target for privacy-minimized pharmacist lookup."""

import json
import logging
import os
from decimal import Decimal
from pathlib import Path

import boto3
import pymysql


logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "repair_demo")
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
                SELECT id AS pharmacy_id, name, city, district, address, rating,
                       pharmacist_name, line_id
                FROM medical_pharmacies
                WHERE is_active=TRUE AND city=%s
                ORDER BY CASE WHEN district=%s THEN 0 ELSE 1 END,
                         rating DESC, id ASC
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
            "pharmacist_name": row["pharmacist_name"],
            "line_id": row["line_id"],
        }
        for row in rows
    ]
    return {
        "task_id": event["task_id"],
        "data_notice": "以下皆為黑客松虛擬藥局與虛擬 LINE 資料。",
        "privacy_notice": "本服務只依地區查詢，不接收或保存任何醫療資訊；請自行透過 LINE 與藥師聯絡。",
        "options": options,
    }


def initialize_medical_demo_data() -> dict:
    statements = [
        statement.strip()
        for statement in Path(__file__).with_name("schema.sql").read_text().split(";")
        if statement.strip()
    ]
    pharmacies = [
        ("信義安心藥局", "台北市", "信義區", "台北市信義區莊敬路210號", 4.9, "林怡安藥師", "@demo-pharm-xinyi-01"),
        ("市府健康藥局", "台北市", "信義區", "台北市信義區忠孝東路五段68號", 4.8, "陳柏宇藥師", "@demo-pharm-xinyi-02"),
        ("松仁好鄰居藥局", "台北市", "信義區", "台北市信義區松仁路123號", 4.7, "王欣儀藥師", "@demo-pharm-xinyi-03"),
        ("敦南社區藥局", "台北市", "大安區", "台北市大安區敦化南路一段200號", 4.9, "李明哲藥師", "@demo-pharm-daan-01"),
        ("板橋新埔藥局", "新北市", "板橋區", "新北市板橋區文化路一段300號", 4.9, "張雅雯藥師", "@demo-pharm-banqiao-01"),
        ("板橋安心藥局", "新北市", "板橋區", "新北市板橋區中山路一段50號", 4.8, "吳家豪藥師", "@demo-pharm-banqiao-02"),
        ("新店健康藥局", "新北市", "新店區", "新北市新店區北新路二段100號", 4.7, "黃思涵藥師", "@demo-pharm-xindian-01"),
        ("中和好鄰居藥局", "新北市", "中和區", "新北市中和區景平路400號", 4.6, "蔡承恩藥師", "@demo-pharm-zhonghe-01"),
        ("西屯安康藥局", "台中市", "西屯區", "台中市西屯區台灣大道三段200號", 4.9, "劉品妤藥師", "@demo-pharm-xitun-01"),
        ("逢甲社區藥局", "台中市", "西屯區", "台中市西屯區福星路500號", 4.8, "楊子謙藥師", "@demo-pharm-xitun-02"),
        ("北屯健康藥局", "台中市", "北屯區", "台中市北屯區崇德路二段80號", 4.7, "周佳蓉藥師", "@demo-pharm-beitun-01"),
        ("南屯安心藥局", "台中市", "南屯區", "台中市南屯區公益路二段120號", 4.6, "鄭宇庭藥師", "@demo-pharm-nantun-01"),
    ]

    with connection() as db:
        try:
            with db.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                cursor.execute("TRUNCATE TABLE medical_pharmacies")
                cursor.executemany(
                    """INSERT INTO medical_pharmacies
                       (name,city,district,address,rating,pharmacist_name,line_id,is_active)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)""",
                    pharmacies,
                )
                db.commit()
        except Exception:
            db.rollback()
            raise
    return {"initialized": True, "virtual_pharmacies": len(pharmacies)}


def lambda_handler(event, context):
    try:
        tool_name = _tool_name(event, context)
        if tool_name == "get_pharmacy_options":
            return get_pharmacy_options(event)
        if tool_name == "initialize_medical_demo_data":
            return initialize_medical_demo_data()
        raise ValueError(f"unknown tool: {tool_name}")
    except Exception as error:
        logger.exception("Medical operation failed")
        return {"error": {"type": type(error).__name__, "message": str(error)}}

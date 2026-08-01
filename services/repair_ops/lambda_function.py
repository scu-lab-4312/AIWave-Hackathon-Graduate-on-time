"""AgentCore Gateway Lambda target backed by the shared CMS RDS."""

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import boto3
import pymysql


logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_NAME = os.environ.get("DB_NAME", "hackathon")
SECRET_ARN = os.environ.get("DB_SECRET_ARN")
TAIPEI_TZ = timezone(timedelta(hours=8))
_secret_cache = None


def percentile(values: list[int], probability: float) -> int:
    """Inclusive linear percentile rounded to the nearest hundred TWD."""
    if not values:
        raise ValueError("cannot calculate estimate without historical events")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    value = ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return max(100, int(round(value / 100.0) * 100))


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


def _json_safe(value):
    if isinstance(value, datetime):
        utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc_value.astimezone(TAIPEI_TZ).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _tool_name(event: dict, context) -> str:
    if event.get("_tool_name"):
        return event.pop("_tool_name")
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    original = custom.get("bedrockAgentCoreToolName", "")
    return original.split("___", 1)[-1]


def _validate_fields(event: dict, allowed: set[str], required: tuple[str, ...]) -> None:
    unexpected = sorted(set(event) - allowed)
    if unexpected:
        raise ValueError(f"unsupported fields: {', '.join(unexpected)}")
    missing = [field for field in required if event.get(field) in (None, "")]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")


def get_repair_options(event: dict) -> dict:
    _validate_fields(
        event,
        {"task_id", "issue_type", "city", "district", "issue_summary"},
        ("task_id", "issue_type", "city", "district"),
    )
    issue_type = str(event["issue_type"]).strip()
    city = str(event["city"]).strip()
    district = str(event["district"]).strip()

    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """SELECT final_price
                   FROM agent_repair_price_history
                   WHERE issue_type=%s AND county_name=%s AND district_name=%s
                   ORDER BY completed_at DESC LIMIT 100""",
                (issue_type, city, district),
            )
            prices = [int(row["final_price"]) for row in cursor.fetchall()]
            basis = f"{city}{district}相似案件"
            if len(prices) < 10:
                cursor.execute(
                    """SELECT final_price
                       FROM agent_repair_price_history
                       WHERE issue_type=%s AND county_name=%s
                       ORDER BY completed_at DESC LIMIT 100""",
                    (issue_type, city),
                )
                prices = [int(row["final_price"]) for row in cursor.fetchall()]
                basis = f"{city}相似案件"
            if not prices:
                cursor.execute(
                    """SELECT final_price
                       FROM agent_repair_price_history
                       WHERE issue_type=%s
                       ORDER BY completed_at DESC LIMIT 100""",
                    (issue_type,),
                )
                prices = [int(row["final_price"]) for row in cursor.fetchall()]
                basis = "全區相似案件"

            cursor.execute(
                """
                SELECT p.id AS provider_id,
                       p.name,
                       p.county_name AS city,
                       p.district_name AS district,
                       p.address,
                       p.phone,
                       p.rate AS rating,
                       s.base_visit_fee,
                       a.id AS slot_id,
                       a.start_at
                FROM cms_homepage_service_type_10 p
                JOIN agent_repair_provider_services s
                  ON s.provider_id=p.id AND s.issue_type=%s AND s.is_active=TRUE
                JOIN agent_repair_availability a
                  ON a.provider_id=p.id AND a.status='AVAILABLE' AND a.start_at>UTC_TIMESTAMP()
                WHERE p.county_name=%s
                  AND p.phone IS NOT NULL
                  AND TRIM(p.phone) <> ''
                ORDER BY CASE WHEN p.district_name=%s THEN 0 ELSE 1 END,
                         p.rate DESC,
                         p.id ASC,
                         a.start_at ASC
                """,
                (issue_type, city, district),
            )
            rows = cursor.fetchall()

    providers: dict[int, dict] = {}
    for row in rows:
        provider = providers.setdefault(
            row["provider_id"],
            {
                "option_id": f"provider-{row['provider_id']}",
                "provider_id": row["provider_id"],
                "name": row["name"],
                "city": row["city"],
                "district": row["district"],
                "address": row["address"],
                "phone": row["phone"],
                "rating": float(row["rating"]),
                "base_visit_fee": int(row["base_visit_fee"]),
                "available_slots": [],
            },
        )
        if len(provider["available_slots"]) < 2:
            provider["available_slots"].append(
                {"slot_id": str(row["slot_id"]), "start_at": _json_safe(row["start_at"])}
            )
    options = list(providers.values())[:3]
    if len(options) < 3:
        raise RuntimeError("目前可服務廠商不足三間")

    return {
        "task_id": event["task_id"],
        "data_notice": "廠商主資料來自黑客松共享 CMS；時段、歷史價格與預訂為 Agent 示範資料。",
        "estimate": {
            "low": percentile(prices, 0.25),
            "high": percentile(prices, 0.75),
            "currency": "TWD",
            "sample_size": len(prices),
            "basis": basis,
            "disclaimer": "參考歷史相似案件，實際費用以現場狀況與廠商報價為準。",
        },
        "options": options,
    }


def create_repair_booking(event: dict) -> dict:
    required = (
        "task_id", "actor_id", "provider_id", "slot_id", "issue_type",
        "issue_summary", "estimate_low", "estimate_high",
    )
    _validate_fields(event, set(required), required)

    with connection() as db:
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """SELECT b.booking_code, b.status, p.name AS provider_name, a.start_at
                       FROM agent_repair_bookings b
                       JOIN cms_homepage_service_type_10 p ON p.id=b.provider_id
                       JOIN agent_repair_availability a ON a.id=b.availability_id
                       WHERE b.task_id=%s""",
                    (event["task_id"],),
                )
                existing = cursor.fetchone()
                if existing:
                    db.rollback()
                    return {
                        "booking_code": existing["booking_code"],
                        "status": existing["status"].lower(),
                        "provider_name": existing["provider_name"],
                        "scheduled_at": _json_safe(existing["start_at"]),
                        "idempotent_replay": True,
                    }

                cursor.execute(
                    """SELECT id, start_at, status
                       FROM agent_repair_availability
                       WHERE id=%s AND provider_id=%s FOR UPDATE""",
                    (event["slot_id"], event["provider_id"]),
                )
                slot = cursor.fetchone()
                if not slot or slot["status"] != "AVAILABLE":
                    raise ValueError("選擇的服務時段已不可用")

                booking_code = "RP-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[-16:]
                cursor.execute(
                    """INSERT INTO agent_repair_bookings
                       (booking_code, task_id, actor_id, provider_id, availability_id, issue_type,
                        issue_summary, estimate_low, estimate_high, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'REQUESTED')""",
                    (
                        booking_code, event["task_id"], event["actor_id"], event["provider_id"],
                        event["slot_id"], event["issue_type"], event["issue_summary"],
                        event["estimate_low"], event["estimate_high"],
                    ),
                )
                cursor.execute(
                    "UPDATE agent_repair_availability SET status='BOOKED' WHERE id=%s",
                    (event["slot_id"],),
                )
                cursor.execute(
                    "SELECT name FROM cms_homepage_service_type_10 WHERE id=%s",
                    (event["provider_id"],),
                )
                provider = cursor.fetchone()
                if not provider:
                    raise ValueError("選擇的廠商不存在")
                db.commit()
                return {
                    "booking_code": booking_code,
                    "status": "requested",
                    "provider_name": provider["name"],
                    "scheduled_at": _json_safe(slot["start_at"]),
                    "estimate": {
                        "low": int(event["estimate_low"]),
                        "high": int(event["estimate_high"]),
                        "currency": "TWD",
                    },
                    "idempotent_replay": False,
                }
        except Exception:
            db.rollback()
            raise


def initialize_repair_support_data() -> dict:
    """Create and idempotently seed Agent-owned tables without modifying CMS data."""
    statements = [
        statement.strip()
        for statement in Path(__file__).with_name("schema.sql").read_text().split(";")
        if statement.strip()
    ]
    issue_types = ("plumbing_leak", "plumbing_clog", "electrical_power", "electrical_light")
    base_prices = {
        "plumbing_leak": 900,
        "plumbing_clog": 1200,
        "electrical_power": 1500,
        "electrical_light": 700,
    }
    now_local = datetime.now(TAIPEI_TZ).replace(minute=0, second=0, microsecond=0)
    now_utc = now_local.astimezone(timezone.utc).replace(tzinfo=None)

    with connection() as db:
        try:
            with db.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                cursor.execute(
                    """SELECT id, county_name, district_name
                       FROM cms_homepage_service_type_10
                       WHERE phone IS NOT NULL AND TRIM(phone) <> ''
                       ORDER BY id"""
                )
                providers = cursor.fetchall()
                if len(providers) < 3:
                    raise RuntimeError("CMS 水電廠商資料不足三間")

                services = [
                    (provider["id"], issue_type, 500 + (provider["id"] % 3) * 100)
                    for provider in providers
                    for issue_type in issue_types
                ]
                cursor.executemany(
                    """INSERT INTO agent_repair_provider_services
                       (provider_id, issue_type, base_visit_fee, is_active)
                       VALUES (%s,%s,%s,TRUE)
                       ON DUPLICATE KEY UPDATE
                         base_visit_fee=VALUES(base_visit_fee), is_active=TRUE""",
                    services,
                )

                cursor.execute(
                    """DELETE FROM agent_repair_availability
                       WHERE status='AVAILABLE' AND start_at<=UTC_TIMESTAMP()"""
                )
                availability = []
                for provider in providers:
                    for day in range(1, 3):
                        for hour in (10, 14):
                            local_slot = (now_local + timedelta(days=day)).replace(hour=hour)
                            start_at = local_slot.astimezone(timezone.utc).replace(tzinfo=None)
                            availability.append((provider["id"], start_at))
                cursor.executemany(
                    """INSERT IGNORE INTO agent_repair_availability
                       (provider_id, start_at, status) VALUES (%s,%s,'AVAILABLE')""",
                    availability,
                )

                history = []
                for index, provider in enumerate(providers[:500]):
                    for issue_index, issue_type in enumerate(issue_types):
                        price = base_prices[issue_type] + (provider["id"] % 10) * 180 + issue_index * 50
                        history.append(
                            (
                                f"cms-{provider['id']}-{issue_type}",
                                provider["id"],
                                issue_type,
                                provider["county_name"],
                                provider["district_name"],
                                price,
                                45 + (provider["id"] % 6) * 15,
                                now_utc - timedelta(days=(index % 180) + 1),
                            )
                        )
                cursor.executemany(
                    """INSERT IGNORE INTO agent_repair_price_history
                       (seed_key, provider_id, issue_type, county_name, district_name,
                        final_price, duration_minutes, completed_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    history,
                )
                db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "initialized": True,
        "cms_providers": len(providers),
        "provider_services": len(services),
        "availability_candidates": len(availability),
        "price_history_candidates": len(history),
        "cms_table_modified": False,
    }


def lambda_handler(event, context):
    try:
        tool_name = _tool_name(event, context)
        if tool_name == "get_repair_options":
            return get_repair_options(event)
        if tool_name == "create_repair_booking":
            return create_repair_booking(event)
        if tool_name == "initialize_repair_support_data":
            return initialize_repair_support_data()
        raise ValueError(f"unknown tool: {tool_name}")
    except Exception as error:
        logger.exception("Repair operation failed")
        return {"error": {"type": type(error).__name__, "message": str(error)}}

"""AgentCore Gateway Lambda target for Taxi matching and booking."""

import json
import logging
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
    direct_name = event.pop("_tool_name", None)
    if direct_name:
        return direct_name
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


def get_taxi_options(event: dict) -> dict:
    required = ("task_id", "city")
    _validate_fields(event, set(required), required)
    city = str(event["city"]).strip()

    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.id AS driver_id,
                       d.name AS fleet_name,
                       d.driver AS driver_name,
                       d.reg_number AS vehicle_reg_number,
                       d.county_name AS city,
                       d.phone,
                       d.rate AS rating,
                       d.description,
                       a.id AS slot_id,
                       a.start_at
                FROM cms_homepage_service_type_13 d
                JOIN agent_taxi_availability a
                  ON a.driver_id=d.id AND a.status='AVAILABLE' AND a.start_at>UTC_TIMESTAMP()
                WHERE d.county_name=%s
                  AND d.phone IS NOT NULL
                  AND TRIM(d.phone) <> ''
                ORDER BY d.rate DESC,
                         d.id ASC,
                         a.start_at ASC
                """,
                (city,),
            )
            rows = cursor.fetchall()

    drivers: dict[int, dict] = {}
    for row in rows:
        driver = drivers.setdefault(
            row["driver_id"],
            {
                "option_id": f"driver-{row['driver_id']}",
                "driver_id": row["driver_id"],
                "fleet_name": row["fleet_name"],
                "driver_name": row["driver_name"],
                "vehicle_reg_number": row["vehicle_reg_number"],
                "city": row["city"],
                "phone": row["phone"],
                "rating": float(row["rating"]),
                "description": row["description"],
                "available_slots": [],
            },
        )
        if len(driver["available_slots"]) < 2:
            driver["available_slots"].append(
                {"slot_id": str(row["slot_id"]), "start_at": _json_safe(row["start_at"])}
            )
    options = list(drivers.values())[:3]
    if len(options) < 3:
        raise RuntimeError("目前可預約司機不足三位")
    return {
        "task_id": event["task_id"],
        "data_notice": "司機主資料來自黑客松共享 CMS；時段與預訂為 Agent 示範資料。",
        "booking_notice": "特殊乘車需求與實際上車位置仍須由使用者自行致電司機確認。",
        "options": options,
    }


def create_taxi_booking(event: dict) -> dict:
    required = (
        "task_id", "actor_id", "driver_id", "slot_id", "pickup_city",
        "pickup_district", "destination", "special_needs",
    )
    _validate_fields(event, set(required), required)

    with connection() as db:
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """SELECT b.booking_code, b.status, d.name AS fleet_name,
                              d.driver AS driver_name, d.reg_number AS vehicle_reg_number,
                              d.phone AS driver_phone,
                              a.start_at, b.pickup_city, b.pickup_district,
                              b.destination, b.special_needs
                       FROM agent_taxi_bookings b
                       JOIN cms_homepage_service_type_13 d ON d.id=b.driver_id
                       JOIN agent_taxi_availability a ON a.id=b.availability_id
                       WHERE b.task_id=%s""",
                    (event["task_id"],),
                )
                existing = cursor.fetchone()
                if existing:
                    db.rollback()
                    return {
                        "booking_code": existing["booking_code"],
                        "status": existing["status"].lower(),
                        "driver_name": existing["driver_name"],
                        "driver_phone": existing["driver_phone"],
                        "fleet_name": existing["fleet_name"],
                        "vehicle_reg_number": existing["vehicle_reg_number"],
                        "scheduled_at": _json_safe(existing["start_at"]),
                        "pickup_city": existing["pickup_city"],
                        "pickup_district": existing["pickup_district"],
                        "destination": existing["destination"],
                        "special_needs": existing["special_needs"],
                        "idempotent_replay": True,
                    }

                cursor.execute(
                    """SELECT id, start_at, status
                       FROM agent_taxi_availability
                       WHERE id=%s AND driver_id=%s FOR UPDATE""",
                    (event["slot_id"], event["driver_id"]),
                )
                slot = cursor.fetchone()
                if not slot or slot["status"] != "AVAILABLE":
                    raise ValueError("選擇的接送時段已不可用")

                cursor.execute(
                    """SELECT name AS fleet_name, driver AS driver_name,
                              reg_number AS vehicle_reg_number, phone
                       FROM cms_homepage_service_type_13 WHERE id=%s""",
                    (event["driver_id"],),
                )
                driver = cursor.fetchone()
                if not driver:
                    raise ValueError("選擇的司機不存在")

                booking_code = "TX-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[-16:]
                cursor.execute(
                    """INSERT INTO agent_taxi_bookings
                       (booking_code, task_id, actor_id, driver_id, availability_id,
                        pickup_city, pickup_district, destination, special_needs, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'REQUESTED')""",
                    (
                        booking_code, event["task_id"], event["actor_id"], event["driver_id"],
                        event["slot_id"], event["pickup_city"], event["pickup_district"],
                        event["destination"], event["special_needs"],
                    ),
                )
                cursor.execute(
                    "UPDATE agent_taxi_availability SET status='BOOKED' WHERE id=%s",
                    (event["slot_id"],),
                )
                db.commit()
                return {
                    "booking_code": booking_code,
                    "status": "requested",
                    "driver_name": driver["driver_name"],
                    "driver_phone": driver["phone"],
                    "fleet_name": driver["fleet_name"],
                    "vehicle_reg_number": driver["vehicle_reg_number"],
                    "scheduled_at": _json_safe(slot["start_at"]),
                    "pickup_city": event["pickup_city"],
                    "pickup_district": event["pickup_district"],
                    "destination": event["destination"],
                    "special_needs": event["special_needs"],
                    "idempotent_replay": False,
                }
        except Exception:
            db.rollback()
            raise


def initialize_taxi_support_data() -> dict:
    """Create Agent-owned tables and slots without modifying the CMS driver table."""
    statements = [
        statement.strip()
        for statement in Path(__file__).with_name("schema.sql").read_text().split(";")
        if statement.strip()
    ]
    now_local = datetime.now(TAIPEI_TZ).replace(minute=0, second=0, microsecond=0)

    with connection() as db:
        try:
            with db.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                cursor.execute(
                    """SELECT id FROM cms_homepage_service_type_13
                       WHERE phone IS NOT NULL AND TRIM(phone) <> '' ORDER BY id"""
                )
                drivers = cursor.fetchall()
                if len(drivers) < 3:
                    raise RuntimeError("CMS 司機資料不足三位")

                cursor.execute(
                    """DELETE FROM agent_taxi_availability
                       WHERE status='AVAILABLE' AND start_at<=UTC_TIMESTAMP()"""
                )
                availability = []
                for driver in drivers:
                    for day in range(1, 3):
                        for hour in (10, 14):
                            local_slot = (now_local + timedelta(days=day)).replace(hour=hour)
                            start_at = local_slot.astimezone(timezone.utc).replace(tzinfo=None)
                            availability.append((driver["id"], start_at))
                cursor.executemany(
                    """INSERT IGNORE INTO agent_taxi_availability
                       (driver_id, start_at, status) VALUES (%s,%s,'AVAILABLE')""",
                    availability,
                )
                db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "initialized": True,
        "cms_drivers": len(drivers),
        "availability_candidates": len(availability),
        "cms_table_modified": False,
    }


def lambda_handler(event, context):
    try:
        tool_name = _tool_name(event, context)
        if tool_name == "get_taxi_options":
            return get_taxi_options(event)
        if tool_name == "create_taxi_booking":
            return create_taxi_booking(event)
        if tool_name == "initialize_taxi_support_data":
            return initialize_taxi_support_data()
        raise ValueError(f"unknown tool: {tool_name}")
    except Exception as error:
        logger.exception("Taxi operation failed")
        return {"error": {"type": type(error).__name__, "message": str(error)}}

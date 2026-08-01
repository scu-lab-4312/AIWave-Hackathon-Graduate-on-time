"""AgentCore Gateway Lambda target backed by RDS for MySQL."""

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
DB_NAME = os.environ.get("DB_NAME", "repair_demo")
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
        client = boto3.client("secretsmanager")
        value = client.get_secret_value(SecretId=SECRET_ARN)
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


def get_repair_options(event: dict) -> dict:
    required = ("task_id", "issue_type", "city", "district")
    missing = [field for field in required if not event.get(field)]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT final_price FROM repair_events WHERE issue_type=%s AND city=%s AND district=%s ORDER BY completed_at DESC LIMIT 100",
                (event["issue_type"], event["city"], event["district"]),
            )
            prices = [row["final_price"] for row in cursor.fetchall()]
            basis = f"{event['city']}{event['district']}相似案件"
            if len(prices) < 10:
                cursor.execute(
                    "SELECT final_price FROM repair_events WHERE issue_type=%s AND city=%s ORDER BY completed_at DESC LIMIT 100",
                    (event["issue_type"], event["city"]),
                )
                prices = [row["final_price"] for row in cursor.fetchall()]
                basis = f"{event['city']}相似案件"
            if not prices:
                cursor.execute(
                    "SELECT final_price FROM repair_events WHERE issue_type=%s ORDER BY completed_at DESC LIMIT 100",
                    (event["issue_type"],),
                )
                prices = [row["final_price"] for row in cursor.fetchall()]
                basis = "全區相似案件"

            cursor.execute(
                """
                SELECT p.id AS provider_id, p.name, p.city, p.district, p.rating,
                       p.completed_jobs, ps.base_visit_fee, a.id AS slot_id, a.start_at
                FROM providers p
                JOIN provider_services ps ON ps.provider_id=p.id AND ps.issue_type=%s
                JOIN provider_availability a ON a.provider_id=p.id AND a.status='AVAILABLE' AND a.start_at>UTC_TIMESTAMP()
                WHERE p.is_active=TRUE AND p.city=%s
                ORDER BY CASE WHEN p.district=%s THEN 0 ELSE 1 END,
                         p.rating DESC, p.completed_jobs DESC, a.start_at ASC
                """,
                (event["issue_type"], event["city"], event["district"]),
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
                "rating": float(row["rating"]),
                "completed_jobs": row["completed_jobs"],
                "base_visit_fee": row["base_visit_fee"],
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
    missing = [field for field in required if event.get(field) in (None, "")]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    with connection() as db:
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """SELECT b.booking_code, b.status, p.name AS provider_name, a.start_at
                       FROM bookings b JOIN providers p ON p.id=b.provider_id
                       JOIN provider_availability a ON a.id=b.availability_id
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
                    "SELECT id, start_at, status FROM provider_availability WHERE id=%s AND provider_id=%s FOR UPDATE",
                    (event["slot_id"], event["provider_id"]),
                )
                slot = cursor.fetchone()
                if not slot or slot["status"] != "AVAILABLE":
                    raise ValueError("選擇的服務時段已不可用")

                booking_code = "RP-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[-16:]
                cursor.execute(
                    """INSERT INTO bookings
                       (booking_code, task_id, actor_id, provider_id, availability_id, issue_type,
                        issue_summary, estimate_low, estimate_high, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'REQUESTED')""",
                    (
                        booking_code, event["task_id"], event["actor_id"], event["provider_id"],
                        event["slot_id"], event["issue_type"], event["issue_summary"],
                        event["estimate_low"], event["estimate_high"],
                    ),
                )
                cursor.execute("UPDATE provider_availability SET status='BOOKED' WHERE id=%s", (event["slot_id"],))
                cursor.execute("SELECT name FROM providers WHERE id=%s", (event["provider_id"],))
                provider = cursor.fetchone()
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


def initialize_demo_data() -> dict:
    schema_path = Path(__file__).with_name("schema.sql")
    statements = [statement.strip() for statement in schema_path.read_text().split(";") if statement.strip()]
    providers = [
        ("安心居家水電", "台北市", "信義區", 4.9, 186),
        ("台北快速水電", "台北市", "信義區", 4.8, 241),
        ("好師傅工程", "台北市", "大安區", 4.7, 159),
        ("家安水電行", "台北市", "松山區", 4.8, 203),
        ("永順修繕", "台北市", "中山區", 4.6, 128),
        ("城市水電服務", "台北市", "內湖區", 4.7, 174),
        ("南港安心工程", "台北市", "南港區", 4.5, 96),
        ("大安專業水電", "台北市", "大安區", 4.9, 275),
        ("松山即刻修", "台北市", "松山區", 4.6, 112),
        ("中山水電幫手", "台北市", "中山區", 4.8, 190),
        ("內湖家庭修繕", "台北市", "內湖區", 4.7, 143),
        ("信義好鄰居水電", "台北市", "信義區", 4.6, 105),
    ]
    issue_types = ("plumbing_leak", "plumbing_clog", "electrical_power", "electrical_light")
    prices = (900, 1100, 1200, 1300, 1500, 1700, 1900, 2200, 2500, 2800)
    now_local = datetime.now(TAIPEI_TZ).replace(minute=0, second=0, microsecond=0)
    now_utc = now_local.astimezone(timezone.utc).replace(tzinfo=None)

    with connection() as db:
        with db.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in ("bookings", "provider_availability", "provider_services", "repair_events", "providers"):
                cursor.execute(f"TRUNCATE TABLE {table}")
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
            cursor.executemany(
                "INSERT INTO providers (name,city,district,rating,completed_jobs,is_active) VALUES (%s,%s,%s,%s,%s,TRUE)",
                providers,
            )
            cursor.execute("SELECT id, district FROM providers ORDER BY id")
            provider_rows = cursor.fetchall()
            services = [(p["id"], issue, 500 + (p["id"] % 3) * 100) for p in provider_rows for issue in issue_types]
            cursor.executemany(
                "INSERT INTO provider_services (provider_id,issue_type,base_visit_fee) VALUES (%s,%s,%s)", services
            )
            availability = []
            for provider in provider_rows:
                for day in range(1, 5):
                    for hour in (10, 14, 18):
                        local_slot = (now_local + timedelta(days=day)).replace(hour=hour)
                        utc_slot = local_slot.astimezone(timezone.utc).replace(tzinfo=None)
                        availability.append((provider["id"], utc_slot))
            cursor.executemany(
                "INSERT INTO provider_availability (provider_id,start_at,status) VALUES (%s,%s,'AVAILABLE')",
                availability,
            )
            events = []
            districts = [p[2] for p in providers]
            for index in range(120):
                issue = issue_types[index % len(issue_types)]
                price = prices[(index * 3) % len(prices)] + (index % 4) * 100
                events.append(
                    (
                        issue, "台北市", districts[index % len(districts)],
                        json.dumps({"demo": True, "severity": (index % 3) + 1}),
                        price, 45 + (index % 6) * 15, now_utc - timedelta(days=index + 1),
                    )
                )
            cursor.executemany(
                """INSERT INTO repair_events
                   (issue_type,city,district,issue_facts_json,final_price,duration_minutes,completed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                events,
            )
            db.commit()
    return {"initialized": True, "providers": len(providers), "repair_events": len(events)}


def lambda_handler(event, context):
    try:
        tool_name = _tool_name(event, context)
        if tool_name == "get_repair_options":
            return get_repair_options(event)
        if tool_name == "create_repair_booking":
            return create_repair_booking(event)
        if tool_name == "initialize_demo_data":
            return initialize_demo_data()
        raise ValueError(f"unknown tool: {tool_name}")
    except Exception as error:
        logger.exception("Repair operation failed")
        return {"error": {"type": type(error).__name__, "message": str(error)}}

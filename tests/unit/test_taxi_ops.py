import unittest
from datetime import datetime
from unittest.mock import patch

from services.taxi_ops import lambda_function


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


class TaxiOpsTests(unittest.TestCase):
    def test_lookup_maps_three_drivers_from_shared_cms(self):
        rows = []
        for driver_id in range(1, 4):
            for slot_index, hour in enumerate((2, 6), start=1):
                rows.append(
                    {
                        "driver_id": driver_id,
                        "fleet_name": f"接送車隊 {driver_id}",
                        "driver_name": f"接送司機 {driver_id}",
                        "vehicle_reg_number": f"TAX-{driver_id:04d}",
                        "city": "台北市",
                        "phone": f"02-2200-000{driver_id}",
                        "rating": 4.9 - driver_id / 10,
                        "description": None,
                        "slot_id": driver_id * 10 + slot_index,
                        "start_at": datetime(2026, 8, 3, hour, 0, 0),
                    }
                )
        fake_connection = _Connection(rows)
        with patch.object(lambda_function, "connection", return_value=fake_connection):
            result = lambda_function.get_taxi_options(
                {"task_id": "taxi-task", "city": "台北市"}
            )

        self.assertEqual(len(result["options"]), 3)
        self.assertEqual(result["options"][0]["phone"], "02-2200-0001")
        self.assertEqual(len(result["options"][0]["available_slots"]), 2)
        self.assertIn("cms_homepage_service_type_13", fake_connection.cursor_instance.query)
        self.assertEqual(fake_connection.cursor_instance.parameters, ("台北市",))

    def test_lookup_rejects_extra_fields(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            lambda_function.get_taxi_options(
                {
                    "task_id": "taxi-task",
                    "city": "台北市",
                    "medical_condition": "must-not-pass",
                }
            )

    def test_lookup_fails_instead_of_returning_fewer_than_three(self):
        with patch.object(lambda_function, "connection", return_value=_Connection([])):
            with self.assertRaisesRegex(RuntimeError, "不足三位"):
                lambda_function.get_taxi_options(
                    {"task_id": "taxi-task", "city": "台北市"}
                )


if __name__ == "__main__":
    unittest.main()

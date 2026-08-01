import unittest
from datetime import datetime
from unittest.mock import patch

from services.repair_ops import lambda_function
from services.repair_ops.lambda_function import percentile


class _Cursor:
    def __init__(self, result_sets):
        self.result_sets = iter(result_sets)
        self.current = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters):
        self.queries.append((query, parameters))
        self.current = next(self.result_sets)

    def fetchall(self):
        return self.current


class _Connection:
    def __init__(self, result_sets):
        self.cursor_instance = _Cursor(result_sets)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


class EstimateTests(unittest.TestCase):
    def test_percentile_range_is_rounded_to_hundreds(self):
        values = [900, 1100, 1200, 1300, 1500, 1700, 1900, 2200, 2500, 2800]
        self.assertEqual(percentile(values, 0.25), 1200)
        self.assertEqual(percentile(values, 0.75), 2100)

    def test_percentile_rejects_empty_history(self):
        with self.assertRaises(ValueError):
            percentile([], 0.25)

    def test_lookup_maps_shared_cms_provider_fields(self):
        prices = [{"final_price": value} for value in range(1000, 2000, 100)]
        provider_rows = []
        for provider_id in range(1, 4):
            for slot_index, hour in enumerate((2, 6), start=1):
                provider_rows.append(
                    {
                        "provider_id": provider_id,
                        "name": f"CMS 水電 {provider_id}",
                        "city": "台北市",
                        "district": "士林區",
                        "address": f"台北市士林區測試路{provider_id}號",
                        "phone": f"02-2000-000{provider_id}",
                        "rating": 4.9 - provider_id / 10,
                        "base_visit_fee": 500 + provider_id * 100,
                        "slot_id": provider_id * 10 + slot_index,
                        "start_at": datetime(2026, 8, 3, hour, 0, 0),
                    }
                )
        fake_connection = _Connection([prices, provider_rows])
        with patch.object(lambda_function, "connection", return_value=fake_connection):
            result = lambda_function.get_repair_options(
                {
                    "task_id": "task-1",
                    "issue_type": "plumbing_leak",
                    "city": "台北市",
                    "district": "士林區",
                    "issue_summary": "廚房水管漏水",
                }
            )

        self.assertEqual(len(result["options"]), 3)
        self.assertEqual(result["options"][0]["address"], "台北市士林區測試路1號")
        self.assertEqual(result["options"][0]["phone"], "02-2000-0001")
        self.assertEqual(len(result["options"][0]["available_slots"]), 2)
        self.assertNotIn("completed_jobs", result["options"][0])
        provider_query = fake_connection.cursor_instance.queries[-1][0]
        self.assertIn("cms_homepage_service_type_10", provider_query)
        self.assertIn("agent_repair_availability", provider_query)

    def test_lookup_rejects_unsupported_fields(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            lambda_function.get_repair_options(
                {
                    "task_id": "task-1",
                    "issue_type": "plumbing_leak",
                    "city": "台北市",
                    "district": "士林區",
                    "password": "must-not-pass",
                }
            )


if __name__ == "__main__":
    unittest.main()

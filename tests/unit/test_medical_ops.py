import unittest
from unittest.mock import patch

from services.medical_ops import lambda_function


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, parameters):
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


class MedicalOpsTests(unittest.TestCase):
    def test_lookup_returns_three_virtual_line_contacts(self):
        rows = [
            {
                "pharmacy_id": index,
                "name": f"藥局 {index}",
                "city": "台北市",
                "district": "信義區",
                "address": f"測試路 {index} 號",
                "rating": 4.9,
                "pharmacist_name": f"藥師 {index}",
                "line_id": f"@demo-{index}",
            }
            for index in range(1, 4)
        ]
        fake_connection = _Connection(rows)
        with patch.object(lambda_function, "connection", return_value=fake_connection):
            result = lambda_function.get_pharmacy_options(
                {"task_id": "task-1", "city": "台北市", "district": "信義區"}
            )
        self.assertEqual(len(result["options"]), 3)
        self.assertEqual(result["options"][0]["line_id"], "@demo-1")
        self.assertEqual(fake_connection.cursor_instance.parameters, ("台北市", "信義區"))

    def test_lookup_rejects_medical_or_personal_fields(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            lambda_function.get_pharmacy_options(
                {
                    "task_id": "task-1",
                    "city": "台北市",
                    "district": "信義區",
                    "medication": "must-not-be-accepted",
                }
            )

    def test_lookup_fails_instead_of_returning_fewer_than_three(self):
        with patch.object(lambda_function, "connection", return_value=_Connection([])):
            with self.assertRaisesRegex(RuntimeError, "不足三間"):
                lambda_function.get_pharmacy_options(
                    {"task_id": "task-1", "city": "台北市", "district": "信義區"}
                )


if __name__ == "__main__":
    unittest.main()

import unittest

from services.repair_ops.lambda_function import percentile


class EstimateTests(unittest.TestCase):
    def test_percentile_range_is_rounded_to_hundreds(self):
        values = [900, 1100, 1200, 1300, 1500, 1700, 1900, 2200, 2500, 2800]
        self.assertEqual(percentile(values, 0.25), 1200)
        self.assertEqual(percentile(values, 0.75), 2100)

    def test_percentile_rejects_empty_history(self):
        with self.assertRaises(ValueError):
            percentile([], 0.25)


if __name__ == "__main__":
    unittest.main()

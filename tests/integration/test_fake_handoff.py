import os
import unittest

from apps.orchestrator import main, task_state


class FakeHandoffIntegrationTests(unittest.TestCase):
    def setUp(self):
        task_state.MEMORY_ID = None
        task_state.clear_local_states()
        os.environ["REWARD_POINTS_ENABLED"] = "false"

    def tearDown(self):
        os.environ.pop("REWARD_POINTS_ENABLED", None)

    def test_backend_is_reported_and_task_is_sticky(self):
        first = main.process_turn("廚房水管漏水", "session-1", "actor-1")
        second = main.process_turn("每秒一滴", "session-1", "actor-1")
        self.assertEqual(first["specialist_backend"], "fake")
        self.assertEqual(second["routing"]["sticky_task_id"], first["specialist"]["task_id"])
        self.assertEqual(second["specialist"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()

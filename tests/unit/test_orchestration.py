import unittest

from apps.orchestrator import main as orchestrator
from apps.orchestrator import task_state
from apps.orchestrator.routing import classify_route
from shared.contracts import ActiveTask, IntentName, RouteAction, SpecialistResponse, TaskStatus


class RoutingTests(unittest.TestCase):
    def test_supported_routes(self):
        cases = [
            ("廚房水管漏水", "plumbing_leak"),
            ("水龍頭一直滴水", "plumbing_leak"),
            ("馬桶堵塞了", "plumbing_clog"),
            ("浴室排水阻塞", "plumbing_clog"),
            ("插座突然沒電", "electrical_power"),
            ("家裡一直跳電", "electrical_power"),
            ("客廳燈具不亮", "electrical_light"),
        ]
        for message, sub_intent in cases:
            with self.subTest(message=message):
                route = classify_route(message)
                self.assertEqual(route.intent, IntentName.REPAIR)
                self.assertEqual(route.sub_intent, sub_intent)
                self.assertEqual(route.action, RouteAction.DISPATCH)

    def test_medical_routes_to_pharmacist_contact_agent(self):
        for message in (
            "我想找附近藥局",
            "要去哪裡領藥",
            "想找藥師的 LINE",
            "我有處方簽想領，我住在台北市士林區，我可以去哪邊領",
        ):
            with self.subTest(message=message):
                route = classify_route(message)
                self.assertEqual(route.intent, IntentName.MEDICAL)
                self.assertEqual(route.sub_intent, "pharmacist_contact")
                self.assertEqual(route.target_agent, "medical-agent")
                self.assertEqual(route.action, RouteAction.DISPATCH)

    def test_medical_task_is_sticky(self):
        task = ActiveTask(
            task_id="medical-task-1",
            target_agent="medical-agent",
            intent="pharmacist_contact",
            missing_fields=["city", "district"],
        )
        route = classify_route("台北市信義區", task)
        self.assertEqual(route.intent, IntentName.MEDICAL)
        self.assertEqual(route.target_agent, "medical-agent")
        self.assertEqual(route.sticky_task_id, "medical-task-1")

    def test_taxi_routes_to_taxi_agent(self):
        for message in (
            "我想叫車去醫院",
            "幫長輩預約無障礙車",
            "需要輪椅接送",
            "可以幫我預約計程車嗎",
        ):
            with self.subTest(message=message):
                route = classify_route(message)
                self.assertEqual(route.intent, IntentName.TAXI)
                self.assertEqual(route.sub_intent, "accessible_ride")
                self.assertEqual(route.target_agent, "taxi-agent")
                self.assertEqual(route.action, RouteAction.DISPATCH)

    def test_taxi_task_is_sticky(self):
        task = ActiveTask(
            task_id="taxi-task-1",
            target_agent="taxi-agent",
            intent="accessible_ride",
            missing_fields=["destination"],
        )
        route = classify_route("要去台大醫院", task)
        self.assertEqual(route.intent, IntentName.TAXI)
        self.assertEqual(route.target_agent, "taxi-agent")
        self.assertEqual(route.sticky_task_id, "taxi-task-1")

    def test_platform_help_routes(self):
        for message in ("你好", "這個平台怎麼使用", "你們怎麼收費", "目前支援什麼服務"):
            with self.subTest(message=message):
                self.assertEqual(classify_route(message).intent, IntentName.PLATFORM_HELP)

    def test_unsupported_routes(self):
        for message in ("我想預約搬家", "需要居家清潔", "可以幫忙打掃嗎", "我要除蟲"):
            with self.subTest(message=message):
                route = classify_route(message)
                self.assertEqual(route.intent, IntentName.UNSUPPORTED_SERVICE)
                self.assertEqual(route.action, RouteAction.REPLY)

    def test_unknown_requires_clarification(self):
        for message in ("家裡有問題", "可以幫我嗎", "怪怪的", "我需要服務"):
            with self.subTest(message=message):
                route = classify_route(message)
                self.assertEqual(route.intent, IntentName.UNKNOWN)
                self.assertTrue(route.needs_clarification)

    def test_safety_alerts(self):
        self.assertEqual(classify_route("插座冒煙").safety_alert, "electrical_danger")
        self.assertEqual(classify_route("水管爆管一直噴").safety_alert, "shut_off_water")

    def test_active_task_sticky_routing(self):
        task = ActiveTask(task_id="task-1", intent="plumbing_leak", missing_fields=["leak_rate"])
        route = classify_route("每秒一滴", task)
        self.assertEqual(route.action, RouteAction.DISPATCH)
        self.assertEqual(route.sticky_task_id, "task-1")
        self.assertEqual(route.target_agent, "repair-agent")

    def test_active_task_cancel_and_new_task(self):
        task = ActiveTask(task_id="task-1", intent="plumbing_leak", missing_fields=["leak_rate"])
        self.assertEqual(classify_route("先不用了", task).action, RouteAction.CANCEL)
        self.assertEqual(classify_route("另外客廳的燈也不亮", task).action, RouteAction.CLARIFY)


class VerticalFlowTests(unittest.TestCase):
    def setUp(self):
        task_state.MEMORY_ID = None
        task_state.clear_local_states()

    def test_repair_follow_up_completes_same_task(self):
        first = orchestrator.process_turn("廚房水管漏水", "session-1", "actor-1")
        self.assertEqual(first["routing"]["intent"], "repair")
        self.assertEqual(first["specialist"]["status"], "needs_input")
        self.assertEqual(first["active_task"]["missing_fields"], ["leak_rate"])
        task_id = first["active_task"]["task_id"]

        second = orchestrator.process_turn("每秒一滴", "session-1", "actor-1")
        self.assertEqual(second["routing"]["sticky_task_id"], task_id)
        self.assertEqual(second["specialist"]["status"], "completed")
        self.assertTrue(second["specialist"]["data"]["ready_for_matching"])
        self.assertIsNone(second["active_task"])

    def test_task_isolated_by_session(self):
        orchestrator.process_turn("廚房水管漏水", "session-a", "actor-1")
        other = orchestrator.process_turn("你好", "session-b", "actor-1")
        self.assertEqual(other["routing"]["intent"], "platform_help")
        self.assertIsNone(other["active_task"])

    def test_cancel_clears_task(self):
        orchestrator.process_turn("廚房水管漏水", "session-c", "actor-1")
        cancelled = orchestrator.process_turn("先不用了", "session-c", "actor-1")
        self.assertEqual(cancelled["routing"]["action"], "cancel")
        self.assertIsNone(cancelled["active_task"])

    def test_safety_message_precedes_question(self):
        response = orchestrator.process_turn("浴室插座冒煙", "session-d", "actor-1")
        self.assertIn("不要觸碰", response["result"])
        self.assertEqual(response["routing"]["safety_alert"], "electrical_danger")

    def test_structured_options_are_persisted_for_selection_turn(self):
        specialist = SpecialistResponse(
            task_id="task-options",
            status=TaskStatus.NEEDS_INPUT,
            message="請選擇廠商",
            data={
                "known_facts": {"city": "台北市", "district": "信義區"},
                "stage": "awaiting_selection",
                "estimate": {"low": 1200, "high": 1900},
                "provider_options": [{"provider_id": 1, "name": "安心居家水電"}],
            },
        )
        facts = orchestrator._next_known_facts(specialist, {})
        self.assertEqual(facts["stage"], "awaiting_selection")
        self.assertEqual(facts["estimate"]["low"], 1200)
        self.assertEqual(facts["provider_options"][0]["provider_id"], 1)

    def test_taxi_driver_options_are_persisted_for_selection_turn(self):
        specialist = SpecialistResponse(
            task_id="taxi-options",
            agent="taxi-agent",
            status=TaskStatus.NEEDS_INPUT,
            message="請選擇司機",
            data={
                "known_facts": {"pickup_city": "台北市", "pickup_district": "士林區"},
                "stage": "awaiting_selection",
                "driver_options": [{"driver_id": 1, "name": "安心接送司機"}],
            },
        )
        facts = orchestrator._next_known_facts(specialist, {})
        self.assertEqual(facts["stage"], "awaiting_selection")
        self.assertEqual(facts["driver_options"][0]["driver_id"], 1)

    def test_medical_handoff_drops_medical_and_personal_details(self):
        message, facts = orchestrator._medical_handoff_input(
            "我在台北市信義區，藥名與電話都不應送過去",
            {"condition": "sensitive", "city": "新北市"},
        )
        self.assertEqual(facts, {"city": "台北市", "district": "信義區"})
        self.assertEqual(message, "只使用以下位置資料：城市=台北市、行政區=信義區")
        self.assertNotIn("藥名", message)
        self.assertNotIn("電話", message)

    def test_medical_handoff_extracts_shilin_from_full_request(self):
        original = "我有處方簽想領，我住在台北市士林區，我可以去哪邊領"
        message, facts = orchestrator._medical_handoff_input(original, {})
        self.assertEqual(facts, {"city": "台北市", "district": "士林區"})
        self.assertEqual(message, "只使用以下位置資料：城市=台北市、行政區=士林區")
        self.assertNotIn("處方", message)

    def test_medical_city_follow_up_does_not_overwrite_saved_district(self):
        message, facts = orchestrator._medical_handoff_input(
            "台北市",
            {"district": "士林區"},
        )
        self.assertEqual(facts, {"city": "台北市", "district": "士林區"})
        self.assertEqual(message, "只使用以下位置資料：城市=台北市、行政區=士林區")


if __name__ == "__main__":
    unittest.main()

import os
import unittest

from apps.orchestrator import main as orchestrator
from apps.orchestrator import profile as profile_module
from apps.orchestrator import routing
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

    def test_active_task_switches_on_cross_domain_intent(self):
        taxi_task = ActiveTask(
            task_id="taxi-1",
            target_agent="taxi-agent",
            intent="accessible_ride",
            missing_fields=["destination"],
        )
        switched = classify_route("我要找藥局", taxi_task)
        self.assertEqual(switched.action, RouteAction.DISPATCH)
        self.assertEqual(switched.target_agent, "medical-agent")
        self.assertEqual(switched.intent, IntentName.MEDICAL)
        self.assertIsNone(switched.sticky_task_id)

        repair_task = ActiveTask(
            task_id="repair-1",
            target_agent="repair-agent",
            intent="plumbing_leak",
            missing_fields=["leak_rate"],
        )
        to_taxi = classify_route("我想叫車去醫院", repair_task)
        self.assertEqual(to_taxi.action, RouteAction.DISPATCH)
        self.assertEqual(to_taxi.target_agent, "taxi-agent")
        self.assertIsNone(to_taxi.sticky_task_id)

    def test_active_task_same_domain_keyword_stays_sticky(self):
        taxi_task = ActiveTask(
            task_id="taxi-1",
            target_agent="taxi-agent",
            intent="accessible_ride",
            missing_fields=["special_needs"],
        )
        route = classify_route("需要輪椅接送", taxi_task)
        self.assertEqual(route.action, RouteAction.DISPATCH)
        self.assertEqual(route.target_agent, "taxi-agent")
        self.assertEqual(route.sticky_task_id, "taxi-1")


class VerticalFlowTests(unittest.TestCase):
    def setUp(self):
        task_state.MEMORY_ID = None
        task_state.clear_local_states()
        # Keep the suite offline: the points integration is display-only and
        # must not turn a completed-task assertion into a live network call.
        os.environ["REWARD_POINTS_ENABLED"] = "false"

    def tearDown(self):
        os.environ.pop("REWARD_POINTS_ENABLED", None)

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

    def test_cross_domain_switch_starts_new_task(self):
        first = orchestrator.process_turn("廚房水管漏水", "session-switch", "actor-1")
        repair_task_id = first["active_task"]["task_id"]
        second = orchestrator.process_turn("我要找藥局", "session-switch", "actor-1")
        self.assertEqual(second["routing"]["target_agent"], "medical-agent")
        self.assertEqual(second["routing"]["intent"], "medical")
        self.assertIsNone(second["routing"]["sticky_task_id"])
        self.assertNotEqual(second["specialist"]["task_id"], repair_task_id)

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

    def test_shared_profile_seeds_location_after_domain_switch(self):
        # A prior agent (e.g. taxi) already learned the user's location + needs.
        task_state.save_turn(
            "session-profile", "u", "a", None, None, None,
            {"city": "台北市", "district": "士林區", "special_needs": "輪椅"},
        )
        result = orchestrator.process_turn("廚房水管漏水", "session-profile", "actor-1")
        facts = result["active_task"]["known_facts"]
        # Repair no longer has to re-ask for the location it never collected.
        self.assertEqual(facts.get("city"), "台北市")
        self.assertEqual(facts.get("district"), "士林區")
        # Wheelchair need is not a repair fact, so it is not injected there,
        # but it stays remembered in the session profile.
        self.assertNotIn("special_needs", facts)
        self.assertEqual(result["shared_profile"]["special_needs"], "輪椅")

    def test_shared_profile_persists_across_turns(self):
        task_state.save_turn(
            "session-persist", "u", "a", None, None, None,
            {"city": "新北市", "district": "板橋區"},
        )
        orchestrator.process_turn("廚房水管漏水", "session-persist", "actor-1")
        second = orchestrator.process_turn("每秒一滴", "session-persist", "actor-1")
        self.assertEqual(second["shared_profile"]["city"], "新北市")
        self.assertEqual(second["shared_profile"]["district"], "板橋區")


class SharedProfileTests(unittest.TestCase):
    def test_taxi_location_translates_to_repair_fact_keys(self):
        taxi_facts = {"pickup_city": "台北市", "pickup_district": "士林區", "special_needs": "輪椅"}
        profile = profile_module.merge_profile({}, "taxi-agent", taxi_facts)
        self.assertEqual(profile, {"city": "台北市", "district": "士林區", "special_needs": "輪椅"})

        repair_seed = profile_module.seed_task_facts("repair-agent", profile)
        self.assertEqual(repair_seed, {"city": "台北市", "district": "士林區"})

        taxi_seed = profile_module.seed_task_facts("taxi-agent", profile)
        self.assertEqual(
            taxi_seed,
            {"pickup_city": "台北市", "pickup_district": "士林區", "special_needs": "輪椅"},
        )

    def test_medical_seed_excludes_non_location_entities(self):
        profile = {"city": "台北市", "district": "士林區", "special_needs": "輪椅"}
        medical_seed = profile_module.seed_task_facts("medical-agent", profile)
        self.assertEqual(medical_seed, {"city": "台北市", "district": "士林區"})

    def test_empty_values_are_not_stored(self):
        profile = profile_module.merge_profile({}, "repair-agent", {"city": "", "district": None})
        self.assertEqual(profile, {})

    def test_last_agent_is_not_seeded_into_specialist_facts(self):
        profile = profile_module.remember_last_agent(
            {"city": "台北市"}, "taxi-agent"
        )
        self.assertEqual(profile_module.last_agent(profile), "taxi-agent")
        # The reserved key must never leak into a specialist's known_facts.
        self.assertNotIn(
            profile_module.LAST_AGENT_KEY,
            profile_module.seed_task_facts("repair-agent", profile),
        )


class SelectionRecoveryTests(unittest.TestCase):
    def setUp(self):
        task_state.MEMORY_ID = None
        task_state.clear_local_states()

    def test_looks_like_selection(self):
        self.assertTrue(
            routing.looks_like_selection("我要選第 1 位司機「周小姐」，時段（slot_id: 115）")
        )
        self.assertFalse(routing.looks_like_selection("我家有漏水"))

    def test_orphan_selection_gets_context_aware_recovery(self):
        # Simulate a prior taxi flow whose task is gone (e.g. dropped mid-booking).
        task_state.save_turn(
            "session-orphan", "u", "a", None, None, None,
            {"city": "台北市", "district": "士林區", "_last_agent": "taxi-agent"},
        )
        result = orchestrator.process_turn(
            "我要選第 1 位司機「周小姐」，時段 8/4 上午10:00（slot_id: 115）",
            "session-orphan",
            "actor-1",
        )
        # It references the接送 service instead of the generic dead-end reply.
        self.assertIn("接送預約", result["result"])
        self.assertNotIn("我還無法確定", result["result"])

    def test_generic_fallback_when_no_recent_service(self):
        result = orchestrator.process_turn("嗯嗯好喔", "session-empty", "actor-1")
        self.assertIn("接送", result["result"])  # copy now lists all three services

    def test_dispatch_records_last_agent(self):
        result = orchestrator.process_turn("廚房水管漏水", "session-last", "actor-1")
        self.assertEqual(result["shared_profile"]["_last_agent"], "repair-agent")


if __name__ == "__main__":
    unittest.main()

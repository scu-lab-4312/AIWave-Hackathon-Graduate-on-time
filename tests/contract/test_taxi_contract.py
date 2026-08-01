import unittest
from io import BytesIO

from adapters.agentcore_taxi import AgentCoreTaxiClient
from adapters.fake_taxi import FakeTaxiClient
from agents.taxi.schemas import DriverOption
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


class TaxiContractTests(unittest.TestCase):
    def request(self):
        return HandoffRequest(
            task_id="55555555-5555-4555-8555-555555555555",
            actor_id="actor-1",
            conversation_id="conversation-1",
            intent="accessible_ride",
            message="想從台北市士林區叫車去台大醫院",
        )

    def test_fake_fallback_never_invents_driver_or_booking(self):
        response = FakeTaxiClient().invoke(self.request())
        self.assertEqual(response.status, TaskStatus.FAILED)
        self.assertNotIn("driver_options", response.data)
        self.assertEqual(response.error["code"], "TAXI_AGENT_UNAVAILABLE")

    def test_agentcore_adapter_validates_runtime_response(self):
        request = self.request()
        specialist = SpecialistResponse(
            task_id=request.task_id,
            agent="taxi-agent",
            status=TaskStatus.NEEDS_INPUT,
            message="請問目的地？",
            data={"missing_fields": ["destination"]},
        )

        class RuntimeClient:
            def invoke_agent_runtime(self, **kwargs):
                self.kwargs = kwargs
                return {"response": BytesIO(specialist.model_dump_json().encode())}

        adapter = object.__new__(AgentCoreTaxiClient)
        adapter.runtime_arn = "arn:test"
        adapter.qualifier = "DEFAULT"
        adapter.client = RuntimeClient()
        response = adapter.invoke(request)
        self.assertEqual(response.agent, "taxi-agent")
        self.assertEqual(adapter.client.kwargs["runtimeSessionId"], request.task_id)

    def test_driver_contract_uses_cms_fields_without_fake_plate(self):
        option = DriverOption.model_validate(
            {
                "option_id": "driver-1",
                "driver_id": 1,
                "fleet_name": "安心接送車隊",
                "driver_name": "王大明",
                "vehicle_reg_number": "TAX-0001",
                "city": "台北市",
                "phone": "02-2200-0001",
                "rating": 4.8,
                "available_slots": [
                    {"slot_id": "1", "start_at": "2026-08-03T10:00:00+08:00"}
                ],
            }
        )
        dumped = option.model_dump()
        self.assertEqual(dumped["phone"], "02-2200-0001")
        self.assertEqual(dumped["vehicle_reg_number"], "TAX-0001")
        self.assertNotIn("address", dumped)


if __name__ == "__main__":
    unittest.main()

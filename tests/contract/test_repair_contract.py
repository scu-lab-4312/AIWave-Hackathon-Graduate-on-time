import unittest
from io import BytesIO

from adapters.agentcore_repair import AgentCoreRepairClient
from adapters.fake_repair import FakeRepairClient
from shared.contracts import HandoffRequest, SpecialistResponse, TaskStatus


class RepairContractTests(unittest.TestCase):
    def request(self):
        return HandoffRequest(
            task_id="11111111-1111-4111-8111-111111111111",
            actor_id="actor-1",
            conversation_id="conversation-1",
            intent="plumbing_leak",
            message="廚房水管漏水",
        )

    def test_fake_adapter_implements_specialist_contract(self):
        request = self.request()
        response = FakeRepairClient().invoke(request)
        validated = SpecialistResponse.model_validate(response)
        self.assertEqual(validated.task_id, request.task_id)
        self.assertEqual(validated.status.value, "needs_input")
        self.assertIn("missing_fields", validated.data)

    def test_agentcore_adapter_validates_runtime_response(self):
        request = self.request()
        specialist = SpecialistResponse(
            task_id=request.task_id,
            status=TaskStatus.NEEDS_INPUT,
            message="漏水速度多快？",
            data={"missing_fields": ["leak_rate"]},
        )

        class RuntimeClient:
            def invoke_agent_runtime(self, **kwargs):
                self.kwargs = kwargs
                return {"response": BytesIO(specialist.model_dump_json().encode())}

        adapter = object.__new__(AgentCoreRepairClient)
        adapter.runtime_arn = "arn:test"
        adapter.qualifier = "DEFAULT"
        adapter.client = RuntimeClient()
        response = adapter.invoke(request)
        self.assertEqual(response.task_id, request.task_id)
        self.assertEqual(adapter.client.kwargs["runtimeSessionId"], request.task_id)


if __name__ == "__main__":
    unittest.main()

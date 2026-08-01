import unittest

from adapters.fake_medical import FakeMedicalClient
from agents.medical.schemas import MedicalAssessment
from shared.contracts import HandoffRequest, TaskStatus


class MedicalContractTests(unittest.TestCase):
    def test_fake_fallback_never_invents_contacts(self):
        request = HandoffRequest(
            task_id="medical-task",
            actor_id="actor",
            conversation_id="conversation",
            intent="pharmacist_contact",
            message="尚未提供城市與行政區。",
        )
        response = FakeMedicalClient().invoke(request)
        self.assertEqual(response.status, TaskStatus.FAILED)
        self.assertEqual(response.data["known_facts"], {})
        self.assertEqual(response.error["code"], "MEDICAL_AGENT_UNAVAILABLE")

    def test_contacts_ready_contract_contains_line_contacts_only(self):
        assessment = MedicalAssessment.model_validate(
            {
                "status": "completed",
                "stage": "contacts_ready",
                "message": "找到三間虛擬藥局。",
                "pharmacy_options": [
                    {
                        "option_id": f"pharmacy-{index}",
                        "pharmacy_id": index,
                        "name": f"虛擬藥局 {index}",
                        "city": "台北市",
                        "district": "信義區",
                        "address": f"測試路 {index} 號",
                        "rating": 4.8,
                        "pharmacist_name": f"測試藥師 {index}",
                        "line_id": f"@demo-{index}",
                    }
                    for index in range(1, 4)
                ],
            }
        )
        self.assertEqual(len(assessment.pharmacy_options), 3)
        self.assertNotIn("pickup_request", assessment.model_dump())


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from alert_explanation.api import create_app

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(create_app())
        self.payload=json.loads((Path(__file__).resolve().parents[1]/"examples/m4-alert.json").read_text(encoding="utf-8-sig"))

    def test_endpoint_returns_eight_answers(self):
        r=self.client.post("/api/alerts/explain",json=self.payload)
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.json()["answers"]),8)
        self.assertFalse(r.json()["control_actions_executed"])

    def test_invalid_evidence_has_422(self):
        self.payload["data_acquisition"]["machine_id"]="wrong"
        r=self.client.post("/api/alerts/explain",json=self.payload)
        self.assertEqual(r.status_code,422)
        self.assertEqual(r.json()["error"],"Invalid backend evidence")

    def test_oversized_body_rejected(self):
        r=self.client.post("/api/alerts/explain",content=b"x"*(256*1024+1),headers={"Content-Type":"application/json"})
        self.assertEqual(r.status_code,413)

    def test_malformed_json(self):
        self.assertEqual(self.client.post("/api/alerts/explain",content="{",headers={"Content-Type":"application/json"}).status_code,422)

    def test_health_and_schema(self):
        self.assertFalse(self.client.get("/health").json()["ai_provider_configured"])
        schema=self.client.get("/api/alerts/explanation-schema").json()
        self.assertIn("answers",schema["properties"])

if __name__ == "__main__":
    unittest.main()


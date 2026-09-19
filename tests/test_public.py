import unittest
from fastapi.testclient import TestClient
from integration.api import create_app
from integration.config import Settings
from integration.runtime import Runtime

class PublicDeploymentTests(unittest.TestCase):
    def test_public_requires_operator_key_and_demo_data(self):
        with self.assertRaises(ValueError):
            create_app(Settings(public_site=True))
        with self.assertRaises(ValueError):
            create_app(Settings(mode='external',public_site=True,operator_key='x'*32))

    def test_viewers_cannot_mutate_and_operator_can(self):
        settings=Settings(database=':memory:',public_site=True,operator_key='test-only-key-12345678901234567890')
        runtime=Runtime(settings)
        try:
            with TestClient(create_app(settings,runtime=runtime,start_background=False)) as client:
                self.assertEqual(client.get('/').status_code,200)
                self.assertEqual(client.get('/api/dashboard').status_code,200)
                self.assertEqual(client.get('/api/access').json(),{'public':True,'can_control':False})
                for path,body in [('/api/demo/reset',{}),('/api/demo/fault/M4',{'fault_type':'STOPPED'}),
                                  ('/api/recovery/M4/correct',{}),('/api/scenarios/compare',{}),('/api/telemetry',{})]:
                    self.assertEqual(client.post(path,json=body).status_code,401)
                self.assertEqual(client.post('/api/demo/reset',headers={'Authorization':'Bearer invalid'}).status_code,401)
                headers={'Authorization':'Bearer '+settings.operator_key}
                self.assertTrue(client.get('/api/access',headers=headers).json()['can_control'])
                self.assertEqual(client.post('/api/demo/fault/M4',json={'fault_type':'STOPPED'},headers=headers).status_code,200)
                self.assertEqual(len(runtime.incidents),1)
                self.assertNotIn(settings.operator_key,client.get('/api/dashboard').text)
                self.assertEqual(client.get('/api/access').headers['cache-control'],'no-store')
        finally:
            runtime.close()

    def test_local_mode_keeps_existing_controls(self):
        runtime=Runtime(Settings(database=':memory:'))
        try:
            with TestClient(create_app(runtime=runtime,start_background=False)) as client:
                self.assertEqual(client.get('/api/access').json(),{'public':False,'can_control':True})
                self.assertEqual(client.post('/api/demo/reset').status_code,200)
        finally:
            runtime.close()


import json
import unittest
import httpx
from jobs_service.ai_setup import verify_provider
from jobs_service.policy import Blocked

class AiSetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_setup_checks_connection_without_a_fake_job(self):
        def handler(request):
            body=json.loads(request.content)
            self.assertNotIn('posting',body['messages'][0]['content'].lower())
            self.assertNotIn('verified_evidence',str(body))
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"ready":true}'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await verify_provider('openrouter','synthetic-key',client=client)

    async def test_no_credit_is_not_reported_as_a_job_metadata_error(self):
        def handler(request): return httpx.Response(402,json={'error':{'message':'synthetic secret must not be shown'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(Blocked) as caught: await verify_provider('openrouter','synthetic-key',client=client)
        self.assertEqual(caught.exception.code,'AI_INSUFFICIENT_CREDITS')

    async def test_invalid_handshake_cannot_activate_provider(self):
        def handler(request): return httpx.Response(200,json={'choices':[{'message':{'content':'{"job":null}'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(Blocked) as caught: await verify_provider('gateway','synthetic-key',client=client)
        self.assertEqual(caught.exception.code,'AI_HANDSHAKE_INVALID')

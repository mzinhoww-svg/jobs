import unittest
import httpx
from jobs_service.ai_diagnostics import diagnose

class AiDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_credit_error_is_identified_without_exposing_key_or_raw_message(self):
        def handler(request): return httpx.Response(402,json={'error':{'code':402,'message':'Not enough credits; synthetic-secret-key must never be shown'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await diagnose('openrouter','synthetic-secret-key',client)
        self.assertEqual(result['http_status'],402)
        self.assertEqual(result['category'],'INSUFFICIENT_CREDITS')
        self.assertNotIn('synthetic-secret-key',str(result))

    async def test_empty_truncated_model_response_is_distinct_from_bad_credential(self):
        def handler(request): return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':''}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await diagnose('openrouter','synthetic-key',client)
        self.assertEqual(result['category'],'MODEL_OUTPUT_TRUNCATED')
        self.assertEqual(result['http_status'],200)

    async def test_rejected_credentials_are_identified(self):
        def handler(request): return httpx.Response(401,json={'error':{'message':'key value should not be echoed'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await diagnose('gateway','synthetic-key',client)
        self.assertEqual(result['category'],'CREDENTIAL_REJECTED')
        self.assertEqual(result['analysis'],'AI_CREDENTIAL_REJECTED')

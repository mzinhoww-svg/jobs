import json
import tempfile
import time
import unittest
from pathlib import Path

import httpx

from jobs_service.api import create_app
from jobs_service.config import Settings
from jobs_service.store import Store


class DashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        token=self.root/'api-token'
        token.write_text('synthetic-dashboard-token-0123456789')
        token.chmod(0o600)
        self.settings=Settings(self.root,token,('example.com',))
        self.store=Store(self.root/'queue.sqlite3')
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.settings)),base_url='http://testserver')
        self.auth={'Authorization':'Bearer synthetic-dashboard-token-0123456789'}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.tmp.cleanup()

    async def test_bearer_whitespace_and_case_without_accepting_wrong_secret(self):
        for header in ('Bearer synthetic-dashboard-token-0123456789 ', 'bearer   synthetic-dashboard-token-0123456789'):
            r=await self.client.get('/applications',headers={'Authorization':header})
            self.assertEqual(r.status_code,200)
        for header in ('Bearer token2','Basic synthetic-dashboard-token-0123456789','Bearer'):
            self.assertEqual((await self.client.get('/applications',headers={'Authorization':header})).status_code,401)

    async def test_paginated_real_metadata_and_filtered_totals(self):
        for i in range(4):
            row,_=self.store.submit(f'https://example.com/jobs/{i}','prepare')
            with self.store.db() as db:
                db.execute('UPDATE applications SET status=?,payload=? WHERE id=?',('BLOQUEADA' if i==0 else 'RECEBIDA',json.dumps({'job':{'title':'100% Payments' if i==0 else 'Product Lead','company':'Fictional Labs','description':'DO_NOT_RETURN_RAW_PAGE'},'ats':'Greenhouse'}),row['id']))
        response=await self.client.get('/applications?limit=2&offset=0',headers=self.auth)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['X-Total-Count'],'4')
        self.assertEqual(len(response.json()),2)
        self.assertEqual(response.json()[0]['job']['company'],'Fictional Labs')
        self.assertIn('url',response.json()[0])
        self.assertNotIn('DO_NOT_RETURN_RAW_PAGE',response.text)
        next_page=(await self.client.get('/applications?limit=2&offset=2',headers=self.auth)).json()
        self.assertFalse(set(x['id'] for x in response.json())&set(x['id'] for x in next_page))
        filtered=await self.client.get('/applications?state=BLOQUEADA&q=%25',headers=self.auth)
        self.assertEqual(filtered.headers['X-Total-Count'],'1')
        self.assertTrue(filtered.json()[0]['can_resume'])
        self.assertEqual(filtered.json()[0]['job']['title'],'100% Payments')
        empty=await self.client.get('/applications',params={'q':"' OR 1=1 --"},headers=self.auth)
        self.assertEqual(empty.json(),[])
        self.assertEqual((await self.client.get('/applications?state=INVALID',headers=self.auth)).status_code,422)

    async def test_system_readiness_is_authenticated_and_contains_no_private_profile(self):
        self.assertEqual((await self.client.get('/system/status')).status_code,401)
        before=(await self.client.get('/system/status',headers=self.auth)).json()
        self.assertFalse(before['profile']['configured'])
        self.assertEqual(before['worker']['state'],'unknown')
        (self.root/'worker-heartbeat').write_text(str(time.time()))
        (self.root/'profile.json').write_text(json.dumps({'identity':{'full_name':'DO_NOT_RETURN_PERSONAL_NAME','preferred_email':'fixture@example.invalid'},'facts':[{'id':'1','text':'PRIVATE_CAREER_TEXT','confirmation':'confirmed','source_kind':'candidate_declaration','source':'synthetic test','date':'2026-10-27'}]}))
        self.store.submit('https://example.com/jobs/readiness','analyze')
        result=await self.client.get('/system/status',headers=self.auth)
        data=result.json()
        self.assertTrue(data['profile']['configured'])
        self.assertEqual(data['profile']['confirmed_facts'],1)
        self.assertEqual(data['worker']['state'],'ready')
        self.assertEqual(data['counts']['total'],1)
        self.assertNotIn('DO_NOT_RETURN_PERSONAL_NAME',result.text)
        self.assertNotIn('PRIVATE_CAREER_TEXT',result.text)
        self.assertNotIn('gmail',result.text.lower())
        self.assertFalse(data['capabilities']['workday'])
        self.assertFalse(data['capabilities']['appllama'])

    async def test_unconfirmed_and_uncertain_have_no_false_success_or_resume(self):
        row,_=self.store.submit('https://example.com/jobs/uncertain')
        self.store.claim('test')
        self.store.identify(row['id'],'greenhouse:fixture:123')
        self.store.submit_intent(row['id'],'test')
        self.store.finish(row['id'],'test','ENVIO_INCERTO','PORTAL_CONFIRMATION_NOT_OBSERVED')
        result=(await self.client.get('/applications/'+row['id'],headers=self.auth)).json()
        self.assertFalse(result['can_resume'])
        self.assertFalse(result['has_proof'])
        self.assertTrue(result['history'])
        self.assertEqual(result['status'],'ENVIO_INCERTO')

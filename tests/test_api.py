import tempfile
import unittest
from pathlib import Path
import httpx
from jobs_service.api import create_app
from jobs_service.config import Settings


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        p=Path(self.tmp.name)
        (p/'key').write_text('synthetic-test-token-0123456789abcdef')
        (p/'key').chmod(0o600)
        self.settings=Settings(p,p/'key',('example.com',))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.settings)),base_url='http://testserver')
        self.headers={'Authorization':'Bearer synthetic-test-token-0123456789abcdef'}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.tmp.cleanup()

    async def test_auth_and_persisted_submit(self):
        self.assertEqual((await self.client.post('/applications',json={'url':'https://example.com/jobs/1'})).status_code,401)
        r=await self.client.post('/applications',headers=self.headers,json={'url':'https://example.com/jobs/1','mode':'prepare'})
        self.assertEqual(r.status_code,201)
        id=r.json()['id']
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.settings)),base_url='http://testserver') as other:
            self.assertEqual((await other.get('/applications/'+id,headers=self.headers)).json()['status'],'RECEBIDA')
        self.assertEqual((await self.client.post('/applications',headers=self.headers,json={'url':'https://example.com/jobs/1','mode':'prepare'})).status_code,200)

    async def test_ssrf_unknown_host_and_invalid_mode(self):
        for u in ['https://127.0.0.1/', 'https://evil.invalid/']:
            self.assertEqual((await self.client.post('/applications',headers=self.headers,json={'url':u,'mode':'prepare'})).status_code,422)
        self.assertEqual((await self.client.post('/applications',headers=self.headers,json={'url':'https://example.com/','mode':'send-spam'})).status_code,422)

    async def test_safe_health_and_status(self):
        self.assertEqual((await self.client.get('/healthz')).json(),{'status':'ok'})
        self.assertEqual((await self.client.get('/applications',headers=self.headers)).json(),[])
        self.assertEqual((await self.client.get('/applications/missing',headers=self.headers)).status_code,404)

    async def test_mode_must_be_explicit(self):
        r=await self.client.post('/applications',headers=self.headers,json={'url':'https://example.com/jobs/2'})
        self.assertEqual(r.status_code,422)

    async def test_private_documents_require_auth_and_known_artifact(self):
        from jobs_service.store import Store
        row,_=Store(self.settings.data_dir/'queue.sqlite3').submit('https://example.com/job/9')
        folder=self.settings.data_dir/'applications'/row['id']
        folder.mkdir(parents=True)
        (folder/'cv.pdf').write_bytes(b'controlled synthetic PDF bytes')
        path='/applications/'+row['id']+'/documents/cv.pdf'
        self.assertEqual((await self.client.get(path)).status_code,401)
        self.assertEqual((await self.client.get(path,headers=self.headers)).content,b'controlled synthetic PDF bytes')
        self.assertEqual((await self.client.get(path.replace('cv.pdf','api-token'),headers=self.headers)).status_code,422)

    async def test_result_exposes_evidence_without_raw_page_or_profile(self):
        from jobs_service.store import Store
        store=Store(self.settings.data_dir/'queue.sqlite3')
        row,_=store.submit('https://example.com/job/10')
        store.claim('test')
        store.checkpoint(row['id'],'test','DOCUMENTOS_PRONTOS',{'job':{'title':'Example role','company':'Fictional','description':'private raw page'},'profile':{'secret':'never expose'},'documents':{'cv.pdf':{'sha256':'a'*64,'bytes':1000}}})
        result=(await self.client.get('/applications/'+row['id'],headers=self.headers)).json()
        self.assertEqual(result['result']['job']['title'],'Example role')
        self.assertEqual(result['result']['documents']['cv.pdf']['bytes'],1000)
        self.assertNotIn('private raw page',str(result))
        self.assertNotIn('never expose',str(result))

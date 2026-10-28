import json
import tempfile
import unittest
from pathlib import Path
import httpx
from jobs_service.api import create_app
from jobs_service.config import Settings
from jobs_service.policy import detect_ats
from jobs_service.store import Store
from jobs_service.worker import process

POSTING={'title':'Payments Lead','company':'Fictional Labs','country':'BR','language':'en','description':'Lead payment partnerships and product strategy. Coordinate operations and improve payment experiences.'}

class UniversalDocumentsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.settings=Settings(self.root,self.root/'missing-token',('job-boards.greenhouse.io',),auth_mode='none')
        self.store=Store(self.root/'queue.sqlite3')
        profile={'identity':{'full_name':'Fictional Candidate','preferred_email':'fixture@example.invalid'},'locations':{'brazil':{'cv_location':'São Paulo, Brazil'}},'facts':[{'id':'f1','text':'Structured payment partnerships and product strategy.','source':'synthetic fixture','date':'2026-10-27','source_kind':'candidate_declaration','confirmation':'confirmed'}]}
        (self.root/'profile.json').write_text(json.dumps(profile))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.settings)),base_url='http://testserver')
    async def asyncTearDown(self):
        await self.client.aclose();self.tmp.cleanup()

    async def test_manual_any_platform_persists_and_prepares_without_browser(self):
        response=await self.client.post('/applications',json={'url':'https://careers.example.org/job/abc','mode':'apply','posting':POSTING})
        self.assertEqual(response.status_code,201,response.text)
        id=response.json()['id']
        self.assertEqual(json.loads(Store(self.root/'queue.sqlite3').get(id)['payload'])['manual_posting']['title'],POSTING['title'])
        class NeverBrowse:
            def __init__(self,*args): raise AssertionError('Manual posting must not open a browser')
        await process(self.store.claim('fixture'),self.store,self.settings,NeverBrowse)
        row=self.store.get(id)
        self.assertEqual(row['status'],'DOCUMENTOS_PRONTOS',row['reason'])
        self.assertEqual(row['reason'],'MANUAL_SUBMISSION_REQUIRED')
        self.assertFalse(row['intent'])
        detail=(await self.client.get('/applications/'+id)).json()
        self.assertTrue(detail['has_documents']);self.assertFalse(detail['has_proof'])
        self.assertIn('tailoring',detail['result'])
        import io,zipfile
        bundle=await self.client.get('/applications/'+id+'/bundle')
        self.assertEqual(bundle.status_code,200)
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
            self.assertIn('cv.docx',z.namelist());self.assertIn('cover-letter.pdf',z.namelist())
            self.assertIn('tailoring-report.json',z.namelist())
            self.assertFalse(any('profile' in n or 'token' in n for n in z.namelist()))

    async def test_any_public_link_accepted_and_private_destinations_rejected(self):
        response=await self.client.post('/applications',json={'url':'https://mastercard.wd1.myworkdayjobs.com/en-US/Corporate/job/role','mode':'apply'})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual((await self.client.post('/applications',json={'url':'https://example.org/jobs/abc','mode':'prepare'})).status_code,201)
        for url in ['https://127.0.0.1/jobs/x','https://169.254.169.254/jobs/x']:
            response=await self.client.post('/applications',json={'url':url,'mode':'prepare'})
            self.assertEqual(response.status_code,422)
        response=await self.client.post('/applications',json={'url':'https://127.0.0.1/jobs/x','mode':'prepare','posting':POSTING})
        self.assertEqual(response.status_code,422)

    def test_platform_identification_is_distinct_from_automatic_submission(self):
        for url,expected in [('https://x.wd1.myworkdayjobs.com/job/role','Workday'),('https://jobs.lever.co/company/abc','Lever'),('https://company.gupy.io/jobs/123','Gupy'),('https://jobs.ashbyhq.com/company/abc','Ashby'),('https://jobs.smartrecruiters.com/company/123','SmartRecruiters'),('https://careers-company.icims.com/jobs/123','iCIMS'),('https://company.taleo.net/careersection/jobdetail.ftl?job=123','Taleo'),('https://careers.successfactors.com/job/abc','SuccessFactors'),('https://www.linkedin.com/jobs/view/123','LinkedIn'),('https://www.indeed.com/viewjob?jk=abc','Indeed')]:
            self.assertEqual(detect_ats(url,[])[0],expected)

    async def test_url_only_reads_public_page_and_uses_configured_ai_without_submission(self):
        from unittest.mock import AsyncMock,patch
        (self.root/'ai-config.json').write_text(json.dumps({'enabled':True,'provider':'openrouter','model':'deepseek/deepseek-v4.1-flash','api_key':'synthetic-key'}))
        (self.root/'ai-config.json').chmod(0o600)
        url='https://custom-careers.example.org/jobs/abc'
        response=await self.client.post('/applications',json={'url':url,'mode':'apply'})
        self.assertEqual(response.status_code,201)
        analysis={'job':POSTING,'ranked_fact_ids':['f1'],'matches':[{'fact_id':'f1','requirement':'Lead payment partnerships and product strategy.'}],'model':'deepseek/deepseek-v4.1-flash','provider':'openrouter'}
        with patch('jobs_service.worker.read_posting',new=AsyncMock(return_value=(POSTING,POSTING['description']))) as reader,patch('jobs_service.worker.analyze_posting',new=AsyncMock(return_value=analysis)) as ai:
            await process(self.store.claim('fixture'),self.store,self.settings)
            reader.assert_awaited_once_with(url,self.settings)
            self.assertEqual(ai.await_count,1)
        final=self.store.get(response.json()['id'])
        self.assertEqual(final['status'],'DOCUMENTOS_PRONTOS',final['reason'])
        self.assertFalse(final['intent'])
        report=json.loads((self.root/'applications'/final['id']/'tailoring-report.json').read_text())
        self.assertEqual(report['ai']['provider'],'openrouter')
        self.assertEqual(report['selected_fact_ids'],['f1'])

    async def test_editing_posting_does_not_offer_old_documents(self):
        response=await self.client.post('/applications',json={'url':'https://example.org/job/edit','mode':'prepare','posting':POSTING})
        id=response.json()['id']
        class NeverBrowse:
            def __init__(self,*args): raise AssertionError('Manual posting must not browse')
        await process(self.store.claim('fixture'),self.store,self.settings,NeverBrowse)
        self.assertEqual((await self.client.get('/applications/'+id+'/bundle')).status_code,200)
        updated={**POSTING,'title':'Different Position'}
        response=await self.client.post('/applications',json={'url':'https://example.org/job/edit','mode':'prepare','posting':updated})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['has_documents'])
        self.assertEqual((await self.client.get('/applications/'+id+'/bundle')).status_code,404)
        self.assertEqual((await self.client.get('/applications/'+id+'/documents/cv.pdf')).status_code,404)

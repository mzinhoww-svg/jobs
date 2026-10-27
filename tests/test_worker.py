import json
import tempfile
import unittest
from pathlib import Path
from jobs_service.store import Store
from jobs_service.config import Settings
from jobs_service.worker import process, verification_answers
from jobs_service.policy import Blocked
from jobs_service.browser import BrowserSession

HTML='''<html lang="en"><h1>Payments Lead</h1><script type="application/ld+json">{"@type":"JobPosting","title":"Payments Lead","description":"Develop payment partnerships","hiringOrganization":{"name":"Example Industries"},"jobLocation":{"address":{"addressCountry":"BR"}},"baseSalary":{"currency":"BRL","value":{"minValue":30000,"maxValue":40000,"unitText":"MONTH"}}}</script>
<form id="application_form"><label>First Name<input required></label><label>Last Name<input required></label><label>Email<input required></label><label>Resume<input type="file" required></label><button>Submit application</button></form>
<script>document.querySelector('form').onsubmit=e=>{e.preventDefault();document.querySelector('form').remove();document.body.insertAdjacentHTML('beforeend','<h2>Your application has been received. Requisition 123</h2>');}</script></html>'''


class FixtureSession(BrowserSession):
    async def __aenter__(self):
        await super().__aenter__()
        async def fixture(route): await route.fulfill(status=200,content_type='text/html',body=HTML)
        await self.context.route('https://job-boards.greenhouse.io/**',fixture)
        return self


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'api-token').write_text('synthetic-token-01234567890123456789')
        (self.root/'api-token').chmod(0o600)
        self.settings=Settings(self.root,self.root/'api-token',('job-boards.greenhouse.io',))
        self.store=Store(self.root/'queue.sqlite3')
        profile={'identity':{'full_name':'Fictional Candidate','preferred_email':'candidate@example.invalid'},'locations':{'brazil':{'cv_location':'São Paulo, Brazil'}},'compensation':{'salary_base_floors':{'BRL':{'monthly':20000},'USD':{'annual':96000}}},'facts':[{'id':'f1','text':'Structured payments partnerships.','source_kind':'candidate_declaration','confirmation':'confirmed','source':'synthetic controlled fixture','date':'2026-10-27'}]}
        (self.root/'profile.json').write_text(json.dumps(profile))

    async def asyncTearDown(self): self.tmp.cleanup()

    async def test_controlled_pipeline_proof_and_restart_no_duplicate(self):
        a,_=self.store.submit('https://job-boards.greenhouse.io/example/jobs/123')
        row=self.store.claim('test')
        await process(row,self.store,self.settings,FixtureSession)
        final=Store(self.root/'queue.sqlite3').get(a['id'])
        self.assertEqual(final['status'],'ENVIADA_COMPROVADA',final['reason'])
        self.assertTrue(json.loads(final['payload'])['proof']['confirmation_hash'])
        self.assertTrue((self.root/'applications'/a['id']/'cv.pdf').is_file())
        self.assertIsNone(Store(self.root/'queue.sqlite3').claim('restart'))
        _,dup=self.store.submit(a['url'])
        self.assertTrue(dup)

    async def test_prepare_never_uploads_or_submits(self):
        a,_=self.store.submit('https://job-boards.greenhouse.io/example/jobs/123','prepare')
        await process(self.store.claim('test'),self.store,self.settings,FixtureSession)
        final=self.store.get(a['id'])
        self.assertEqual(final['status'],'DOCUMENTOS_PRONTOS')
        self.assertFalse(final['intent'])

    async def test_missing_gmail_is_honest_verification_blocker(self):
        async with FixtureSession(self.settings) as session:
            await session.page.set_content('<form><label>Verification code<input required></label></form>')
            with self.assertRaises(Blocked) as e:
                await verification_answers(session.page,{'identity':{'preferred_email':'candidate@example.invalid'}},{},self.settings,'123',0)
            self.assertEqual(e.exception.code,'GMAIL_OAUTH_MISSING')

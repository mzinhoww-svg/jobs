import asyncio
import hashlib
import re
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from playwright.async_api import async_playwright, expect

from jobs_service.api import create_app
from jobs_service.config import Settings
from jobs_service.documents import generate_documents
from jobs_service.store import Store


TOKEN='synthetic-ui-token-0123456789abcdef'


class DashboardBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        key=self.root/'api-token';key.write_text(TOKEN);key.chmod(0o600)
        self.store=Store(self.root/'queue.sqlite3')
        self.row,_=self.store.submit('https://example.com/jobs/payments','prepare')
        self.store.claim('fixture')
        output=self.root/'applications'/self.row['id']
        documents=generate_documents({'full_name':'Fictional Candidate','preferred_email':'fixture@example.invalid','location':'São Paulo, Brazil','facts':[{'id':'f1','text':'Structured payments partnerships.','source_kind':'candidate_declaration','confirmation':'confirmed','source':'controlled fixture','date':'2026-10-27'}]}, {'title':'Payments Lead','company':'Fictional Labs','description':'Payments partnerships','language':'en'},output)
        self.pdf=(output/'cv.pdf').read_bytes()
        self.store.finish(self.row['id'],'fixture','DOCUMENTOS_PRONTOS','PREPARE_COMPLETE_NO_UPLOAD',{'job':{'title':'Payments Lead','company':'Fictional Labs','country':'BR'},'documents':documents,'ats':'Greenhouse'})
        app=create_app(Settings(self.root,key,('example.com',),auth_mode=getattr(self,'auth_mode','bearer')))
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0));self.sock.listen()
        self.url='http://127.0.0.1:'+str(self.sock.getsockname()[1])
        self.server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,loop='asyncio'))
        self.thread=threading.Thread(target=self.server.run,kwargs={'sockets':[self.sock]},daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.server.started: break
            await asyncio.sleep(.05)
        if not self.server.started: raise RuntimeError('Fixture HTTP server did not start')
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        self.context=await self.browser.new_context(accept_downloads=True)
        self.page=await self.context.new_page()
        await self.page.goto(self.url)

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.pw.stop()
        self.server.should_exit=True
        await asyncio.to_thread(self.thread.join,5)
        self.sock.close()
        self.tmp.cleanup()

    async def login(self,remember=False,value=TOKEN):
        await self.page.locator('#token').fill(value)
        await self.page.locator('#remember').set_checked(remember)
        await self.page.locator('#login-button').click()
        await expect(self.page.locator('#dashboard')).to_be_visible()
        await expect(self.page.locator('#rows tr')).to_have_count(1)

    async def test_invalid_token_never_saved_valid_token_survives_reload_logout_forgets(self):
        await self.page.locator('#token').fill('wrong-synthetic-token')
        await self.page.locator('#remember').check()
        await self.page.locator('#login-button').click()
        await expect(self.page.locator('#login-error')).to_contain_text('Token inválido')
        self.assertIsNone(await self.page.evaluate("localStorage.getItem('candidaturas.token')"))
        await self.login(True,'  Bearer "'+TOKEN+'"  ')
        self.assertEqual(await self.page.evaluate("localStorage.getItem('candidaturas.token')"),TOKEN)
        await self.page.reload()
        await expect(self.page.locator('#dashboard')).to_be_visible()
        await expect(self.page.locator('#rows tr')).to_have_count(1)
        await self.page.locator('#logout').click()
        await expect(self.page.locator('#login')).to_be_visible()
        self.assertIsNone(await self.page.evaluate("localStorage.getItem('candidaturas.token')"))
        self.assertEqual(await self.page.locator('#rows tr').count(),0)

    async def test_real_history_documents_search_and_safe_external_text(self):
        await self.login()
        await self.page.get_by_role('button',name='Ver detalhes',exact=True).click()
        await expect(self.page.locator('#detail')).to_be_visible()
        await expect(self.page.locator('#detail-body .timeline li')).to_have_count(3)
        async with self.page.expect_download() as download:
            await self.page.get_by_role('button',name='↓ cv.pdf',exact=True).click()
        downloaded=await download.value
        self.assertEqual(hashlib.sha256(Path(await downloaded.path()).read_bytes()).digest(),hashlib.sha256(self.pdf).digest())
        await self.page.locator('#close-detail').click()
        bad,_=self.store.submit('https://example.com/jobs/untrusted','analyze')
        with self.store.db() as c:
            c.execute('UPDATE applications SET payload=? WHERE id=?', ('{"job":{"title":"<img src=x onerror=window.__xss=1>","company":"Untrusted Company"}}',bad['id']))
        await self.page.locator('#refresh').click()
        await expect(self.page.locator('#rows tr')).to_have_count(2)
        self.assertEqual(await self.page.locator('#rows img').count(),0)
        self.assertIsNone(await self.page.evaluate('window.__xss'))
        await self.page.locator('#search').fill('Payments')
        await expect(self.page.locator('#rows tr')).to_have_count(1)
        await expect(self.page.locator('#rows')).to_contain_text('Payments Lead')

    async def test_workday_url_is_queued_and_actual_progress_stays_honest(self):
        await self.login()
        await self.page.locator('#job-url').fill('https://mastercard.wd1.myworkdayjobs.com/jobs/123')
        await self.page.locator('#submit-job').click()
        await expect(self.page.locator('#detail')).to_be_visible()
        self.assertEqual(self.store.count(),2)
        row=next(x for x in self.store.list() if 'myworkdayjobs' in x['url'])
        self.assertEqual(row['mode'],'apply')
        claimed=self.store.claim('fixture')
        self.store.finish(claimed['id'],'fixture','BLOQUEADA','PRIVATE_PROFILE_MISSING')
        await self.page.get_by_role('button',name=re.compile('Atualizar histórico')).click()
        await expect(self.page.locator('#detail-body')).to_contain_text('Bloqueada')
        await expect(self.page.locator('#detail-body')).not_to_contain_text('Enviada com comprovação')

    async def test_mobile_layout_export_has_no_token_or_html_execution(self):
        await self.page.set_viewport_size({'width':390,'height':844})
        await self.login()
        self.assertLessEqual(await self.page.evaluate('document.documentElement.scrollWidth'),390)
        async with self.page.expect_download() as result:
            await self.page.locator('#export').click()
        file=await result.value
        exported=Path(await file.path()).read_text()
        self.assertNotIn(TOKEN,exported)
        self.assertIn('Payments Lead',exported)
        self.assertIn('DOCUMENTOS_PRONTOS',exported)

    async def test_manual_description_and_complete_package_download(self):
        await self.login()
        await self.page.get_by_text('Se o portal bloquear a leitura: informar a descrição da vaga',exact=True).click()
        await self.page.locator('#posting-title').fill('Product Lead')
        await self.page.locator('#posting-company').fill('Fictional Labs')
        await self.page.locator('#posting-description').fill('Lead payment partnerships and coordinate product strategy across business and operations teams.')
        await self.page.locator('#posting-country').select_option('BR')
        await self.page.locator('#job-url').fill('https://custom.example.org/job/abc')
        await self.page.locator('#submit-job').click()
        await expect(self.page.locator('#detail')).to_be_visible()
        row=next(x for x in self.store.list() if 'custom.example.org' in x['url'])
        import json,zipfile
        self.assertEqual(json.loads(row['payload'])['manual_posting']['company'],'Fictional Labs')
        self.assertEqual(await self.page.locator('#posting-description').input_value(),'')
        await self.page.locator('#close-detail').click()
        await self.page.get_by_role('button',name='Ver detalhes').last.click()
        async with self.page.expect_download() as result:
            await self.page.get_by_role('button',name='↓ Baixar pacote CV + carta + análise',exact=True).click()
        download=await result.value
        with zipfile.ZipFile(await download.path()) as z:
            self.assertIn('cv.pdf',z.namelist());self.assertIn('cover-letter.docx',z.namelist())
            self.assertIn('tailoring-report.json',z.namelist())


class OpenAccessBrowserTests(unittest.IsolatedAsyncioTestCase):
    auth_mode='none'
    asyncSetUp=DashboardBrowserTests.asyncSetUp
    asyncTearDown=DashboardBrowserTests.asyncTearDown

    async def test_no_token_opens_dashboard_clears_stored_secret_and_queues(self):
        await expect(self.page.locator('#dashboard')).to_be_visible()
        await expect(self.page.locator('#login')).to_be_hidden()
        await expect(self.page.locator('.sidebar-bottom')).to_contain_text('Acesso público')
        await self.page.evaluate("localStorage.setItem('candidaturas.token','obsolete-synthetic-token')")
        await self.page.reload()
        await expect(self.page.locator('#rows tr')).to_have_count(1)
        self.assertIsNone(await self.page.evaluate("localStorage.getItem('candidaturas.token')"))
        await self.page.locator('#job-url').fill('https://example.com/jobs/no-token')
        await self.page.locator('#mode').select_option('analyze')
        await self.page.locator('#submit-job').click()
        await expect(self.page.locator('#detail')).to_be_visible()
        self.assertEqual(self.store.count(),2)

import hashlib
import tempfile
import unittest
from pathlib import Path
from playwright.async_api import async_playwright
from jobs_service.browser import GreenhouseAdapter, parse_posting
from jobs_service.policy import Blocked

FORM='''<!doctype html><html lang="en"><h1>Payments Lead</h1><h2>Example Industries</h2>
<script type="application/ld+json">{"@type":"JobPosting","title":"Payments Lead","hiringOrganization":{"name":"Example Industries"},"jobLocation":{"address":{"addressCountry":"BR"}},"baseSalary":{"currency":"BRL","value":{"minValue":30000,"maxValue":40000,"unitText":"MONTH"}}}</script>
<p>Develop financial partnerships.</p><form id="application_form">
<label>First Name<input id="first_name" required></label><label>Last Name<input id="last_name" required></label>
<label>Email<input id="email" type="email" required></label>
<label>Resume<input id="resume" type="file" required></label>
<label>Country<select id="country" required><option value="">Choose</option><option value="BR">Brazil</option></select></label>
<label>Employment Type<select id="employment" required onchange="document.querySelector('#conditional').hidden=this.value!=='employee'"><option value="">Choose</option><option value="employee">Employee</option></select></label>
<div id="conditional" hidden><label>Notice period<input id="notice" required></label></div>
<button type="submit">Submit application</button></form><script>
document.querySelector('form').onsubmit=e=>{e.preventDefault();window.submitted=true;document.querySelector('form').remove();document.body.insertAdjacentHTML('beforeend','<section id="application_confirmation">Thank you for applying. Your application has been received. Requisition 123</section>');};
</script></html>'''


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.file=Path(self.tmp.name)/'cv.pdf'
        self.file.write_bytes(b'%PDF-1.4\ncontrolled document real bytes\n%%EOF')
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        self.page=await self.browser.new_page()
        await self.page.route('https://job-boards.greenhouse.io/**',lambda route:route.fulfill(status=200,body='<html></html>'))
        await self.page.goto('https://job-boards.greenhouse.io/example/jobs/123')
        self.adapter=GreenhouseAdapter(self.page,'greenhouse:example:123')

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()
        self.tmp.cleanup()

    async def test_real_file_bytes_conditional_select_and_confirmation(self):
        await self.page.set_content(FORM)
        info=await parse_posting(self.page)
        self.assertEqual(info['country'],'BR')
        self.assertEqual(info['salary']['min'],30000)
        answer={'First Name':'Fictional','Last Name':'Candidate','Email':'candidate@example.invalid','Country':'Brazil','Employment Type':'Employee','Notice period':'30 days'}
        await self.adapter.fill(answer,{'Resume':self.file})
        self.assertEqual(await self.page.locator('#notice').input_value(),'30 days')
        uploaded=await self.page.locator('#resume').evaluate('async e=>Array.from(new Uint8Array(await e.files[0].arrayBuffer()))')
        self.assertEqual(bytes(uploaded),self.file.read_bytes())
        intents=[]
        proof=await self.adapter.submit(lambda:intents.append('committed'))
        self.assertEqual(intents,['committed'])
        self.assertEqual(proof['identity'],'greenhouse:example:123')
        self.assertEqual(len(proof['confirmation_hash']),64)

    async def test_unknown_required_and_reset_are_blocked(self):
        await self.page.set_content('<form><label>Unknown legal declaration<input required></label></form>')
        with self.assertRaises(Blocked): await self.adapter.fill({}, {})
        await self.page.set_content('<form><label>Name<input id="x" required onblur="this.value=\'\'"></label></form>')
        with self.assertRaises(Blocked): await self.adapter.fill({'Name':'Fictional'}, {})

    async def test_captcha_and_empty_file_not_bypassed(self):
        await self.page.set_content('<form><div class="g-recaptcha"></div></form>')
        with self.assertRaises(Blocked) as error: await self.adapter.fill({}, {})
        self.assertEqual(error.exception.code,'CAPTCHA_REQUIRES_HUMAN')
        await self.page.set_content('<form><label>Resume<input type="file" required></label></form>')
        self.file.write_bytes(b'')
        with self.assertRaises(Blocked): await self.adapter.fill({}, {'Resume':self.file})

    async def test_preexisting_thank_you_not_proof_and_timeout_uncertain(self):
        await self.page.set_content('<p>Thank you for applying. Your application has been received. Requisition 123</p><form onsubmit="event.preventDefault()"><button>Submit application</button></form>')
        proof=await self.adapter.submit(lambda:None,timeout=150)
        self.assertIsNone(proof)

    async def test_unrelated_dom_change_and_wrong_requisition_are_not_proof(self):
        await self.page.set_content('''<p>Your application has been received. Requisition 999</p><form onsubmit="event.preventDefault();document.body.append('Please correct error')"><button>Submit application</button></form>''')
        self.assertIsNone(await self.adapter.submit(lambda:None,timeout=150))
        await self.page.set_content('''<form id="application_form" onsubmit="event.preventDefault();this.remove();document.body.append('Your application has been received. Requisition 999')"><button>Submit application</button></form>''')
        self.assertIsNone(await self.adapter.submit(lambda:None,timeout=150))

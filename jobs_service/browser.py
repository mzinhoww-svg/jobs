"""Narrow Greenhouse form adapter, tested on controlled forms only."""
import asyncio
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout
from .policy import Blocked, public_url, detect_ats


async def parse_posting(page):
    objects=[]
    for raw in await page.locator('script[type="application/ld+json"]').all_text_contents():
        try:
            obj=json.loads(raw)
        except (ValueError,TypeError): continue
        objects.extend(obj if isinstance(obj,list) else obj.get('@graph',[obj]))
    posting=next((x for x in objects if x.get('@type')=='JobPosting'),{})
    title=posting.get('title') or (await page.locator('h1').first.inner_text() if await page.locator('h1').count() else '')
    org=posting.get('hiringOrganization',{})
    location=posting.get('jobLocation',{})
    if isinstance(location,list): location=location[0] if len(location)==1 else {}
    country=location.get('address',{}).get('addressCountry')
    if isinstance(country,dict): country=country.get('name')
    country={'Brazil':'BR','Brasil':'BR','United States':'US','USA':'US'}.get(country,country)
    base=posting.get('baseSalary',{})
    value=base.get('value',{}) if isinstance(base,dict) else {}
    salary={}
    if value.get('minValue') and value.get('maxValue'):
        salary={'min':value['minValue'],'max':value['maxValue'],'currency':base.get('currency'),
                'period':{'MONTH':'monthly','YEAR':'annual'}.get(value.get('unitText')),
                'kind':'base','official':True,'sources':[{'url':page.url,'date':date.today().isoformat(),'type':'official_job_posting'}],
                'rationale':'Published base range for this exact position; compare employment regime before answering.'}
    return {'title':title,'company':org.get('name',''),'country':country,
            'language':(await page.locator('html').get_attribute('lang') or 'en').split('-')[0],
            'description':posting.get('description') or (await page.locator('body').inner_text())[:60000],
            'salary':salary,'canonical_url':page.url}


def normalized(label):
    return re.sub(r'\s+',' ',label.replace('*','')).strip().casefold()


FIELD_METADATA = '''e=>{
    const label=e.labels?.[0]?.cloneNode(true);
    label?.querySelectorAll('input,select,textarea,button').forEach(x=>x.remove());
    return {label:label?.textContent||e.getAttribute('aria-label')||e.name||e.id,
            tag:e.tagName,type:e.type,required:e.required||e.getAttribute('aria-required')==='true',id:e.id||e.name};
}'''


class GreenhouseAdapter:
    def __init__(self,page,identity):
        self.page=page
        self.identity=identity

    async def captcha(self):
        if await self.page.locator('.g-recaptcha, .h-captcha, iframe[src*="recaptcha"], iframe[src*="hcaptcha"], [data-sitekey]').count():
            raise Blocked('CAPTCHA_REQUIRES_HUMAN')

    async def form(self):
        forms=self.page.locator('#application_form, #application-form, form[id*="application"]')
        if await forms.count(): return forms.first
        forms=self.page.locator('form')
        if await forms.count()!=1: raise Blocked('APPLICATION_FORM_NOT_IDENTIFIED')
        return forms.first

    async def fields(self):
        form=await self.form()
        return form.locator('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')

    async def fill(self,answers,files):
        await self.captcha()
        answers={normalized(k):v for k,v in answers.items()}
        files={normalized(k):Path(v) for k,v in files.items()}
        checked={}
        # Re-scan after each pass because selecting an option may reveal new fields.
        for _ in range(5):
            changed=False
            fields=await self.fields()
            for i in range(await fields.count()):
                loc=fields.nth(i)
                if not await loc.is_visible() or not await loc.is_enabled(): continue
                meta=await loc.evaluate(FIELD_METADATA)
                key=normalized(meta['label'])
                if key in checked: continue
                value=answers.get(key)
                if meta['type']=='file':
                    path=files.get(key)
                    if path is None: continue
                    if not path.is_file() or not 0<path.stat().st_size<=5*1024*1024:
                        raise Blocked('ATTACHMENT_EMPTY_OR_TOO_LARGE')
                    await loc.set_input_files(str(path.resolve()))
                    actual=await loc.evaluate('async e=>Array.from(new Uint8Array(await e.files[0].arrayBuffer()))')
                    if hashlib.sha256(bytes(actual)).digest()!=hashlib.sha256(path.read_bytes()).digest():
                        raise Blocked('ATTACHMENT_BYTES_MISMATCH')
                    checked[key]=('file',hashlib.sha256(path.read_bytes()).hexdigest())
                elif value is not None:
                    if meta['type'] in ('checkbox','radio'):
                        if type(value) is not bool: raise Blocked('BOOLEAN_ANSWER_REQUIRED')
                        await loc.set_checked(value)
                        checked[key]=('checked',value)
                    elif meta['tag']=='SELECT':
                        await loc.select_option(label=str(value))
                        checked[key]=('select',str(value))
                    elif await loc.get_attribute('role')=='combobox':
                        await loc.click()
                        option=self.page.get_by_role('option',name=str(value),exact=True)
                        if await option.count()!=1: raise Blocked('SELECT_OPTION_AMBIGUOUS')
                        await option.click()
                        checked[key]=('value',str(value))
                    else:
                        await loc.fill(str(value))
                        await loc.blur()
                        checked[key]=('value',str(value))
                else: continue
                changed=True
            if not changed: break
        # Yield two animation frames, then read final values after all conditional updates.
        await self.page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
        fields=await self.fields()
        for i in range(await fields.count()):
            loc=fields.nth(i)
            if not await loc.is_visible() or not await loc.is_enabled(): continue
            meta=await loc.evaluate(FIELD_METADATA)
            key=normalized(meta['label'])
            expected=checked.get(key)
            if expected:
                kind,value=expected
                if kind=='checked': actual=await loc.is_checked()
                elif kind=='select': actual=await loc.locator('option:checked').inner_text()
                elif kind=='file':
                    b=await loc.evaluate('async e=>e.files.length?Array.from(new Uint8Array(await e.files[0].arrayBuffer())):[]')
                    actual=hashlib.sha256(bytes(b)).hexdigest()
                else: actual=await loc.input_value()
                if actual!=value: raise Blocked('FORM_VALUE_NOT_PERSISTED')
            elif meta['required']:
                # Do not trust prefilled author defaults, browser autofill or an arbitrary first option.
                raise Blocked('REQUIRED_ANSWER_UNKNOWN')
        await self.captcha()

    async def submit(self,before_click,timeout=10000):
        await self.captcha()
        if detect_ats(self.page.url,[])[1]!=self.identity:
            raise Blocked('REQUISITION_CONTEXT_MISMATCH')
        selector='#application_confirmation, .application-confirmation, [role=status], [role=alert], h1, h2, h3, p, section, div'
        before=set(await self.page.locator(selector).all_text_contents())
        form=await self.form()
        button=form.get_by_role('button',name=re.compile(r'^(submit application|submit|enviar candidatura|enviar inscrição)$',re.I))
        if await button.count()!=1: raise Blocked('SUBMIT_BUTTON_AMBIGUOUS')
        before_click()  # Durable intent first; even a failed click is uncertain.
        try:
            await button.click(timeout=timeout)
        except BrowserTimeout:
            return None
        deadline=asyncio.get_running_loop().time()+timeout/1000
        requisition=self.identity.split(':')[-1]
        exact_id=re.compile(r'(?<![A-Za-z0-9_-])'+re.escape(requisition)+r'(?![A-Za-z0-9_-])')
        explicit=re.compile(r'(?:application (?:has been |was )?(?:received|submitted)|candidatura (?:foi )?recebida)',re.I)
        while asyncio.get_running_loop().time()<deadline:
            # A retained form or old testimonial can never be proof. Require a
            # new confirmation with the exact requisition observed in the URL.
            if not await form.is_visible():
                for text in await self.page.locator(selector).all_text_contents():
                    if text not in before and explicit.search(text) and exact_id.search(text):
                        return {'identity':self.identity,'confirmation_hash':hashlib.sha256(text.encode()).hexdigest(),
                                'type':'new_explicit_portal_confirmation','at':__import__('time').time()}
            await asyncio.sleep(.05)
        return None


class BrowserSession:
    def __init__(self,settings): self.settings=settings

    async def __aenter__(self):
        self.pw=await async_playwright().start()
        proxy=os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        kwargs={'executable_path':self.settings.chromium,'headless':True}
        if proxy: kwargs['proxy']={'server':proxy,'bypass':'<-loopback>'}
        self.browser=await self.pw.chromium.launch(**kwargs)
        state=self.settings.data_dir/'browser-state.json'
        context_args={'service_workers':'block','accept_downloads':False}
        if state.exists():
            if state.stat().st_mode & 0o077: raise Blocked('BROWSER_SESSION_PERMISSIONS')
            context_args['storage_state']=str(state)
        self.context=await self.browser.new_context(**context_args)
        async def guarded(route):
            try:
                public_url(route.request.url,self.settings.allowed_hosts,resolve=not bool(proxy))
            except (ValueError,OSError):
                await route.abort('blockedbyclient')
            else:
                # Do not let Chromium follow an uninspected redirect, including
                # POST redirects. Resolve initial URL redirects before browsing.
                try:
                    response=await route.fetch(max_redirects=0,timeout=20000)
                    if 300<=response.status<400:
                        await route.abort('blockedbyclient')
                    else: await route.fulfill(response=response)
                except Exception:
                    await route.abort('failed')
        await self.context.route('**/*',guarded)
        # Block WebSocket channels; they are not needed by the initial adapter.
        await self.context.route_web_socket('**/*',lambda ws:ws.close())
        self.page=await self.context.new_page()
        self.page.set_default_timeout(12000)
        return self

    async def __aexit__(self,*exc):
        state=self.settings.data_dir/'browser-state.json'
        await self.context.storage_state(path=str(state))
        state.chmod(0o600)
        await self.context.close()
        await self.browser.close()
        await self.pw.stop()

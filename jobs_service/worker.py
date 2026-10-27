"""Single-profile remote worker. No email outreach, CAPTCHA bypass or blind retry."""
import asyncio
import fcntl
import json
import os
import re
import signal
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin
import httpx
from playwright.async_api import Error as BrowserError
from .browser import BrowserSession, GreenhouseAdapter, parse_posting
from .config import Settings
from .documents import generate_documents
from .gmail import Gmail
from .policy import Blocked, detect_ats, choose_salary, profile_view, public_url, verified_fact
from .store import Store


async def resolve_redirects(url,settings):
    proxy=bool(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'))
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        for _ in range(8):
            public_url(url,settings.allowed_hosts,resolve=not proxy)
            r=await client.get(url,headers={'User-Agent':'PrivateJobsService/0.1'})
            if r.status_code in (404,410): raise Blocked('VAGA_ENCERRADA')
            if r.status_code in (301,302,303,307,308):
                url=urljoin(url,r.headers.get('location',''))
            elif r.status_code>=400: raise Blocked('PORTAL_ACCESS_UNAVAILABLE')
            else: return url
        raise Blocked('REDIRECT_LIMIT')


def answers_for(profile,view,job,context,salary):
    name=view['full_name'].split()
    answers={'First Name':name[0],'Last Name':' '.join(name[1:]),'Email':view['preferred_email'],
             'Phone':view.get('phone'),'LinkedIn Profile':view.get('linkedin')}
    # Only exact question labels from private traceable per-job answers.
    # Generic yes/no/legal/consent decisions have no fallback.
    for label,fact in context.get('answers',{}).items():
        if verified_fact(fact):
            answers[label]=fact.get('value')
    salary_field=context.get('salary_field')
    if salary_field:
        if (not salary or salary_field.get('kind')!='base'
            or salary_field.get('currency')!=salary['currency']
            or salary_field.get('period')!=salary['period']):
            raise Blocked('SALARY_FIELD_UNIT_UNVERIFIED')
        answers[salary_field['label']]=str(salary['chosen'])
    return {k:v for k,v in answers.items() if v is not None}


async def verification_answers(page,profile,context,settings,requisition,started):
    field=page.get_by_label(re.compile(r'^(verification code|email verification code|código de verificação)\s*\*?$',re.I))
    if await field.count()==0: return {}
    credentials=settings.data_dir/'gmail-oauth.json'
    if not credentials.exists(): raise Blocked('GMAIL_OAUTH_MISSING')
    domains=set(context.get('email_verification',{}).get('allowed_sender_domains',[]))
    if not domains: raise Blocked('GMAIL_SENDER_CONTEXT_REQUIRED')
    gmail=Gmail(credentials,profile['identity']['preferred_email'])
    try:
        code=await asyncio.to_thread(gmail.verification_code,domains,requisition,started)
    finally:
        gmail.client.close()
    label=await field.evaluate('e=>e.labels?.[0]?.textContent||e.getAttribute("aria-label")')
    return {label:code}


async def process(row,store,settings,session_factory=BrowserSession):
    id,owner=row['id'],row['owner']
    async def keep_alive():
        while True:
            await asyncio.sleep(30)
            store.heartbeat(id,owner)
            (settings.data_dir/'worker-heartbeat').write_text(str(time.time()))
    heartbeat=asyncio.create_task(keep_alive())
    try:
        profile_path=settings.data_dir/'profile.json'
        if not profile_path.exists(): raise Blocked('PRIVATE_PROFILE_MISSING')
        profile=json.loads(profile_path.read_text())
        context_path=settings.data_dir/'contexts'/(id+'.json')
        context=json.loads(context_path.read_text()) if context_path.exists() else {}
        async with session_factory(settings) as session:
            # A fixture session does not make network requests; real sessions
            # resolve redirects through a separate read-only, validated client.
            url=await resolve_redirects(row['url'],settings) if session_factory is BrowserSession else row['url']
            response=await session.page.goto(url,wait_until='domcontentloaded',timeout=30000)
            if response and response.status in (404,410): raise Blocked('VAGA_ENCERRADA')
            frames=[f.url for f in session.page.frames if f!=session.page.main_frame]
            ats,identity=detect_ats(session.page.url,frames)
            if not identity: raise Blocked('ATS_ADAPTER_NOT_IMPLEMENTED')
            if not store.identify(id,identity): return
            job=await parse_posting(session.page)
            frame=next((f for f in session.page.frames if detect_ats(f.url,[])[1]==identity),session.page)
            if not job.get('country') and frame!=session.page:
                framed=await parse_posting(frame)
                if framed.get('country'): job=framed
            # Private, traceable observations can supplement missing metadata.
            for key in ('country','company','language'):
                fact=context.get(key,{})
                if not job.get(key) and verified_fact(fact):
                    job[key]=fact['value']
            store.checkpoint(id,owner,'EM_ANALISE',{'job':job,'ats':ats,'identity':identity})
            if row['mode']=='analyze':
                store.finish(id,owner,'EM_ANALISE','ANALYSIS_COMPLETE')
                return
            if not job.get('title') or not job.get('company'): raise Blocked('JOB_METADATA_INCOMPLETE')
            view=profile_view(profile,job.get('country'))
            if not view['facts']: raise Blocked('CONFIRMED_CAREER_FACTS_REQUIRED')
            output=settings.data_dir/'applications'/id
            output.mkdir(parents=True,exist_ok=True,mode=0o700)
            salary=None
            research=context.get('salary_research') or job.get('salary')
            if research:
                floors={currency:values.get('annual',values.get('monthly',0)*12)
                        for currency,values in profile['compensation']['salary_base_floors'].items()}
                # Fit is based on overlap with confirmed evidence, not a fabricated ATS score.
                description=job.get('description','').lower()
                evidence=' '.join(f['text'] for f in view['facts']).lower()
                concepts=('payment','partner','product','financial','loyalty')
                required=[c for c in concepts if c in description]
                fit=sum(c in evidence for c in required)/len(required) if required else .5
                salary=choose_salary(research,floors,fit)
                (output/'salary_research.json').write_text(json.dumps(salary,ensure_ascii=False,indent=2))
            else:
                (output/'salary_research.json').write_text(json.dumps({'status':'MISSING','reason':'NO_VERIFIED_PUBLISHED_RANGE_OR_COMPANY_COMPARABLES'}))
            docs=generate_documents(view,job,output)
            store.checkpoint(id,owner,'DOCUMENTOS_PRONTOS',{'documents':docs,'salary':salary})
            if row['mode']=='prepare':
                store.finish(id,owner,'DOCUMENTOS_PRONTOS','PREPARE_COMPLETE_NO_UPLOAD')
                return
            adapter=GreenhouseAdapter(frame,identity)
            await adapter.captcha()
            form_text=(await (await adapter.form()).inner_text()).lower()
            if any(x in form_text for x in ('salary','remuneração','pretensão')) and not context.get('salary_field'):
                raise Blocked('SALARY_FIELD_MAPPING_REQUIRED')
            if not salary: raise Blocked('SALARY_RESEARCH_REQUIRED')
            answers=answers_for(profile,view,job,context,salary)
            answers.update(await verification_answers(frame,profile,context,settings,identity.split(':')[-1],row['updated']))
            store.checkpoint(id,owner,'EM_PREENCHIMENTO')
            files={'Resume':output/'cv.pdf','Resume/CV':output/'cv.pdf','Currículo':output/'cv.pdf',
                   'Cover Letter':output/'cover-letter.pdf'}
            await adapter.fill(answers,files)
            proof=await adapter.submit(lambda:store.submit_intent(id,owner))
            if proof:
                store.finish(id,owner,'ENVIADA_COMPROVADA',None,{'proof':proof})
            else:
                store.finish(id,owner,'ENVIO_INCERTO','PORTAL_CONFIRMATION_NOT_OBSERVED')
    except Blocked as e:
        current=store.get(id)
        if current['intent']:
            state='ENVIO_INCERTO'
        elif e.code in ('VAGA_ENCERRADA','INCOMPATIVEL_REMUNERACAO','INCOMPATIVEL_REQUISITO'):
            state=e.code
        elif e.code.startswith('GMAIL_'):
            state='AGUARDANDO_VERIFICACAO'
        else: state='BLOQUEADA'
        store.finish(id,owner,state,e.code)
    except (httpx.TransportError,BrowserError):
        store.retry(id,owner)
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError):
        # No upstream text or PII in logs, API reasons or error events.
        store.finish(id,owner,'ENVIO_INCERTO' if store.get(id)['intent'] else 'BLOQUEADA','CONFIGURATION_OR_DATA_INVALID')
    finally:
        heartbeat.cancel()
        try: await heartbeat
        except asyncio.CancelledError: pass


async def run():
    settings=Settings.from_env()
    settings.validate()
    store=Store(settings.data_dir/'queue.sqlite3')
    owner=uuid.uuid4().hex
    stop=asyncio.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig,stop.set)
    # Process lock is stronger than the lease: an old browser cannot coexist
    # with a replacement worker just because a heartbeat was delayed.
    with (settings.data_dir/'worker.lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('ONE_WORKER_PER_PROFILE') from None
        while not stop.is_set():
            (settings.data_dir/'worker-heartbeat').write_text(str(time.time()))
            row=store.claim(owner)
            if row: await process(row,store,settings)
            else:
                try: await asyncio.wait_for(stop.wait(),timeout=2)
                except TimeoutError: pass


if __name__=='__main__': asyncio.run(run())

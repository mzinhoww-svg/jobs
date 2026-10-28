import secrets
import json
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field
from .config import Settings
from .policy import public_url, verified_fact
from .store import Store, STATES
from .presentation import summary, result_view

WEB_ROOT=Path(__file__).with_name('web')


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=4096)
    mode: Literal['apply', 'analyze', 'prepare']


def create_app(settings):
    token=settings.validate()
    store=Store(settings.data_dir/'queue.sqlite3')
    app=FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authenticated(authorization: str = Header(default='')):
        if settings.auth_mode=='none': return
        parts=authorization.strip().split(None,1)
        presented=parts[1].strip() if len(parts)==2 and parts[0].lower()=='bearer' else ''
        if not secrets.compare_digest(presented.encode(),token.encode()):
            raise HTTPException(401,'AUTHENTICATION_REQUIRED',headers={'WWW-Authenticate':'Bearer'})

    @app.middleware('http')
    async def headers(request, call_next):
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.get('/auth/config')
    def auth_config():
        return {'required':settings.auth_mode!='none'}

    @app.get('/healthz')
    def health():
        store.list()  # Fails when persistence is inaccessible.
        return {'status':'ok'}

    @app.get('/', response_class=HTMLResponse)
    def ui():
        return HTMLResponse((WEB_ROOT/'index.html').read_text())

    @app.get('/ui.js')
    def js():
        return FileResponse(WEB_ROOT/'ui.js',media_type='application/javascript')

    @app.get('/ui.css')
    def css():
        return FileResponse(WEB_ROOT/'ui.css',media_type='text/css')

    def public(row):
        return summary(row)

    @app.get('/system/status',dependencies=[Depends(authenticated)])
    def system_status():
        age=None
        try:
            age=time.time()-float((settings.data_dir/'worker-heartbeat').read_text())
            if age<0: age=None
        except (OSError,ValueError): pass
        facts=0
        configured=False
        try:
            profile=json.loads((settings.data_dir/'profile.json').read_text())
            facts=sum(verified_fact(f) for f in profile.get('facts',[]) if isinstance(f,dict))
            configured=bool(profile.get('identity',{}).get('full_name') and profile.get('identity',{}).get('preferred_email') and facts)
        except (OSError,ValueError,TypeError,AttributeError): pass
        return {'version':'0.2.0','authentication_required':settings.auth_mode!='none',
                'worker':{'state':'unknown' if age is None else ('ready' if age<90 else 'stale'),'heartbeat_age_seconds':round(age,1) if age is not None else None},
                'profile':{'configured':configured,'confirmed_facts':facts},'counts':store.counts(),
                'capabilities':{'greenhouse':'controlled_tests','workday':False,'appllama':False}}

    @app.post('/applications',dependencies=[Depends(authenticated)])
    def submit(body: Submission):
        try:
            # Admission does not fetch. DNS resolution belongs to the egress
            # boundary; managed proxies resolve destination DNS themselves.
            url=public_url(body.url,settings.allowed_hosts,resolve=False)
        except (ValueError,OSError):
            raise HTTPException(422,'URL_NOT_APPROVED') from None
        row,duplicate=store.submit(url,body.mode)
        return JSONResponse({**public(row),'duplicate':duplicate},status_code=200 if duplicate else 201)

    @app.get('/applications',dependencies=[Depends(authenticated)])
    def listing(limit:int=Query(default=200,ge=1,le=200),offset:int=Query(default=0,ge=0),q:str=Query(default='',max_length=200),state:str=Query(default='')):
        if state and state not in STATES: raise HTTPException(422,'INVALID_STATE')
        return JSONResponse([public(x) for x in store.list(limit,offset,q,state or None)],headers={'X-Total-Count':str(store.count(q,state or None))})

    @app.get('/applications/{id}',dependencies=[Depends(authenticated)])
    def status(id: str):
        row=store.get(id)
        if not row: raise HTTPException(404,'NOT_FOUND')
        return {**public(row),'history':store.history(id),'result':result_view(row)}

    @app.get('/applications/{id}/documents/{name}',dependencies=[Depends(authenticated)])
    def document(id: str, name: Literal['cv.pdf','cv.docx','cover-letter.pdf','cover-letter.docx']):
        from fastapi.responses import FileResponse
        if not store.get(id): raise HTTPException(404,'NOT_FOUND')
        root=(settings.data_dir/'applications').resolve()
        path=(root/id/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404,'NOT_FOUND')
        return FileResponse(path,filename=name)

    @app.post('/applications/{id}/resume',dependencies=[Depends(authenticated)])
    def resume(id: str):
        try: store.resume(id)
        except ValueError: raise HTTPException(409,'RESUME_NOT_ALLOWED') from None
        return public(store.get(id))
    return app


def factory(): return create_app(Settings.from_env())

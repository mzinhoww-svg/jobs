import secrets
import json
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .config import Settings
from .policy import public_url
from .store import Store


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=4096)
    mode: Literal['apply', 'analyze', 'prepare']


def create_app(settings):
    token=settings.validate()
    store=Store(settings.data_dir/'queue.sqlite3')
    app=FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authenticated(authorization: str = Header(default='')):
        if not secrets.compare_digest(authorization.encode(), ('Bearer '+token).encode()):
            raise HTTPException(401,'AUTHENTICATION_REQUIRED',headers={'WWW-Authenticate':'Bearer'})

    @app.middleware('http')
    async def headers(request, call_next):
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.get('/healthz')
    def health():
        store.list()  # Fails when persistence is inaccessible.
        return {'status':'ok'}

    @app.get('/', response_class=HTMLResponse)
    def ui():
        return '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Candidaturas privadas</title>
<h1>Candidaturas privadas</h1><p>Entrada autenticada. Enviar autoriza a candidatura; preparar e analisar não fazem upload.</p>
<label>Token <input id="token" type="password" autocomplete="off"></label>
<form id="form"><label>URL da vaga <input id="url" type="url" required></label>
<select id="mode"><option value="apply">Candidatar</option><option value="prepare">Preparar</option><option value="analyze">Analisar</option></select>
<button>Adicionar à fila</button></form><button id="refresh">Atualizar estados</button><pre id="result"></pre><script src="/ui.js"></script></html>'''

    @app.get('/ui.js')
    def js():
        from fastapi.responses import Response
        return Response('''const el=id=>document.getElementById(id);
async function request(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+el('token').value,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});el('result').textContent=JSON.stringify(await r.json(),null,2);}
el('form').addEventListener('submit',e=>{e.preventDefault();request('/applications',{url:el('url').value,mode:el('mode').value});});
el('refresh').addEventListener('click',()=>request('/applications'));''',media_type='application/javascript')

    def public(row):
        return {k:row[k] for k in ('id','status','reason','mode','created','updated','attempts')}

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
    def listing(): return [public(x) for x in store.list()]

    @app.get('/applications/{id}',dependencies=[Depends(authenticated)])
    def status(id: str):
        row=store.get(id)
        if not row: raise HTTPException(404,'NOT_FOUND')
        data=json.loads(row['payload'])
        job=data.get('job',{})
        result={'job':{k:job[k] for k in ('title','company','country','language') if k in job},
                'ats':data.get('ats'),'documents':data.get('documents',{}),
                'proof':data.get('proof')}
        salary=data.get('salary') or {}
        result['salary']={k:salary[k] for k in ('chosen','currency','period','kind','sources','rationale') if k in salary}
        return {**public(row),'history':store.history(id),'result':result}

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

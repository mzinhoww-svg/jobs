import json
import unittest
import httpx
from jobs_service.intelligence import analyze_posting, extract_url
from jobs_service.policy import Blocked

SOURCE='Payments Lead\nFictional Labs\nLead payment partnerships and product strategy. Coordinate operations.'
FACTS=[{'id':'f1','text':'Structured payment partnerships.','source':'fixture','date':'2026-10-27','source_kind':'candidate_declaration','confirmation':'confirmed'}]

class IntelligenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_tavily_extracts_url_without_local_destination_fetch(self):
        calls=[]
        def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url),'https://api.tavily.com/extract')
            self.assertEqual(json.loads(request.content)['urls'],['https://careers.example.org/role'])
            return httpx.Response(200,json={'results':[{'url':'https://careers.example.org/role','raw_content':SOURCE}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await extract_url('https://careers.example.org/role','synthetic-key',client)
        self.assertEqual(result,SOURCE);self.assertEqual(len(calls),1)

    async def test_model_selects_only_existing_verified_facts_and_source_quotes(self):
        def handler(request):
            self.assertEqual(str(request.url),'https://openrouter.ai/api/v1/chat/completions')
            body=json.loads(request.content)
            self.assertEqual(body['model'],'deepseek/deepseek-v4.1-flash')
            result={'job':{'title':'Payments Lead','company':'Fictional Labs','country':None,'language':'en'},'ranked_fact_ids':['f1'],'matches':[{'fact_id':'f1','requirement':'Lead payment partnerships and product strategy.'}]}
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await analyze_posting(SOURCE,FACTS,'synthetic-key',client=client)
        self.assertEqual(result['ranked_fact_ids'],['f1'])
        self.assertEqual(result['job']['description'],SOURCE)

    async def test_model_cannot_invent_evidence_or_requirement_quotes(self):
        def handler(request):
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'job':{'title':'Payments Lead','company':'Fictional Labs','language':'en'},'ranked_fact_ids':['invented'],'matches':[{'fact_id':'invented','requirement':'Must be a certified astronaut'}]})}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(Blocked) as caught:
                await analyze_posting(SOURCE,FACTS,'synthetic-key',client=client)
        self.assertEqual(caught.exception.code,'AI_EVIDENCE_INVALID')

    async def test_private_url_never_reaches_extraction_provider(self):
        def handler(request): raise AssertionError('Private URL must not reach provider')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError): await extract_url('https://127.0.0.1/x','synthetic-key',client)

    async def test_public_reader_pins_ip_and_tls_name_before_fetch(self):
        from jobs_service.reader import public_fetch
        def handler(request):
            self.assertEqual(request.url.host,'93.184.216.34')
            self.assertEqual(request.headers['host'],'example.org')
            self.assertEqual(request.extensions['sni_hostname'],'example.org')
            return httpx.Response(200,text='Public job posting')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            status,_,body=await public_fetch('https://example.org/jobs/1',client,['93.184.216.34'])
            self.assertEqual(status,200);self.assertIn(b'posting',body)
            with self.assertRaises(Blocked): await public_fetch('https://example.org/jobs/1',client,['127.0.0.1'])

    async def test_gateway_uses_same_evidence_validation(self):
        def handler(request):
            self.assertEqual(str(request.url),'https://ai-gateway.vercel.sh/v1/chat/completions')
            body=json.loads(request.content)
            self.assertNotIn('preferred_email',body['messages'][1]['content'])
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'job':{'title':'Payments Lead','company':'Fictional Labs','language':'en'},'ranked_fact_ids':['f1'],'matches':[]})}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await analyze_posting(SOURCE,FACTS,'synthetic-key',provider='gateway',client=client)
        self.assertEqual(result['provider'],'gateway')

    async def test_actual_chromium_reader_keeps_readable_job_despite_form_captcha(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock,patch
        from jobs_service.reader import read_posting
        from jobs_service.config import Settings
        html=b'<html lang="en"><h1>Payments Lead</h1><script type="application/ld+json">{"@type":"JobPosting","title":"Payments Lead","description":"Lead payment partnerships and product strategy.","hiringOrganization":{"name":"Fictional Labs"},"jobLocation":{"address":{"addressCountry":"BR"}}}</script><p>Lead payment partnerships and product strategy.</p><form><div class="g-recaptcha"></div></form></html>'
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(Path(tmp),Path(tmp)/'unused',())
            with patch('jobs_service.reader.public_fetch',new=AsyncMock(return_value=(200,{'content-type':'text/html'},html))):
                job,text=await read_posting('https://careers.example.org/job',settings)
        self.assertEqual(job['company'],'Fictional Labs')
        self.assertIn('Payments Lead',text)

    def test_private_config_reports_status_without_returning_credential(self):
        import tempfile
        from pathlib import Path
        from jobs_service.intelligence import ai_config,ai_enabled,public_ai_status
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ai-config.json';p.write_text(json.dumps({'provider':'openrouter','api_key':'synthetic-private-key','enabled':True}));p.chmod(0o600)
            self.assertTrue(ai_enabled(tmp))
            self.assertEqual(ai_config(tmp)[0],'openrouter')
            self.assertNotIn('synthetic-private-key',json.dumps(public_ai_status(tmp)))
            p.chmod(0o644)
            self.assertFalse(public_ai_status(tmp)['enabled'])

    async def test_malformed_jsonld_is_ignored_without_crashing_reader(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import AsyncMock,patch
        from jobs_service.reader import read_posting
        from jobs_service.config import Settings
        html=b'<html lang="en"><h1>Payments Lead</h1><script type="application/ld+json">"hello"</script><script type="application/ld+json">{"@graph":[null,42,"x",{"@type":"JobPosting","title":"Payments Lead","hiringOrganization":"bad","jobLocation":"bad","baseSalary":{"value":"bad"}}]}</script><p>Lead payment partnerships and product strategy.</p></html>'
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(Path(tmp),Path(tmp)/'unused',())
            with patch('jobs_service.reader.public_fetch',new=AsyncMock(return_value=(200,{'content-type':'text/html'},html))):
                job,_=await read_posting('https://careers.example.org/job',settings)
        self.assertEqual(job['title'],'Payments Lead')
        self.assertEqual(job['company'],'')
        self.assertIsNone(job['country'])
        self.assertEqual(job['salary'],{})

    async def test_real_tls_verifies_original_hostname_and_does_not_follow_private_redirect(self):
        import asyncio,ssl,subprocess,tempfile,threading
        from pathlib import Path
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from jobs_service.reader import public_fetch
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers['Host'])
                self.send_response(302 if self.path=='/redirect' else 200)
                if self.path=='/redirect': self.send_header('Location','https://127.0.0.1/private')
                self.end_headers();self.wfile.write(b'Public fixture')
            def log_message(self,*args): pass
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cert=root/'cert.pem';key=root/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=careers.example.org','-addext','subjectAltName=DNS:careers.example.org'],check=True,capture_output=True)
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key)
            server.socket=ctx.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                transport=httpx.AsyncHTTPTransport(verify=ssl.create_default_context(cafile=str(cert)),trust_env=False)
                original=transport._pool._network_backend
                destinations=[]
                class FixtureBackend:
                    async def connect_tcp(self,host,port,**kwargs):
                        destinations.append(host)
                        assert host=='93.184.216.34', 'Destination must already be a validated public IP'
                        return await original.connect_tcp('127.0.0.1',server.server_port,**kwargs)
                    async def sleep(self,seconds): await asyncio.sleep(seconds)
                transport._pool._network_backend=FixtureBackend()
                async with httpx.AsyncClient(transport=transport,trust_env=False,timeout=5) as client:
                    status,_,body=await public_fetch('https://careers.example.org/job',client,['93.184.216.34'])
                    self.assertEqual(status,200);self.assertIn(b'fixture',body)
                    with self.assertRaises(httpx.ConnectError):
                        await public_fetch('https://wrong.example.org/job',client,['93.184.216.34'])
                    status,headers,_=await public_fetch('https://careers.example.org/redirect',client,['93.184.216.34'])
                    self.assertEqual(status,302)
                    before=len(destinations)
                    with self.assertRaises(ValueError): await public_fetch(headers['location'],client)
                    self.assertEqual(len(destinations),before)
                self.assertEqual(seen,['careers.example.org','careers.example.org'])
            finally:
                await asyncio.to_thread(server.shutdown);server.server_close();thread.join(5)

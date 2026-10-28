"""Fresh read-only Chromium for public job pages; no candidate session or local hosts."""
import asyncio
import ipaddress
import os
import socket
from urllib.parse import urlsplit,urlunsplit
import httpx
from playwright.async_api import async_playwright
from .browser import parse_posting
from .policy import Blocked,public_url,detect_ats


async def public_fetch(url,client,addresses=None):
    url=public_url(url,None,resolve=False)
    parsed=urlsplit(url);host=parsed.hostname
    if addresses is None:
        try:
            records=await asyncio.to_thread(socket.getaddrinfo,host,443,type=socket.SOCK_STREAM)
            addresses=list(dict.fromkeys(record[4][0] for record in records))
        except OSError: raise Blocked('PORTAL_ACCESS_UNAVAILABLE') from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses): raise Blocked('PRIVATE_DESTINATION')
    address=addresses[0]
    if ':' in address: address='['+address+']'
    pinned=urlunsplit(('https',address,parsed.path,parsed.query,''))
    # Pin the network destination, retain original Host and TLS SNI. DNS cannot
    # change the connection to a local address after validation.
    async with client.stream('GET',pinned,headers={'Host':host,'Connection':'close','User-Agent':'Mozilla/5.0 (compatible; PrivateJobsReader/1.0)'},extensions={'sni_hostname':host},follow_redirects=False) as response:
        chunks=[];size=0
        async for chunk in response.aiter_bytes():
            size+=len(chunk)
            if size>8*1024*1024: raise Blocked('PORTAL_RESOURCE_TOO_LARGE')
            chunks.append(chunk)
        headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-encoding','transfer-encoding','content-length','set-cookie')}
        return response.status_code,headers,b''.join(chunks)


async def read_posting(url,settings):
    public_url(url,None,resolve=False)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=settings.chromium,headless=True)
        context=await browser.new_context(service_workers='block',accept_downloads=False)
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                async def route(request_route):
                    request=request_route.request
                    if request.method!='GET' or request.resource_type in ('image','media','font'):
                        await request_route.abort('blockedbyclient');return
                    try:
                        status,headers,body=await public_fetch(request.url,client)
                        if status in (301,302,303,307,308):
                            # Chromium follows only through this same pinned guard.
                            await request_route.fulfill(status=status,headers=headers,body=b'')
                        else: await request_route.fulfill(status=status,headers=headers,body=body)
                    except (ValueError,OSError,httpx.HTTPError,Blocked): await request_route.abort('blockedbyclient')
                await context.route('**/*',route)
                await context.route_web_socket('**/*',lambda ws:ws.close())
                page=await context.new_page();page.set_default_timeout(15000)
                response=await page.goto(url,wait_until='domcontentloaded',timeout=45000)
                if response and response.status in (404,410): raise Blocked('VAGA_ENCERRADA')
                if response and response.status>=400: raise Blocked('PORTAL_ACCESS_UNAVAILABLE')
                # Allow SPA rendering, without waiting for ads/analytics forever.
                try: await page.wait_for_load_state('networkidle',timeout=6000)
                except Exception: pass
                job=await parse_posting(page)
                text=(await page.locator('body').inner_text())[:60000]
                ats,identity=detect_ats(page.url,[f.url for f in page.frames])
                if identity:
                    frame=next((f for f in page.frames if detect_ats(f.url,[])[1]==identity),page)
                    job['application_url']=frame.url
                    if frame!=page:
                        framed=await parse_posting(frame)
                        if framed.get('title') and framed.get('company'): job.update(framed)
                        text=(text+'\n'+await frame.locator('body').inner_text())[:60000]
                job['ats']=ats;job['identity']=identity
                if not job.get('company') and len(text)<500 and await page.locator('.g-recaptcha,.h-captcha,iframe[src*="recaptcha"],iframe[src*="hcaptcha"]').count():
                    raise Blocked('CAPTCHA_REQUIRES_HUMAN')
                return job,text
        finally:
            await context.close();await browser.close()

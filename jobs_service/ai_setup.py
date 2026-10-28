"""Validate model connectivity independently from job extraction, then save privately."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
import httpx
from jobs_service.intelligence import PROVIDERS,DEFAULT_MODEL
from jobs_service.policy import Blocked


async def verify_provider(provider,key,model=DEFAULT_MODEL,client=None):
    if provider not in PROVIDERS: raise Blocked('AI_PROVIDER_INVALID')
    if not key.strip(): raise Blocked('AI_NOT_CONFIGURED')
    if client is None:
        async with httpx.AsyncClient(timeout=90) as own:
            return await verify_provider(provider,key,model,own)
    try:
        response=await client.post(PROVIDERS[provider],headers={'Authorization':'Bearer '+key.strip()},json={
            'model':model,'temperature':0,'max_tokens':1024,'response_format':{'type':'json_object'},
            'messages':[{'role':'user','content':'Connection health check. Reply with exactly this JSON object: {"ready":true}. No explanation.'}]})
        errors={401:'AI_CREDENTIAL_REJECTED',403:'AI_ACCESS_REJECTED',402:'AI_INSUFFICIENT_CREDITS',404:'AI_MODEL_UNAVAILABLE',429:'AI_RATE_LIMITED'}
        if response.status_code in errors: raise Blocked(errors[response.status_code])
        if response.status_code>=500: raise Blocked('AI_PROVIDER_UNAVAILABLE')
        if response.status_code>=400: raise Blocked('AI_REQUEST_REJECTED')
        message=response.json()['choices'][0]['message']['content']
        result=json.loads(message)
        if not isinstance(result,dict) or result.get('ready') is not True: raise Blocked('AI_HANDSHAKE_INVALID')
    except httpx.HTTPError: raise Blocked('AI_CONNECTION_FAILED') from None
    except (ValueError,KeyError,IndexError,TypeError): raise Blocked('AI_HANDSHAKE_INVALID') from None


def main():
    config=json.load(sys.stdin)
    try: asyncio.run(verify_provider(config['provider'],config['api_key'],config['model']))
    except Blocked as error:
        print('AI_SETUP_FAILED: '+error.code);raise SystemExit(1)
    path=Path('/var/lib/jobs/ai-config.json')
    fd,name=tempfile.mkstemp(prefix='ai-config-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f: json.dump(config,f)
        os.chmod(name,0o600);os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)
    print('AI_CONFIGURED: conexao com o modelo validada; chave salva no volume privado. Analise de vaga real ainda depende de validacao.')


if __name__=='__main__': main()

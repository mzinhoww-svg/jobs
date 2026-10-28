"""Operator-only diagnostics: report categories, never upstream text or secrets."""
import asyncio
import json
import sys
import httpx
from jobs_service.intelligence import analyze_posting,DEFAULT_MODEL
from jobs_service.policy import Blocked


async def diagnose(provider,key,client=None):
    if client is None:
        async with httpx.AsyncClient(timeout=90) as own:
            return await diagnose(provider,key,own)
    result={'provider':provider,'model':DEFAULT_MODEL,'http_status':None,'category':'NETWORK_OR_TRANSPORT_ERROR'}
    async def observe(response):
        await response.aread()
        status=response.status_code;result['http_status']=status
        if status in (401,403): result['category']='CREDENTIAL_REJECTED';return
        if status==402: result['category']='INSUFFICIENT_CREDITS';return
        if status==429: result['category']='RATE_LIMITED';return
        if status==404: result['category']='MODEL_OR_ENDPOINT_NOT_FOUND';return
        if status>=500: result['category']='PROVIDER_UNAVAILABLE';return
        if status>=400: result['category']='REQUEST_REJECTED';return
        try: body=response.json()
        except ValueError: result['category']='RESPONSE_NOT_JSON';return
        choices=body.get('choices') if isinstance(body,dict) else None
        if not choices or not isinstance(choices,list) or not isinstance(choices[0],dict): result['category']='RESPONSE_HAS_NO_CHOICES';return
        choice=choices[0]
        if choice.get('finish_reason')=='length': result['category']='MODEL_OUTPUT_TRUNCATED';return
        message=choice.get('message')
        content=message.get('content') if isinstance(message,dict) else None
        if not isinstance(content,str) or not content.strip(): result['category']='MODEL_EMPTY_CONTENT';return
        try: json.loads(content)
        except ValueError: result['category']='MODEL_CONTENT_NOT_JSON';return
        result['category']='RESPONSE_RECEIVED'
    client.event_hooks['response'].append(observe)
    source='Payments Lead at Fictional Labs. This is a synthetic job posting for a payments professional to lead payment partnerships and product operations in Brazil.'
    facts=[{'id':'fixture','text':'Structured payment partnerships.','source':'synthetic test','confirmation':'confirmed','source_kind':'candidate_declaration','date':'2026-10-27'}]
    try:
        await analyze_posting(source,facts,key,DEFAULT_MODEL,provider,client)
        result['analysis']='OK';result['category']='AI_VALIDATED'
    except Blocked as error:
        result['analysis']=error.code
        if result['category']=='RESPONSE_RECEIVED': result['category']='MODEL_VALIDATION_FAILED'
    finally: client.event_hooks['response'].remove(observe)
    return result


if __name__=='__main__':
    config=json.load(sys.stdin)
    print('AI_DIAGNOSTIC '+json.dumps(asyncio.run(diagnose(config['provider'],config['api_key'])),ensure_ascii=False))

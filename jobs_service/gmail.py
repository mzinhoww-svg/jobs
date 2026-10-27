"""Read-only Gmail access. Never logs messages, OTPs or URLs with tokens."""
import base64
import json
import re
import time
from email.utils import getaddresses
from pathlib import Path
import httpx
from .policy import Blocked


def match_message(message, recipient, domains, requisition, started):
    raw=message.get('payload',{}).get('headers',[])
    headers={x['name'].lower():x['value'] for x in raw}
    # Use the first Google authentication result (prepended by receiving Gmail),
    # not a sender-supplied duplicate further down the headers.
    auth=next((x['value'] for x in raw if x['name'].lower()=='authentication-results'),'')
    senders=[a.lower() for _,a in getaddresses([headers.get('from','')])]
    recipients=[a.lower() for _,a in getaddresses([headers.get('to','')])]
    stamp=int(message.get('internalDate','0'))/1000
    subject=headers.get('subject','')
    sender_domain=senders[0].split('@')[-1] if len(senders)==1 else ''
    sender_authenticated=(auth.startswith('mx.google.com;') and bool(re.search(r'\bdmarc=pass\b[^;]*\bheader\.from='+re.escape(sender_domain)+r'(?:\s|;|$)',auth,re.I)))
    purpose=bool(re.search(r'\b(?:verify|verification|verifica\w*)\b',subject,re.I) and re.search(r'\b(?:application|candidatura|inscri\w*)\b',subject,re.I))
    exact_requisition=bool(re.search(r'(?<![A-Za-z0-9_-])'+re.escape(requisition)+r'(?![A-Za-z0-9_-])',subject))
    return (len(senders)==1 and senders[0].split('@')[-1] in domains
            and recipient.lower() in recipients and started <= stamp <= time.time()+30
            and exact_requisition and purpose and sender_authenticated)


def extract_otp(message, text, recipient, domains, requisition, started):
    if time.time()-started > 600 or not match_message(message,recipient,domains,requisition,started):
        return None
    matches=re.findall(r'\b(?:code|código)\s*(?:is|é|:)?\s*(\d{4,8})\b',text,re.I)
    return matches[0] if len(set(matches))==1 else None


def body_text(payload):
    data=payload.get('body',{}).get('data','')
    own=base64.urlsafe_b64decode(data+'='*(-len(data)%4)).decode('utf-8','replace') if data else ''
    return own+'\n'+'\n'.join(body_text(p) for p in payload.get('parts',[]))


class Gmail:
    def __init__(self, credential_file, expected_email):
        self.file=Path(credential_file)
        self.expected_email=expected_email
        self.client=httpx.Client(timeout=20)

    def _token(self):
        if not self.file.exists(): raise Blocked('GMAIL_OAUTH_MISSING')
        if self.file.stat().st_mode & 0o077: raise Blocked('GMAIL_CREDENTIAL_PERMISSIONS')
        data=json.loads(self.file.read_text())
        if data.get('refresh_token'):
            r=self.client.post('https://oauth2.googleapis.com/token',data={k:data[k] for k in ('client_id','client_secret','refresh_token')}|{'grant_type':'refresh_token'})
            if r.status_code!=200: raise Blocked('GMAIL_REFRESH_FAILED')
            return r.json()['access_token']
        if not data.get('access_token'): raise Blocked('GMAIL_OAUTH_MISSING')
        return data['access_token']

    def _get(self,path,params=None):
        r=self.client.get('https://gmail.googleapis.com/gmail/v1/users/me/'+path,headers={'Authorization':'Bearer '+self._token()},params=params)
        if r.status_code!=200: raise Blocked('GMAIL_ACCESS_UNAVAILABLE')
        return r.json()

    def verify_identity(self):
        identity=self._get('profile')
        if identity.get('emailAddress','').lower()!=self.expected_email.lower(): raise Blocked('GMAIL_ACCOUNT_MISMATCH')
        return True

    def messages_for(self, domains, requisition, started):
        self.verify_identity()
        # Escape user-controlled input; no arbitrary Gmail search expressions.
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',requisition): raise Blocked('GMAIL_CONTEXT_INVALID')
        if not all(re.fullmatch(r'[a-z0-9.-]+',d) for d in domains): raise Blocked('GMAIL_CONTEXT_INVALID')
        q=f'to:{self.expected_email} after:{int(started)} '+ ' {'+' '.join('from:@'+d for d in domains)+'} '+requisition
        results=self._get('messages',{'q':q,'maxResults':20})
        messages=[self._get('messages/'+m['id'],{'format':'full'}) for m in results.get('messages',[])]
        return [m for m in messages if match_message(m,self.expected_email,domains,requisition,started)]

    def verification_code(self,domains,requisition,started):
        messages=self.messages_for(domains,requisition,started)
        if len(messages)>1: raise Blocked('GMAIL_VERIFICATION_AMBIGUOUS')
        if messages:
            code=extract_otp(messages[0],body_text(messages[0]['payload']),self.expected_email,domains,requisition,started)
            if code: return code
        raise Blocked('GMAIL_CODE_NOT_FOUND_OR_EXPIRED')

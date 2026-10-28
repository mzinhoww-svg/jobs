"""Pure policy decisions. External pages cannot modify these rules."""
import ipaddress
import re
import socket
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class Blocked(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def verified_fact(fact):
    if (fact.get('confirmation')!='confirmed' or not fact.get('source')
        or fact.get('source_kind') not in {'candidate_declaration','professional_record','official_job_posting','verified_employer_source'}):
        return False
    try: date.fromisoformat(fact.get('date',''))
    except (TypeError,ValueError): return False
    return True


def canonical_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('INVALID_URL')
    if len(url) > 4096 or p.port not in (None, 80, 443):
        raise ValueError('INVALID_URL')
    # Strip tracking only; preserve parameters that may identify the requisition.
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    host = p.hostname.encode('idna').decode().lower()
    if ':' in host:
        host = '[' + host + ']'
    return urlunsplit((p.scheme, host, p.path.rstrip('/') or '/', urlencode(sorted(q)), ''))


def public_url(url, allowed_hosts=None, resolve=True):
    url = canonical_url(url)
    p = urlsplit(url)
    if p.scheme != 'https':
        raise ValueError('HTTPS_REQUIRED')
    host = p.hostname
    if host in ('localhost', 'metadata.google.internal') or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('PRIVATE_DESTINATION')
    if allowed_hosts is not None and host not in allowed_hosts:
        raise ValueError('HOST_NOT_APPROVED')
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)] if resolve else []
    if any(not ip.is_global for ip in addresses):
        raise ValueError('PRIVATE_DESTINATION')
    return url


PLATFORM_DOMAINS={
    'greenhouse.io':'Greenhouse','myworkdayjobs.com':'Workday','myworkdaysite.com':'Workday',
    'lever.co':'Lever','gupy.io':'Gupy','ashbyhq.com':'Ashby','smartrecruiters.com':'SmartRecruiters',
    'icims.com':'iCIMS','taleo.net':'Taleo','successfactors.com':'SuccessFactors',
    'successfactors.eu':'SuccessFactors','linkedin.com':'LinkedIn','indeed.com':'Indeed',
    'indeed.com.br':'Indeed','personio.de':'Personio','personio.com':'Personio','jobvite.com':'Jobvite','workable.com':'Workable','recruitee.com':'Recruitee','teamtailor.com':'Teamtailor','avature.net':'Avature'}


def platform_name(url):
    host=(urlsplit(url).hostname or '').lower()
    return next((name for domain,name in PLATFORM_DOMAINS.items() if host==domain or host.endswith('.'+domain)),None)


def approved_hosts(url, configured):
    """Known public ATS domains can be read; arbitrary hosts require pasted text."""
    host=urlsplit(url).hostname
    return tuple(dict.fromkeys([*configured,*([host] if platform_name(url) else [])]))


def detect_ats(url, frames):
    for candidate in [url, *frames]:
        p = urlsplit(candidate)
        host = p.hostname or ''
        if host == 'greenhouse.io' or host.endswith('.greenhouse.io'):
            match = re.search(r'^/([^/]+)/jobs/(\d+)', p.path)
            if match:
                return 'Greenhouse', f'greenhouse:{match[1]}:{match[2]}'
            query = dict(parse_qsl(p.query))
            if '/embed/job_app' in p.path and query.get('for') and query.get('token', '').isdigit():
                return 'Greenhouse', f"greenhouse:{query['for']}:{query['token']}"
    for candidate in [url,*frames]:
        name=platform_name(candidate)
        if name: return name,None
    return 'DESCONHECIDO', None


def profile_view(profile, country):
    if country not in ('BR', 'US'):
        raise Blocked('HIRING_COUNTRY_UNKNOWN')
    loc = profile['locations']['brazil' if country == 'BR' else 'united_states']
    identity = profile['identity']
    # Build a whitelist view instead of copying the full profile into documents.
    view = {k: identity.get(k) for k in ('full_name', 'preferred_email')}
    for k in ('phone', 'linkedin'):
        raw = identity.get(k)
        view[k] = raw.get('value') if isinstance(raw, dict) and verified_fact(raw) else (raw if isinstance(raw,str) else None)
    view['location'] = loc['cv_location']
    view['facts'] = [f for f in profile.get('facts', []) if verified_fact(f)]
    view['work_authorized'] = True if country == 'BR' else profile.get('work_authorization', {}).get('united_states', {}).get('authorized_for_target_employer')
    view['sponsorship'] = False if country == 'BR' else profile.get('work_authorization', {}).get('united_states', {}).get('future_sponsorship_required')
    return view


def choose_salary(research, annual_floors, fit=.5):
    currency = research.get('currency')
    if (currency not in annual_floors or research.get('kind') != 'base'
            or research.get('period') not in ('monthly', 'annual')
            or not research.get('sources') or not research.get('rationale')):
        raise Blocked('SALARY_RESEARCH_REQUIRED')
    for source in research['sources']:
        if not source.get('url') or not source.get('date'):
            raise Blocked('SALARY_SOURCE_REQUIRED')
    low, high = research.get('min'), research.get('max')
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or not 0 < low <= high:
        raise Blocked('SALARY_RANGE_UNKNOWN')
    annual_factor = 12 if research['period'] == 'monthly' else 1
    floor = annual_floors[currency] / annual_factor
    if high < floor:
        if research.get('official') is True:
            raise Blocked('INCOMPATIVEL_REMUNERACAO')
        raise Blocked('SALARY_LOW_CONFIDENCE')
    chosen = max(floor, low + (high - low) * max(0, min(1, fit)))
    return {**research, 'chosen': round(chosen, 2)}


def document_profile_view(profile,country):
    if country in ('BR','US'):
        return profile_view(profile,country)
    identity=profile['identity']
    view={k:identity.get(k) for k in ('full_name','preferred_email')}
    for key in ('phone','linkedin'):
        value=identity.get(key)
        view[key]=value.get('value') if isinstance(value,dict) and verified_fact(value) else value if isinstance(value,str) else None
    view['facts']=[f for f in profile.get('facts',[]) if verified_fact(f)]
    return view

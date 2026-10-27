import unittest
from jobs_service.policy import canonical_url, public_url, detect_ats, choose_salary, profile_view, Blocked


class PolicyTests(unittest.TestCase):
    def test_url_ssrf_and_credentials(self):
        for url in ['file:///etc/passwd', 'http://127.0.0.1/', 'https://u:p@example.com', 'https://169.254.169.254/', 'https://[::1]/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_url(url)
        self.assertEqual(canonical_url('https://EXAMPLE.com/job/1?utm_medium=x&gh_jid=123#foo'), 'https://example.com/job/1?gh_jid=123')

    def test_greenhouse_host_boundary_regional_and_iframe(self):
        self.assertEqual(detect_ats('https://boards.eu.greenhouse.io/acme/jobs/123', []), ('Greenhouse', 'greenhouse:acme:123'))
        self.assertEqual(detect_ats('https://company.test/careers?gh_jid=123', [])[0], 'DESCONHECIDO')
        self.assertEqual(detect_ats('https://company.test/careers', ['https://job-boards.greenhouse.io/acme/jobs/123'])[0], 'Greenhouse')
        self.assertEqual(detect_ats('https://greenhouse.io.evil.test/acme/jobs/123', [])[0], 'DESCONHECIDO')

    def test_salary_dynamic_and_base_floor(self):
        r = {'currency':'USD','period':'annual','kind':'base','min':140000,'max':180000,'official':True,'sources':[{'url':'https://company.test/jobs/1','date':'2026-10-27'}], 'rationale':'Published range for same role/location'}
        s = choose_salary(r, {'USD':96000}, fit=.75)
        self.assertEqual(s['chosen'], 170000)
        r['min'],r['max']=190000,230000
        self.assertEqual(choose_salary(r, {'USD':96000}, fit=.75)['chosen'],220000)
        r['max'],r['min']=90000,80000
        with self.assertRaises(Blocked) as e: choose_salary(r, {'USD':96000})
        self.assertEqual(e.exception.code,'INCOMPATIVEL_REMUNERACAO')

    def test_salary_unknown_total_and_low_confidence_do_not_invent(self):
        for r in [{}, {'currency':'USD','kind':'total'}, {'currency':'EUR','kind':'base'}, {'currency':'USD','kind':'base','min':50000,'max':60000,'official':False}]:
            with self.assertRaises(Blocked): choose_salary(r, {'USD':96000})

    def test_country_not_inferred_from_currency_and_unknown_authorization(self):
        p={'identity':{'full_name':'Fictional Candidate','preferred_email':'test@example.invalid'},'locations':{'brazil':{'cv_location':'São Paulo, Brazil'},'united_states':{'cv_location':'Miami, FL, USA'}},'work_authorization':{'united_states':{'authorized_for_target_employer':None}},'facts':[]}
        br=profile_view(p,'BR')
        self.assertNotIn('Miami',str(br))
        self.assertNotIn('visa',str(br))
        us=profile_view(p,'US')
        self.assertNotIn('full_address',us)
        self.assertIsNone(us['work_authorized'])
        with self.assertRaises(Blocked): profile_view(p,'LATAM')

    def test_generated_document_is_not_independent_provenance(self):
        p={'identity':{'full_name':'Example','preferred_email':'example@example.invalid','phone':{'value':'invented','confirmation':'unknown'}},'locations':{'brazil':{'cv_location':'São Paulo, Brazil'}},'facts':[{'id':'generated','text':'Made up fact','confirmation':'confirmed','source':'generated CV','source_kind':'generated_document','date':'2026-10-27'}]}
        view=profile_view(p,'BR')
        self.assertEqual(view['facts'],[])
        self.assertIsNone(view['phone'])

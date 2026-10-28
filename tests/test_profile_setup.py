import json,tempfile,unittest
from pathlib import Path
import httpx
from jobs_service.api import create_app
from jobs_service.config import Settings
from jobs_service.profile_setup import issue_link

PROFILE={'locations':{'brazil':{'cv_location':'São Paulo, Brazil'}},'identity':{'full_name':'Fictional Candidate','preferred_email':'fixture@example.invalid'},'facts':[{'id':'f1','text':'Structured payment partnerships.','source':'synthetic controlled test','source_kind':'candidate_declaration','date':'2026-10-27','confirmation':'confirmed'}]}

class ProfileSetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(Settings(self.root,self.root/'unused',(),auth_mode='none'))),base_url='http://testserver')
    async def asyncTearDown(self): await self.client.aclose();self.tmp.cleanup()

    async def test_public_app_cannot_import_profile_without_operator_link(self):
        r=await self.client.post('/setup/profile',json=PROFILE)
        self.assertEqual(r.status_code,401)
        self.assertFalse((self.root/'profile.json').exists())

    async def test_valid_link_imports_once_and_preserves_previous_profile(self):
        (self.root/'profile.json').write_text(json.dumps(PROFILE));(self.root/'profile.json').chmod(0o600)
        token=issue_link(self.root)
        changed={**PROFILE,'identity':{'full_name':'Updated Fictional Candidate','preferred_email':'fixture@example.invalid'}}
        response=await self.client.post('/setup/profile',headers={'X-Profile-Setup':token},json=changed)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(json.loads((self.root/'profile.json').read_text())['identity']['full_name'],'Updated Fictional Candidate')
        self.assertEqual((self.root/'profile.json').stat().st_mode&0o777,0o600)
        self.assertTrue(list(self.root.glob('profile-before-import-*.json')))
        self.assertEqual((await self.client.post('/setup/profile',headers={'X-Profile-Setup':token},json=changed)).status_code,401)
        self.assertNotIn(token,response.text)

    async def test_expired_or_invalid_profile_never_overwrites_data(self):
        expired=issue_link(self.root,now=0)
        self.assertEqual((await self.client.post('/setup/profile',headers={'X-Profile-Setup':expired},json=PROFILE)).status_code,401)
        token=issue_link(self.root)
        self.assertEqual((await self.client.post('/setup/profile',headers={'X-Profile-Setup':token},json={'identity':PROFILE['identity'],'facts':[]})).status_code,422)
        self.assertFalse((self.root/'profile.json').exists())
        self.assertEqual((await self.client.post('/setup/profile',headers={'X-Profile-Setup':token},json=PROFILE)).status_code,200)

    async def test_malformed_locations_or_translations_do_not_replace_profile(self):
        import copy
        (self.root/'profile.json').write_text(json.dumps(PROFILE))
        token=issue_link(self.root)
        for kind in ('locations','translations'):
            malformed=copy.deepcopy(PROFILE)
            if kind=='locations': malformed.pop('locations')
            else: malformed['facts'][0]['translations']=None
            r=await self.client.post('/setup/profile',headers={'X-Profile-Setup':token},json=malformed)
            self.assertEqual(r.status_code,422)
            self.assertEqual(json.loads((self.root/'profile.json').read_text()),PROFILE)

    async def test_write_failure_consumes_link_without_replacing_existing_profile(self):
        from unittest.mock import patch
        from jobs_service.profile_setup import consume_link,link_valid
        (self.root/'profile.json').write_text(json.dumps(PROFILE))
        token=issue_link(self.root)
        with patch('jobs_service.profile_setup.atomic_json',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError): consume_link(self.root,token,PROFILE)
        self.assertFalse(link_valid(self.root,token))
        self.assertEqual(json.loads((self.root/'profile.json').read_text()),PROFILE)

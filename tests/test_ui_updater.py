import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('docker'),'Deployment-host check requires Docker CLI/daemon.')
class UiUpdaterChecks(unittest.TestCase):
    def test_missing_override_cannot_create_or_replace_services(self):
        script=Path(__file__).resolve().parents[1]/'deploy/update-ui.sh'
        with tempfile.TemporaryDirectory() as tmp:
            env=os.environ.copy();env['JOBS_VPS_OVERRIDE']=str(Path(tmp)/'missing.json')
            before=subprocess.check_output(['docker','ps','-q'],text=True)
            result=subprocess.run(['bash',str(script),'--check'],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('VPS_OVERRIDE_MISSING',result.stderr)
            self.assertEqual(subprocess.check_output(['docker','ps','-q'],text=True),before)

    def test_new_config_cannot_silently_start_an_uninstalled_project(self):
        script=Path(__file__).resolve().parents[1]/'deploy/update-ui.sh'
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'override.json'
            config.write_text('{}')
            env=os.environ.copy();env.update(JOBS_VPS_OVERRIDE=str(config),JOBS_COMPOSE_PROJECT='missing-ui-update-fixture')
            before=subprocess.check_output(['docker','ps','-q'],text=True)
            result=subprocess.run(['bash',str(script),'--check'],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('EXISTING_STACK_NOT_FOUND',result.stderr)
            self.assertEqual(subprocess.check_output(['docker','ps','-q'],text=True),before)

    def test_changed_compose_volume_is_rejected_before_mutation(self):
        import json
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); override=folder/'override.json';override.write_text('{}')
            cli=folder/'docker'
            cli.write_text("#!/usr/bin/env python3\n"+"import sys,json\n"+
                "a=sys.argv[1:]\n"+
                "if a[0]=='compose':\n"+
                " if a[-1]=='--quiet': pass\n"+
                " elif 'ps' in a: print('container-'+a[-1])\n"+
                " elif a[-1]=='--images': print('candidaturas-jobs:local')\n"+
                " elif a[-2:]==['--format','json']: print(json.dumps({'services':{s:{'volumes':[{'target':'/var/lib/jobs','type':'volume','source':'jobs-private'}]} for s in ['api','worker']},'volumes':{'jobs-private':{'name':'wrong-volume'}}}))\n"+
                " else: raise SystemExit('UNEXPECTED_MUTATION')\n"+
                "elif a[0]=='inspect':\n"+
                " fmt=a[2]\n"+
                " if 'working_dir' in fmt: print("+repr(str(root))+ ")\n"+
                " elif '.Config.Image' in fmt: print('candidaturas-jobs:local')\n"+
                " else: print('existing-private-volume')\n"+
                "else: raise SystemExit('UNEXPECTED_MUTATION')\n")
            cli.chmod(0o700)
            env=os.environ.copy();env.update(PATH=str(folder)+os.pathsep+env['PATH'],JOBS_VPS_OVERRIDE=str(override))
            result=subprocess.run(['bash',str(root/'deploy/update-ui.sh'),'--check'],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('PRIVATE_COMPOSE_VOLUME_MISMATCH',result.stderr)
            self.assertNotIn('UNEXPECTED_MUTATION',result.stderr)

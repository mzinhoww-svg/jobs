import os
import socket
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


@unittest.skipUnless(shutil.which('docker'), 'Host deployment checks require Docker CLI/daemon; run on the deployment host or CI host.')
class VpsInstallerTests(unittest.TestCase):
    def test_rejects_symlinked_parent_before_creating_any_installation(self):
        script=Path(__file__).resolve().parents[1]/'deploy/install-vps.sh'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'real').mkdir()
            (root/'alias').symlink_to(root/'real',target_is_directory=True)
            env=os.environ.copy();env['JOBS_INSTALL_ROOT']=str(root/'alias'/'app-install')
            result=subprocess.run(['bash',str(script),'--check'],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('INSTALL_ROOT_NOT_CANONICAL',result.stderr)
            self.assertFalse((root/'real'/'app-install').exists())

    def test_refuses_existing_project_resources_from_another_root(self):
        script=Path(__file__).resolve().parents[1]/'deploy/install-vps.sh'
        network='jobs-installer-test-'+uuid.uuid4().hex
        subprocess.run(['docker','network','create','--label','com.docker.compose.project=candidaturas-jobs','--label','io.candidaturas.install-root=/different-installation',network],check=True,capture_output=True)
        try:
            with tempfile.TemporaryDirectory() as tmp,socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
                root=Path(tmp)/'new-install'
                env=os.environ.copy();env.update(JOBS_INSTALL_ROOT=str(root),JOBS_HTTP_PORT=str(port))
                result=subprocess.run(['bash',str(script),'--check'],env=env,text=True,capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('PROJECT_ALREADY_EXISTS',result.stderr)
                self.assertFalse(root.exists())
        finally:
            subprocess.run(['docker','network','rm',network],check=True,capture_output=True)

    def test_check_refuses_busy_port_without_writes_or_container_changes(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen()
            target=Path(tmp)/'installation-must-not-be-created'
            env=os.environ.copy()
            env.update(JOBS_INSTALL_ROOT=str(target),JOBS_HTTP_PORT=str(listener.getsockname()[1]))
            before=subprocess.check_output(['docker','ps','-q'],text=True)
            result=subprocess.run(['bash',str(root/'deploy/install-vps.sh'),'--check'],env=env,text=True,capture_output=True)
            after=subprocess.check_output(['docker','ps','-q'],text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('PORT_IN_USE',result.stdout+result.stderr)
            self.assertFalse(target.exists())
            self.assertEqual(before,after)

    def test_check_free_port_is_read_only_and_compose_is_isolated(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
            probe.close()
            target=Path(tmp)/'not-created'
            env=os.environ.copy()
            env.update(JOBS_INSTALL_ROOT=str(target),JOBS_HTTP_PORT=str(port))
            result=subprocess.run(['bash',str(root/'deploy/install-vps.sh'),'--check'],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PREFLIGHT_OK',result.stdout)
            self.assertFalse(target.exists())
            config=subprocess.run(['docker','compose','-p','candidaturas-jobs','-f',str(root/'compose.yaml'),'-f',str(root/'deploy/compose.vps.yaml'),'config','--format','json'],env=env,text=True,capture_output=True)
            self.assertEqual(config.returncode,0,config.stderr)
            import json
            services=json.loads(config.stdout)['services']
            self.assertEqual(services['api']['ports'][0]['host_ip'],'127.0.0.1')
            self.assertEqual(int(services['api']['ports'][0]['published']),port)
            self.assertEqual(int(services['worker']['mem_limit']),768*1024*1024)
            self.assertTrue(services['worker']['image'].startswith('candidaturas-jobs:'))

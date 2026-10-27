import json
import tempfile
import unittest
from pathlib import Path
from jobs_service.admin import initialize, backup, restore
from jobs_service.store import Store


class AdminTests(unittest.TestCase):
    def test_init_no_overwrite_and_consistent_backup_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/'data'
            initialize(data)
            token=(data/'api-token').read_text()
            self.assertGreaterEqual(len(token),32)
            self.assertEqual((data/'api-token').stat().st_mode & 0o777,0o600)
            initialize(data)
            self.assertEqual((data/'api-token').read_text(),token)
            store=Store(data/'queue.sqlite3')
            row,_=store.submit('https://example.com/jobs/1')
            artifacts=data/'applications'/row['id']
            artifacts.mkdir(parents=True)
            (artifacts/'cv.pdf').write_bytes(b'synthetic artifact')
            snapshot=root/'snapshot'
            backup(data,snapshot)
            restored=root/'restored'
            restore(snapshot,restored)
            self.assertEqual(Store(restored/'queue.sqlite3').get(row['id'])['status'],'RECEBIDA')
            self.assertEqual((restored/'applications'/row['id']/'cv.pdf').read_bytes(),b'synthetic artifact')
            self.assertFalse((snapshot/'api-token').exists())
            with self.assertRaises(ValueError): restore(snapshot,restored)

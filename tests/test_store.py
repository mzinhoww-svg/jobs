import tempfile
import unittest
from pathlib import Path

from jobs_service.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'queue.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_deduplication_and_persistence(self):
        a, dup = self.store.submit('https://boards.greenhouse.io/example/jobs/123?utm_source=a')
        b, duplicate = Store(self.path).submit('https://boards.greenhouse.io/example/jobs/123')
        self.assertFalse(dup)
        self.assertTrue(duplicate)
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(Store(self.path).get(a['id'])['status'], 'RECEBIDA')

    def test_single_worker_claim_and_expired_recovery(self):
        a, _ = self.store.submit('https://example.com/jobs/1')
        self.assertEqual(self.store.claim('w1', now=100)['id'], a['id'])
        self.assertIsNone(self.store.claim('w2', now=101))
        self.assertEqual(self.store.claim('w2', now=500)['id'], a['id'])

    def test_intent_survives_crash_without_resubmit(self):
        a, _ = self.store.submit('https://example.com/jobs/2')
        self.store.claim('w1', now=100)
        self.store.submit_intent(a['id'], 'w1')
        self.assertIsNone(Store(self.path).claim('w2', now=500))
        self.assertEqual(self.store.get(a['id'])['status'], 'ENVIO_INCERTO')
        with self.assertRaises(ValueError):
            self.store.resume(a['id'])

    def test_proof_required_and_wrong_worker_rejected(self):
        a, _ = self.store.submit('https://example.com/jobs/3')
        self.store.claim('w1')
        with self.assertRaises(ValueError):
            self.store.finish(a['id'], 'w2', 'BLOQUEADA', 'UNKNOWN')
        with self.assertRaises(ValueError):
            self.store.finish(a['id'], 'w1', 'ENVIADA_COMPROVADA', None)

    def test_canonical_identity_prevents_cross_url_duplicate(self):
        a, _ = self.store.submit('https://example.com/careers/123')
        b, _ = self.store.submit('https://boards.greenhouse.io/acme/jobs/123')
        self.assertTrue(self.store.identify(a['id'], 'greenhouse:acme:123'))
        self.assertFalse(self.store.identify(b['id'], 'greenhouse:acme:123'))
        self.assertEqual(self.store.get(b['id'])['status'], 'DUPLICADA')

    def test_promote_prepare_to_apply_without_losing_identity(self):
        a,_=self.store.submit('https://example.com/jobs/10','prepare')
        self.store.claim('prepare')
        self.store.identify(a['id'],'greenhouse:example:10')
        self.store.finish(a['id'],'prepare','DOCUMENTOS_PRONTOS','PREPARE_COMPLETE_NO_UPLOAD')
        promoted,duplicate=self.store.submit(a['url'],'apply')
        self.assertTrue(duplicate)
        self.assertEqual(promoted['mode'],'apply')
        self.assertEqual(promoted['status'],'RECEBIDA')
        self.assertEqual(promoted['identity'],'greenhouse:example:10')

    def test_promotion_while_analyzing_is_queued(self):
        a,_=self.store.submit('https://example.com/jobs/11','analyze')
        self.store.claim('analysis')
        self.store.submit(a['url'],'apply')
        self.store.finish(a['id'],'analysis','EM_ANALISE','ANALYSIS_COMPLETE')
        self.assertEqual(self.store.get(a['id'])['status'],'RECEBIDA')
        self.assertEqual(self.store.claim('apply')['mode'],'apply')

    def test_alternate_canonical_url_can_promote_existing_prepare(self):
        a,_=self.store.submit('https://example.com/jobs/12','prepare')
        self.store.identify(a['id'],'greenhouse:example:12')
        b,_=self.store.submit('https://boards.greenhouse.io/example/jobs/12','apply')
        self.assertFalse(self.store.identify(b['id'],'greenhouse:example:12'))
        self.assertEqual(self.store.get(a['id'])['mode'],'apply')

    def test_finish_is_single_transaction(self):
        a,_=self.store.submit('https://example.com/jobs/13')
        self.store.claim('worker')
        transactions=[]
        original=self.store.db
        from contextlib import contextmanager
        @contextmanager
        def traced():
            with original() as c:
                c.set_trace_callback(transactions.append)
                yield c
        self.store.db=traced
        self.store.finish(a['id'],'worker','BLOQUEADA','UNKNOWN_REQUIRED')
        self.assertEqual(sum(x.upper()=='COMMIT' for x in transactions),1)

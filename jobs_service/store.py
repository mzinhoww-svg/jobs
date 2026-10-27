"""Durable single-profile queue; intent is committed before browser submit."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .policy import canonical_url

STATES = {'RECEBIDA', 'EM_ANALISE', 'DOCUMENTOS_PRONTOS', 'EM_PREENCHIMENTO',
          'AGUARDANDO_VERIFICACAO', 'ENVIADA_COMPROVADA', 'ENVIO_INCERTO', 'DUPLICADA',
          'VAGA_ENCERRADA', 'INCOMPATIVEL_REMUNERACAO', 'INCOMPATIVEL_REQUISITO', 'BLOQUEADA'}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as c:
            c.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT, identity TEXT UNIQUE,
                owner TEXT, lease REAL DEFAULT 0, attempts INTEGER DEFAULT 0,
                available REAL DEFAULT 0, intent INTEGER DEFAULT 0, payload TEXT DEFAULT '{}',
                created REAL NOT NULL, updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, application_id TEXT, status TEXT, reason TEXT, at REAL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _event(self, c, id, status, reason=None):
        c.execute('INSERT INTO events(application_id,status,reason,at) VALUES(?,?,?,?)', (id, status, reason, time.time()))

    def _promote(self,c,row,mode):
        rank={'analyze':0,'prepare':1,'apply':2}
        if row['intent'] or rank[mode]<=rank[row['mode']]: return False
        if row['owner']:
            c.execute('UPDATE applications SET mode=?,updated=? WHERE id=?',(mode,time.time(),row['id']))
        else:
            c.execute("UPDATE applications SET mode=?,status='RECEBIDA',reason='MODE_PROMOTED',available=0,updated=? WHERE id=?",(mode,time.time(),row['id']))
        self._event(c,row['id'],'RECEBIDA' if not row['owner'] else row['status'],'MODE_PROMOTED_TO_'+mode.upper())
        return True

    def submit(self, url, mode='apply'):
        if mode not in ('apply', 'analyze', 'prepare'):
            raise ValueError('INVALID_MODE')
        url = canonical_url(url)
        now, id = time.time(), uuid.uuid4().hex
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM applications WHERE url=?', (url,)).fetchone()
            if old:
                self._promote(c,old,mode)
                return dict(c.execute('SELECT * FROM applications WHERE id=?',(old['id'],)).fetchone()), True
            c.execute('INSERT INTO applications(id,url,mode,status,created,updated) VALUES(?,?,?,?,?,?)', (id, url, mode, 'RECEBIDA', now, now))
            self._event(c, id, 'RECEBIDA')
        return self.get(id), False

    def get(self, id):
        with self.db() as c:
            row = c.execute('SELECT * FROM applications WHERE id=?', (id,)).fetchone()
            return dict(row) if row else None

    def _filters(self, q='', state=None):
        where, args=[], []
        if state:
            if state not in STATES: raise ValueError('INVALID_STATE')
            where.append('status=?');args.append(state)
        if q:
            literal=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            pattern='%'+literal+'%'
            where.append("(url LIKE ? ESCAPE '\\' OR json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.job.title') LIKE ? ESCAPE '\\' OR json_extract(CASE WHEN json_valid(payload) THEN payload ELSE '{}' END,'$.job.company') LIKE ? ESCAPE '\\')")
            args.extend([pattern]*3)
        return (' WHERE '+' AND '.join(where) if where else ''), args

    def list(self, limit=200, offset=0, q='', state=None):
        if not 1<=limit<=200 or offset<0: raise ValueError('INVALID_PAGINATION')
        where,args=self._filters(q,state)
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM applications'+where+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',[*args,limit,offset])]

    def count(self, q='', state=None):
        where,args=self._filters(q,state)
        with self.db() as c:
            return c.execute('SELECT COUNT(*) FROM applications'+where,args).fetchone()[0]

    def counts(self):
        with self.db() as c:
            by_status={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) AS n FROM applications GROUP BY status')}
        return {'total':sum(by_status.values()),'by_status':by_status}

    def history(self, id):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT status,reason,at FROM events WHERE application_id=? ORDER BY seq', (id,))]

    def claim(self, owner, now=None):
        now = time.time() if now is None else now
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            expired = c.execute('SELECT id,intent FROM applications WHERE owner IS NOT NULL AND lease<?', (now,)).fetchall()
            for r in expired:
                status = 'ENVIO_INCERTO' if r['intent'] else 'RECEBIDA'
                c.execute('UPDATE applications SET status=?,reason=?,owner=NULL,lease=0,updated=? WHERE id=?', (status, 'WORKER_INTERRUPTED', now, r['id']))
                self._event(c, r['id'], status, 'WORKER_INTERRUPTED')
            if c.execute('SELECT 1 FROM applications WHERE owner IS NOT NULL').fetchone():
                return None
            row = c.execute("SELECT * FROM applications WHERE status='RECEBIDA' AND available<=? ORDER BY created LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            c.execute("UPDATE applications SET status='EM_ANALISE',owner=?,lease=?,attempts=attempts+1,updated=? WHERE id=?", (owner, now+180, now, row['id']))
            self._event(c, row['id'], 'EM_ANALISE')
            return dict(c.execute('SELECT * FROM applications WHERE id=?', (row['id'],)).fetchone())

    def heartbeat(self, id, owner):
        with self.db() as c:
            result = c.execute('UPDATE applications SET lease=? WHERE id=? AND owner=?', (time.time()+180, id, owner))
            if result.rowcount != 1:
                raise ValueError('LEASE_LOST')

    def identify(self, id, identity):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            other = c.execute('SELECT * FROM applications WHERE identity=? AND id<>?', (identity, id)).fetchone()
            if other:
                current=c.execute('SELECT * FROM applications WHERE id=?',(id,)).fetchone()
                self._promote(c,other,current['mode'])
                c.execute("UPDATE applications SET status='DUPLICADA',reason='CANONICAL_DUPLICATE',owner=NULL,lease=0 WHERE id=?", (id,))
                self._event(c, id, 'DUPLICADA', 'CANONICAL_DUPLICATE')
                return False
            c.execute('UPDATE applications SET identity=? WHERE id=?', (identity, id))
            return True

    def checkpoint(self, id, owner, status, payload=None):
        if status not in STATES:
            raise ValueError('INVALID_STATE')
        with self.db() as c:
            row = c.execute('SELECT * FROM applications WHERE id=? AND owner=?', (id, owner)).fetchone()
            if not row:
                raise ValueError('LEASE_LOST')
            data = json.loads(row['payload'])
            data.update(payload or {})
            c.execute('UPDATE applications SET status=?,payload=?,updated=? WHERE id=?', (status, json.dumps(data), time.time(), id))
            self._event(c, id, status)

    def submit_intent(self, id, owner):
        with self.db() as c:
            n = c.execute("UPDATE applications SET intent=1,status='EM_PREENCHIMENTO',updated=? WHERE id=? AND owner=? AND mode='apply' AND intent=0", (time.time(), id, owner)).rowcount
            if n != 1:
                raise ValueError('SUBMIT_NOT_AUTHORIZED')
            self._event(c, id, 'EM_PREENCHIMENTO', 'SUBMIT_INTENT')

    def finish(self, id, owner, status, reason, payload=None):
        if status not in STATES: raise ValueError('INVALID_STATE')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM applications WHERE id=? AND owner=?',(id,owner)).fetchone()
            if not row: raise ValueError('LEASE_LOST')
            if status=='ENVIADA_COMPROVADA':
                proof=(payload or {}).get('proof',{})
                if not row['intent'] or proof.get('identity')!=row['identity'] or not proof.get('confirmation_hash'):
                    raise ValueError('PROOF_REQUIRED')
            if ((reason=='ANALYSIS_COMPLETE' and row['mode'] in ('prepare','apply'))
                or (reason=='PREPARE_COMPLETE_NO_UPLOAD' and row['mode']=='apply')):
                status,reason='RECEBIDA','MODE_PROMOTION_QUEUED'
            data=json.loads(row['payload']);data.update(payload or {})
            c.execute('UPDATE applications SET status=?,payload=?,reason=?,owner=NULL,lease=0,updated=? WHERE id=?',
                      (status,json.dumps(data),reason,time.time(),id))
            self._event(c,id,status,reason)

    def retry(self, id, owner):
        row = self.get(id)
        if row['intent']:
            return self.finish(id, owner, 'ENVIO_INCERTO', 'RECONCILIATION_REQUIRED')
        if row['attempts'] >= 3:
            return self.finish(id, owner, 'BLOQUEADA', 'RETRY_LIMIT')
        self.finish(id, owner, 'RECEBIDA', 'TRANSIENT_RETRY')
        with self.db() as c:
            c.execute('UPDATE applications SET available=? WHERE id=?', (time.time()+30*2**row['attempts'], id))

    def resume(self, id):
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM applications WHERE id=?', (id,)).fetchone()
            if not row or row['intent'] or row['status'] not in ('BLOQUEADA', 'AGUARDANDO_VERIFICACAO', 'DOCUMENTOS_PRONTOS'):
                raise ValueError('RESUME_NOT_ALLOWED')
            c.execute("UPDATE applications SET status='RECEBIDA',reason=NULL,available=0,attempts=0 WHERE id=?", (id,))
            self._event(c, id, 'RECEBIDA', 'MANUAL_RESUME')

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from layers.layer4.logger import RecoveryLogger

class Store:
    def __init__(self, path):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp TEXT, kind TEXT, payload TEXT)')
        self.connection.commit()

    def add(self, kind, payload):
        self.connection.execute('INSERT INTO events(timestamp,kind,payload) VALUES(?,?,?)',
            (datetime.now(timezone.utc).isoformat(), kind, json.dumps(payload, default=str)))
        self.connection.commit()

    def recent(self, limit=100):
        rows = self.connection.execute('SELECT id,timestamp,kind,payload FROM events ORDER BY id DESC LIMIT ?', (limit,))
        return [dict(id=r[0], timestamp=r[1], kind=r[2], payload=json.loads(r[3])) for r in rows]

    def close(self):
        self.connection.close()

class AuditLogger(RecoveryLogger):
    def __init__(self, store):
        super().__init__()
        self.store = store

    def log(self, event_type, payload):
        entry = super().log(event_type, payload)
        self._entries = self._entries[-500:]
        self.store.add(event_type, payload)
        return entry

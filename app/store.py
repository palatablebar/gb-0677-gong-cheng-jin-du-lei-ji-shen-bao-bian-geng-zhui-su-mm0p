import sqlite3,json
from datetime import datetime,timezone
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
from app.seal import build_seal
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS seals (business_sha TEXT PRIMARY KEY,run_id TEXT NOT NULL,payload TEXT NOT NULL,sealed_at TEXT NOT NULL)")
    return db
def save(run_id,payload):
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False)))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def save_seal(run):
    payload=build_seal(run)
    sealed_at=datetime.now(timezone.utc).isoformat();payload["run_record"]["sealed_at"]=sealed_at
    with connect() as db:
        cursor=db.execute("INSERT OR IGNORE INTO seals(business_sha,run_id,payload,sealed_at) VALUES (?,?,?,?)",(payload["business_sha256"],run["run_id"],json.dumps(payload,ensure_ascii=False),sealed_at))
        created=cursor.rowcount==1
    return get_seal(run["run_id"]),created
def get_seal(run_id):
    with connect() as db: row=db.execute("SELECT payload FROM seals WHERE run_id=? ORDER BY rowid DESC LIMIT 1",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_SEALED","批次尚未封存",404)
    return json.loads(row[0])
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)

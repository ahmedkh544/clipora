import hashlib, hmac, os, secrets, sqlite3, time
from pathlib import Path

DB_PATH=Path(os.getenv("CLIPORA_DB_PATH", "/data/clipora.db" if os.name != "nt" else "studio_data/clipora.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
FREE_MONTHLY_JOBS=int(os.getenv("CLIPORA_FREE_MONTHLY_JOBS", "3"))


def _db():
    c=sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,
          plan TEXT NOT NULL DEFAULT 'free',created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '',error TEXT,clips_json TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id,created_at DESC);
        """)


def _hash_password(password, salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),310000).hex()
    return salt+"$"+digest


def _check_password(password, encoded):
    try:
        salt,digest=encoded.split("$",1)
        actual=hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),310000).hex()
        return hmac.compare_digest(actual,digest)
    except ValueError:
        return False


def create_user(email,password):
    email=email.strip().lower()
    if len(password)<8: raise ValueError("Password must contain at least 8 characters")
    uid=secrets.token_hex(16)
    with _db() as c:
        try:c.execute("INSERT INTO users VALUES(?,?,?,?,?)",(uid,email,_hash_password(password),"free",time.time()))
        except sqlite3.IntegrityError: raise ValueError("Email already registered")
    return uid


def authenticate(email,password):
    with _db() as c:
        row=c.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
    if not row or not _check_password(password,row["password_hash"]): return None
    return dict(row)


def create_session(user_id,days=14):
    token=secrets.token_urlsafe(32)
    with _db() as c:c.execute("INSERT INTO sessions VALUES(?,?,?)",(token,user_id,time.time()+days*86400))
    return token


def get_user_by_session(token):
    if not token:return None
    with _db() as c:
        row=c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?",(token,time.time())).fetchone()
    return dict(row) if row else None


def logout(token):
    if token:
        with _db() as c:c.execute("DELETE FROM sessions WHERE token=?",(token,))


def monthly_job_count(user_id):
    month=time.strftime("%Y-%m",time.gmtime())
    with _db() as c:return c.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND strftime('%Y-%m',datetime(created_at,'unixepoch'))=?",(user_id,month)).fetchone()[0]


def can_create_job(user):
    return user["plan"]=="pro" or monthly_job_count(user["id"])<FREE_MONTHLY_JOBS


def create_job(job_id,user_id):
    now=time.time()
    with _db() as c:c.execute("INSERT INTO jobs(id,user_id,status,progress,message,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(job_id,user_id,"queued",0,"Queued",now,now))


def update_job(job_id,**fields):
    if not fields:return
    fields["updated_at"]=time.time()
    sets=", ".join(f"{k}=?" for k in fields)
    with _db() as c:c.execute(f"UPDATE jobs SET {sets} WHERE id=?",(*fields.values(),job_id))


def get_job(job_id,user_id=None):
    with _db() as c:
        q="SELECT * FROM jobs WHERE id=?"; args=[job_id]
        if user_id:q+=" AND user_id=?"; args.append(user_id)
        row=c.execute(q,args).fetchone()
    if not row:return None
    import json
    out=dict(row); out["clips"]=json.loads(out.pop("clips_json") or "[]"); return out


def recent_jobs(user_id,limit=20):
    with _db() as c: rows=c.execute("SELECT id,status,progress,message,error,created_at,updated_at FROM jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",(user_id,limit)).fetchall()
    return [dict(r) for r in rows]


def cleanup_old_files(root,max_age_hours=24):
    cutoff=time.time()-max_age_hours*3600; removed=0
    for p in Path(root).glob("**/*"):
        if p.is_file() and p.stat().st_mtime<cutoff:
            try:p.unlink(); removed+=1
            except OSError:pass
    return removed


init_db()

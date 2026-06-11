from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import sqlite3
import hashlib
import jwt
import os
import base64
import json

SECRET_KEY = os.environ.get("SECRET_KEY", "weekly-report-secret-key-2024")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12
DB_PATH = "weekly_report.db"

app = FastAPI(title="Weekly Report API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# ── DB 초기화 ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','team_leader','group_leader','line_leader')),
            team_id INTEGER REFERENCES teams(id),
            group_id INTEGER REFERENCES groups(id),
            line_id INTEGER REFERENCES lines(id)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            week_label TEXT NOT NULL,
            status TEXT,
            schedule TEXT,
            assignee_id INTEGER REFERENCES users(id),
            note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            content_type TEXT,
            data BLOB NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # 기본 admin 계정
    pw = hashlib.sha256("admin1234".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users(username,password,full_name,role) VALUES(?,?,?,?)",
              ("admin", pw, "시스템관리자", "admin"))
    conn.commit()
    conn.close()

init_db()

# ── 인증 헬퍼 ─────────────────────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")
    return dict(user)

def require_manager(user=Depends(get_current_user)):
    if user["role"] not in ("admin", "team_leader", "group_leader", "line_leader"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    return user

# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class LoginReq(BaseModel):
    username: str
    password: str

class TeamReq(BaseModel):
    name: str

class GroupReq(BaseModel):
    name: str
    team_id: int

class LineReq(BaseModel):
    name: str
    group_id: int

class UserReq(BaseModel):
    username: str
    password: str
    full_name: str
    role: str
    team_id: Optional[int] = None
    group_id: Optional[int] = None
    line_id: Optional[int] = None

class UserUpdateReq(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    team_id: Optional[int] = None
    group_id: Optional[int] = None
    line_id: Optional[int] = None
    password: Optional[str] = None

class TaskReq(BaseModel):
    name: str
    group_id: int

class ActivityReq(BaseModel):
    task_id: int
    name: str
    week_label: str  # 예: "2024-W23"
    status: Optional[str] = None
    schedule: Optional[str] = None
    assignee_id: Optional[int] = None
    note: Optional[str] = None

class ActivityUpdateReq(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    schedule: Optional[str] = None
    assignee_id: Optional[int] = None
    note: Optional[str] = None

# ── 인증 ──────────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def login(req: LoginReq):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (req.username, hash_pw(req.password))
    ).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀립니다")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": {
        "id": user["id"], "username": user["username"],
        "full_name": user["full_name"], "role": user["role"],
        "team_id": user["team_id"], "group_id": user["group_id"], "line_id": user["line_id"]
    }}

@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user

# ── 팀 ────────────────────────────────────────────────────────────────────────

@app.get("/teams")
def list_teams(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/teams", status_code=201)
def create_team(req: TeamReq, user=Depends(require_manager)):
    conn = get_db()
    try:
        cur = conn.execute("INSERT INTO teams(name) VALUES(?)", (req.name,))
        conn.commit()
        tid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 팀명입니다")
    finally:
        conn.close()
    return {"id": tid, "name": req.name}

@app.put("/teams/{tid}")
def update_team(tid: int, req: TeamReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE teams SET name=? WHERE id=?", (req.name, tid))
    conn.commit()
    conn.close()
    return {"id": tid, "name": req.name}

@app.delete("/teams/{tid}", status_code=204)
def delete_team(tid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM teams WHERE id=?", (tid,))
    conn.commit()
    conn.close()

# ── 그룹 ──────────────────────────────────────────────────────────────────────

@app.get("/groups")
def list_groups(team_id: Optional[int] = None, user=Depends(get_current_user)):
    conn = get_db()
    if team_id:
        rows = conn.execute(
            "SELECT g.*, t.name as team_name FROM groups g JOIN teams t ON t.id=g.team_id WHERE g.team_id=? ORDER BY g.name",
            (team_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT g.*, t.name as team_name FROM groups g JOIN teams t ON t.id=g.team_id ORDER BY t.name, g.name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/groups", status_code=201)
def create_group(req: GroupReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO groups(name,team_id) VALUES(?,?)", (req.name, req.team_id))
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return {"id": gid, "name": req.name, "team_id": req.team_id}

@app.put("/groups/{gid}")
def update_group(gid: int, req: GroupReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE groups SET name=?, team_id=? WHERE id=?", (req.name, req.team_id, gid))
    conn.commit()
    conn.close()
    return {"id": gid, "name": req.name, "team_id": req.team_id}

@app.delete("/groups/{gid}", status_code=204)
def delete_group(gid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    conn.commit()
    conn.close()

# ── 라인 ──────────────────────────────────────────────────────────────────────

@app.get("/lines")
def list_lines(group_id: Optional[int] = None, user=Depends(get_current_user)):
    conn = get_db()
    if group_id:
        rows = conn.execute(
            "SELECT l.*, g.name as group_name FROM lines l JOIN groups g ON g.id=l.group_id WHERE l.group_id=? ORDER BY l.name",
            (group_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT l.*, g.name as group_name FROM lines l JOIN groups g ON g.id=l.group_id ORDER BY g.name, l.name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/lines", status_code=201)
def create_line(req: LineReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO lines(name,group_id) VALUES(?,?)", (req.name, req.group_id))
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return {"id": lid, "name": req.name, "group_id": req.group_id}

@app.put("/lines/{lid}")
def update_line(lid: int, req: LineReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE lines SET name=?, group_id=? WHERE id=?", (req.name, req.group_id, lid))
    conn.commit()
    conn.close()
    return {"id": lid, "name": req.name, "group_id": req.group_id}

@app.delete("/lines/{lid}", status_code=204)
def delete_line(lid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM lines WHERE id=?", (lid,))
    conn.commit()
    conn.close()

# ── 사용자 ────────────────────────────────────────────────────────────────────

@app.get("/users")
def list_users(user=Depends(require_manager)):
    conn = get_db()
    rows = conn.execute(
        """SELECT u.id, u.username, u.full_name, u.role,
                  u.team_id, t.name as team_name,
                  u.group_id, g.name as group_name,
                  u.line_id, l.name as line_name
           FROM users u
           LEFT JOIN teams t ON t.id=u.team_id
           LEFT JOIN groups g ON g.id=u.group_id
           LEFT JOIN lines l ON l.id=u.line_id
           ORDER BY u.role, u.full_name"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/users", status_code=201)
def create_user(req: UserReq, user=Depends(require_manager)):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users(username,password,full_name,role,team_id,group_id,line_id) VALUES(?,?,?,?,?,?,?)",
            (req.username, hash_pw(req.password), req.full_name, req.role, req.team_id, req.group_id, req.line_id)
        )
        conn.commit()
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다")
    finally:
        conn.close()
    return {"id": uid}

@app.put("/users/{uid}")
def update_user(uid: int, req: UserUpdateReq, user=Depends(require_manager)):
    conn = get_db()
    fields, vals = [], []
    if req.full_name is not None:
        fields.append("full_name=?"); vals.append(req.full_name)
    if req.role is not None:
        fields.append("role=?"); vals.append(req.role)
    if req.team_id is not None:
        fields.append("team_id=?"); vals.append(req.team_id)
    if req.group_id is not None:
        fields.append("group_id=?"); vals.append(req.group_id)
    if req.line_id is not None:
        fields.append("line_id=?"); vals.append(req.line_id)
    if req.password is not None:
        fields.append("password=?"); vals.append(hash_pw(req.password))
    if fields:
        vals.append(uid)
        conn.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/users/{uid}", status_code=204)
def delete_user(uid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()

# ── 업무(Task) ────────────────────────────────────────────────────────────────

@app.get("/tasks")
def list_tasks(group_id: Optional[int] = None, user=Depends(get_current_user)):
    conn = get_db()
    if group_id:
        rows = conn.execute(
            "SELECT t.*, g.name as group_name FROM tasks t JOIN groups g ON g.id=t.group_id WHERE t.group_id=? ORDER BY t.name",
            (group_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT t.*, g.name as group_name FROM tasks t JOIN groups g ON g.id=t.group_id ORDER BY g.name, t.name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/tasks", status_code=201)
def create_task(req: TaskReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO tasks(name,group_id) VALUES(?,?)", (req.name, req.group_id))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {"id": tid, "name": req.name, "group_id": req.group_id}

@app.put("/tasks/{tid}")
def update_task(tid: int, req: TaskReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE tasks SET name=?, group_id=? WHERE id=?", (req.name, req.group_id, tid))
    conn.commit()
    conn.close()
    return {"id": tid}

@app.delete("/tasks/{tid}", status_code=204)
def delete_task(tid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()

# ── Activity ──────────────────────────────────────────────────────────────────

@app.get("/activities")
def list_activities(
    week_label: Optional[str] = None,
    task_id: Optional[int] = None,
    group_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    conn = get_db()
    q = """
        SELECT a.*, t.name as task_name, t.group_id,
               g.name as group_name,
               u.full_name as assignee_name
        FROM activities a
        JOIN tasks t ON t.id=a.task_id
        JOIN groups g ON g.id=t.group_id
        LEFT JOIN users u ON u.id=a.assignee_id
        WHERE 1=1
    """
    params = []
    if week_label:
        q += " AND a.week_label=?"; params.append(week_label)
    if task_id:
        q += " AND a.task_id=?"; params.append(task_id)
    if group_id:
        q += " AND t.group_id=?"; params.append(group_id)
    q += " ORDER BY g.name, t.name, a.name"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/activities", status_code=201)
def create_activity(req: ActivityReq, user=Depends(get_current_user)):
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO activities(task_id,name,week_label,status,schedule,assignee_id,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (req.task_id, req.name, req.week_label, req.status, req.schedule, req.assignee_id, req.note, now, now)
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return {"id": aid}

@app.put("/activities/{aid}")
def update_activity(aid: int, req: ActivityUpdateReq, user=Depends(get_current_user)):
    conn = get_db()
    fields, vals = ["updated_at=?"], [datetime.utcnow().isoformat()]
    if req.name is not None:
        fields.append("name=?"); vals.append(req.name)
    if req.status is not None:
        fields.append("status=?"); vals.append(req.status)
    if req.schedule is not None:
        fields.append("schedule=?"); vals.append(req.schedule)
    if req.assignee_id is not None:
        fields.append("assignee_id=?"); vals.append(req.assignee_id)
    if req.note is not None:
        fields.append("note=?"); vals.append(req.note)
    vals.append(aid)
    conn.execute(f"UPDATE activities SET {','.join(fields)} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/activities/{aid}", status_code=204)
def delete_activity(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM activities WHERE id=?", (aid,))
    conn.commit()
    conn.close()

@app.post("/activities/copy-from-prev-week")
def copy_from_prev_week(
    current_week: str,
    task_id: Optional[int] = None,
    group_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    """전주 activity 목록을 반환 (금주 신규 입력 시 참조용)"""
    # current_week: "2024-W24" → prev: "2024-W23"
    try:
        year, wnum = current_week.split("-W")
        year, wnum = int(year), int(wnum)
        if wnum == 1:
            prev_label = f"{year-1}-W52"
        else:
            prev_label = f"{year}-W{wnum-1:02d}"
    except Exception:
        raise HTTPException(status_code=400, detail="week_label 형식 오류 (예: 2024-W23)")

    conn = get_db()
    q = """
        SELECT a.*, t.name as task_name, t.group_id, g.name as group_name, u.full_name as assignee_name
        FROM activities a
        JOIN tasks t ON t.id=a.task_id
        JOIN groups g ON g.id=t.group_id
        LEFT JOIN users u ON u.id=a.assignee_id
        WHERE a.week_label=?
    """
    params = [prev_label]
    if task_id:
        q += " AND a.task_id=?"; params.append(task_id)
    if group_id:
        q += " AND t.group_id=?"; params.append(group_id)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return {"prev_week": prev_label, "activities": [dict(r) for r in rows]}

# ── 첨부파일 ──────────────────────────────────────────────────────────────────

@app.get("/activities/{aid}/attachments")
def list_attachments(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, activity_id, filename, content_type, uploaded_at FROM attachments WHERE activity_id=?",
        (aid,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/activities/{aid}/attachments", status_code=201)
async def upload_attachment(aid: int, file: UploadFile = File(...), user=Depends(get_current_user)):
    data = await file.read()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO attachments(activity_id,filename,content_type,data) VALUES(?,?,?,?)",
        (aid, file.filename, file.content_type, data)
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return {"id": fid, "filename": file.filename}

@app.get("/attachments/{fid}")
def download_attachment(fid: int, user=Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다")
    import io
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.BytesIO(row["data"]),
        media_type=row["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'}
    )

@app.delete("/attachments/{fid}", status_code=204)
def delete_attachment(fid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM attachments WHERE id=?", (fid,))
    conn.commit()
    conn.close()

# ── 주간 조회 헬퍼 ────────────────────────────────────────────────────────────

@app.get("/weekly-report")
def weekly_report(week_label: str, group_id: Optional[int] = None, user=Depends(get_current_user)):
    """그룹별 업무/activity 트리 반환"""
    conn = get_db()
    g_q = "SELECT * FROM groups"
    g_p = []
    if group_id:
        g_q += " WHERE id=?"; g_p.append(group_id)
    groups = conn.execute(g_q, g_p).fetchall()
    result = []
    for grp in groups:
        tasks = conn.execute("SELECT * FROM tasks WHERE group_id=? ORDER BY name", (grp["id"],)).fetchall()
        task_list = []
        for t in tasks:
            acts = conn.execute(
                """SELECT a.*, u.full_name as assignee_name
                   FROM activities a LEFT JOIN users u ON u.id=a.assignee_id
                   WHERE a.task_id=? AND a.week_label=? ORDER BY a.name""",
                (t["id"], week_label)
            ).fetchall()
            task_list.append({"id": t["id"], "name": t["name"], "activities": [dict(a) for a in acts]})
        result.append({"id": grp["id"], "name": grp["name"], "tasks": task_list})
    conn.close()
    return result

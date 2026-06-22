"""
weekly_report 패키지 공통 설정:
DB 연결, 인증 헬퍼, Pydantic 모델을 여기서 관리합니다.
"""
import sqlite3
import hashlib
import hmac
import base64
import json
import os
from ctypes import CDLL
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ── 설정값 ─────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "weekly-report-secret-key-2024")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12
DB_PATH = os.environ.get("WR_DB_PATH", os.path.join(os.path.dirname(__file__), "weekly_report.sqlite"))

security = HTTPBearer(auto_error=False)

# ── DRM ────────────────────────────────────────────────────────────────────────

def _enable_drm():
    """DRM 보호 파일 접근 전 Fasoo DRM 활성화"""
    try:
        fasoo = CDLL("c:/windows/system32/f_nxldr.dll")
        ret = fasoo.EnableDRM()
        return ret
    except OSError:
        # Windows 환경이 아니거나 DLL 없을 때 무시 (개발 환경 등)
        pass

# ── DB ─────────────────────────────────────────────────────────────────────────

def get_db():
    _enable_drm()
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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','team_leader','group_leader','line_leader','member')),
            team_id INTEGER REFERENCES teams(id),
            group_id INTEGER REFERENCES groups(id)
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
        CREATE TABLE IF NOT EXISTS activity_assignees (
            activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (activity_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS activity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            action TEXT NOT NULL CHECK(action IN ('create','update')),
            changed_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # 기존 단일 담당자(assignee_id)를 복수 담당자 테이블로 이전 (기존 DB 호환)
    conn.execute("""
        INSERT OR IGNORE INTO activity_assignees(activity_id, user_id)
        SELECT id, assignee_id FROM activities WHERE assignee_id IS NOT NULL
    """)
    # 기본 admin 계정
    pw = hashlib.sha256("admin1234".encode()).hexdigest()
    c.execute(
        "INSERT OR IGNORE INTO users(username,password,full_name,role) VALUES(?,?,?,?)",
        ("admin", pw, "시스템관리자", "admin")
    )
    conn.commit()
    # tasks.sort_order 마이그레이션 (기존 DB 호환)
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    # activity_history 테이블 마이그레이션 (기존 DB 호환)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                action TEXT NOT NULL,
                changed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    except Exception:
        pass
    # lines 테이블 / users.line_id 제거 마이그레이션 (기존 DB 호환)
    # 'line_leader' 역할은 유지하되, 조직 단위 'lines' 테이블과 연결 컬럼만 제거
    try:
        conn.execute("DROP TABLE IF EXISTS lines")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE users DROP COLUMN line_id")
        conn.commit()
    except Exception:
        pass  # 컬럼이 이미 없는 경우 무시
    conn.commit()
    conn.close()

# ── 인증 ───────────────────────────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def create_token(user_id: int, role: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp = int((datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp())
    payload = _b64url(json.dumps({"sub": str(user_id), "role": role, "exp": exp}).encode())
    sig = _b64url(hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"

def _decode_token(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid")
        header, payload_b64, sig = parts
        expected = _b64url(
            hmac.new(SECRET_KEY.encode(), f"{header}.{payload_b64}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature mismatch")
        # base64 패딩 복원
        pad = 4 - len(payload_b64) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (pad % 4)))
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            raise ValueError("expired")
        return payload
    except ValueError:
        raise
    except Exception:
        raise ValueError("invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    try:
        payload = _decode_token(credentials.credentials)
        user_id = int(payload["sub"])
    except ValueError as e:
        if "expired" in str(e):
            raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
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

# ── Pydantic 모델 ───────────────────────────────────────────────────────────────

class LoginReq(BaseModel):
    username: str
    password: str

class TeamReq(BaseModel):
    name: str

class GroupReq(BaseModel):
    name: str
    team_id: int

class UserReq(BaseModel):
    username: str
    password: str
    full_name: str
    role: str
    team_id: Optional[int] = None
    group_id: Optional[int] = None

class UserUpdateReq(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    team_id: Optional[int] = None
    group_id: Optional[int] = None
    password: Optional[str] = None

class TaskReq(BaseModel):
    name: str
    group_id: int

class ActivityReq(BaseModel):
    task_id: int
    name: str
    week_label: str
    status: Optional[str] = None
    schedule: Optional[str] = None
    assignee_ids: Optional[List[int]] = None
    note: Optional[str] = None

class ActivityUpdateReq(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    schedule: Optional[str] = None
    assignee_ids: Optional[List[int]] = None
    note: Optional[str] = None

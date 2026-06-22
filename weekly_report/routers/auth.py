from fastapi import APIRouter, HTTPException
from weekly_report.core import (
    LoginReq, get_db, hash_pw, create_token, get_current_user,
    init_db, DB_PATH, Depends
)
import os

router = APIRouter(prefix="/wr/auth", tags=["WR - 인증"])


@router.get("/health")
def health():
    """서버 연결 및 DB 상태 확인용 (인증 불필요)"""
    db_exists = os.path.exists(DB_PATH)
    try:
        conn = get_db()
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        db_ok = True
    except Exception as e:
        db_ok = False
        user_count = str(e)
    return {
        "status": "ok",
        "db_path": DB_PATH,
        "db_exists": db_exists,
        "db_ok": db_ok,
        "user_count": user_count,
    }


@router.post("/login")
def login(req: LoginReq):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=? AND (is_deleted IS NULL OR is_deleted=0)",
        (req.username, hash_pw(req.password))
    ).fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀립니다")
    token = create_token(user["id"], user["role"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "team_id": user["team_id"],
            "group_id": user["group_id"],
        },
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user

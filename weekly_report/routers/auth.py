from fastapi import APIRouter
from weekly_report.core import (
    LoginReq, get_db, hash_pw, create_token, get_current_user, Depends
)

router = APIRouter(prefix="/wr/auth", tags=["WR - 인증"])

@router.post("/login")
def login(req: LoginReq):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (req.username, hash_pw(req.password))
    ).fetchone()
    conn.close()
    from fastapi import HTTPException
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀립니다")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": {
        "id": user["id"], "username": user["username"],
        "full_name": user["full_name"], "role": user["role"],
        "team_id": user["team_id"], "group_id": user["group_id"], "line_id": user["line_id"]
    }}

@router.get("/me")
def me(user=Depends(get_current_user)):
    return user

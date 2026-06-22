import sqlite3
from fastapi import APIRouter, HTTPException, Depends
from weekly_report.core import (
    get_db, hash_pw, require_manager, get_current_user,
    UserReq, UserUpdateReq
)

router = APIRouter(prefix="/wr/users", tags=["WR - 사용자"])


def _validate_membership(role, team_id, group_id):
    """admin을 제외한 모든 사용자는 팀 필수, 그룹은 선택(팀 하부 조직)."""
    if role == "admin":
        return
    if team_id is None:
        raise HTTPException(status_code=400, detail="팀은 필수입니다")


@router.post("/register", status_code=201)
def register_user(req: UserReq):
    """회원가입 — 인증 불필요. role은 admin 제외."""
    if req.role == "admin":
        raise HTTPException(status_code=403, detail="admin 역할은 직접 가입할 수 없습니다")
    _validate_membership(req.role, req.team_id, req.group_id)
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users(username,password,full_name,role,team_id,group_id) VALUES(?,?,?,?,?,?)",
            (req.username, hash_pw(req.password), req.full_name, req.role,
             req.team_id, req.group_id)
        )
        conn.commit()
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다")
    finally:
        conn.close()
    return {"id": uid}

@router.get("")
def list_users(user=Depends(require_manager)):
    conn = get_db()
    rows = conn.execute(
        """SELECT u.id, u.username, u.full_name, u.role,
                  u.team_id, t.name as team_name,
                  u.group_id, g.name as group_name
           FROM users u
           LEFT JOIN teams t ON t.id=u.team_id
           LEFT JOIN groups g ON g.id=u.group_id
           WHERE u.is_deleted IS NULL OR u.is_deleted=0
           ORDER BY u.role, u.full_name"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("", status_code=201)
def create_user(req: UserReq, user=Depends(require_manager)):
    _validate_membership(req.role, req.team_id, req.group_id)
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users(username,password,full_name,role,team_id,group_id) VALUES(?,?,?,?,?,?)",
            (req.username, hash_pw(req.password), req.full_name, req.role,
             req.team_id, req.group_id)
        )
        conn.commit()
        uid = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 아이디입니다")
    finally:
        conn.close()
    return {"id": uid}

@router.put("/{uid}")
def update_user(uid: int, req: UserUpdateReq, user=Depends(get_current_user)):
    # 본인 비밀번호 변경은 허용, 그 외 필드 수정은 관리자만 허용
    is_self = user["id"] == uid
    is_manager = user["role"] in ("admin", "team_leader", "group_leader", "line_leader")
    if not is_self and not is_manager:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    if is_self and not is_manager:
        if any(v is not None for v in [req.full_name, req.role, req.team_id, req.group_id]):
            raise HTTPException(status_code=403, detail="권한이 없습니다")
    conn = get_db()
    # 관리자가 역할을 포함해 수정하는 경우, 팀/그룹을 한 쌍으로 기록하고 소속 규칙 검증
    is_full_edit = is_manager and req.role is not None
    fields, vals = [], []
    if req.full_name  is not None: fields.append("full_name=?");  vals.append(req.full_name)
    if req.role       is not None: fields.append("role=?");       vals.append(req.role)
    if is_full_edit:
        _validate_membership(req.role, req.team_id, req.group_id)
        fields.append("team_id=?");  vals.append(req.team_id)
        fields.append("group_id=?"); vals.append(req.group_id)
    else:
        if req.team_id    is not None: fields.append("team_id=?");    vals.append(req.team_id)
        if req.group_id   is not None: fields.append("group_id=?");   vals.append(req.group_id)
    if req.password   is not None: fields.append("password=?");   vals.append(hash_pw(req.password))
    if fields:
        vals.append(uid)
        conn.execute(f"UPDATE users SET {','.join(fields)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"ok": True}

@router.delete("/{uid}", status_code=204)
def delete_user(uid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE users SET is_deleted=1, deleted_at=datetime('now') WHERE id=?", (uid,))
    conn.commit()
    conn.close()

@router.get("/deleted")
def list_deleted_users(user=Depends(require_manager)):
    conn = get_db()
    rows = conn.execute(
        """SELECT u.id, u.username, u.full_name, u.role,
                  u.team_id, t.name as team_name,
                  u.group_id, g.name as group_name, u.deleted_at
           FROM users u
           LEFT JOIN teams t ON t.id=u.team_id
           LEFT JOIN groups g ON g.id=u.group_id
           WHERE u.is_deleted=1
           ORDER BY u.deleted_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/{uid}/restore", status_code=200)
def restore_user(uid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE users SET is_deleted=0, deleted_at=NULL WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return {"ok": True}

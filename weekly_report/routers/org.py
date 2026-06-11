import sqlite3
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from weekly_report.core import (
    get_db, get_current_user, require_manager,
    TeamReq, GroupReq, LineReq
)

router = APIRouter(prefix="/wr", tags=["WR - 조직"])

# ── 팀 ────────────────────────────────────────────────────────────────────────

@router.get("/teams")
def list_teams(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/teams", status_code=201)
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

@router.put("/teams/{tid}")
def update_team(tid: int, req: TeamReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE teams SET name=? WHERE id=?", (req.name, tid))
    conn.commit()
    conn.close()
    return {"id": tid, "name": req.name}

@router.delete("/teams/{tid}", status_code=204)
def delete_team(tid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM teams WHERE id=?", (tid,))
    conn.commit()
    conn.close()

# ── 그룹 ──────────────────────────────────────────────────────────────────────

@router.get("/groups")
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

@router.post("/groups", status_code=201)
def create_group(req: GroupReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO groups(name,team_id) VALUES(?,?)", (req.name, req.team_id))
    conn.commit()
    gid = cur.lastrowid
    conn.close()
    return {"id": gid, "name": req.name, "team_id": req.team_id}

@router.put("/groups/{gid}")
def update_group(gid: int, req: GroupReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE groups SET name=?, team_id=? WHERE id=?", (req.name, req.team_id, gid))
    conn.commit()
    conn.close()
    return {"id": gid}

@router.delete("/groups/{gid}", status_code=204)
def delete_group(gid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM groups WHERE id=?", (gid,))
    conn.commit()
    conn.close()

# ── 라인 ──────────────────────────────────────────────────────────────────────

@router.get("/lines")
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

@router.post("/lines", status_code=201)
def create_line(req: LineReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO lines(name,group_id) VALUES(?,?)", (req.name, req.group_id))
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return {"id": lid, "name": req.name, "group_id": req.group_id}

@router.put("/lines/{lid}")
def update_line(lid: int, req: LineReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE lines SET name=?, group_id=? WHERE id=?", (req.name, req.group_id, lid))
    conn.commit()
    conn.close()
    return {"id": lid}

@router.delete("/lines/{lid}", status_code=204)
def delete_line(lid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM lines WHERE id=?", (lid,))
    conn.commit()
    conn.close()

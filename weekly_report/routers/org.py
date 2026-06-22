import sqlite3
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from weekly_report.core import (
    get_db, get_current_user, require_manager,
    TeamReq, GroupReq
)

router = APIRouter(prefix="/wr", tags=["WR - 조직"])

# ── 팀 ────────────────────────────────────────────────────────────────────────

@router.get("/teams")
def list_teams():
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
def list_groups(team_id: Optional[int] = None):
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

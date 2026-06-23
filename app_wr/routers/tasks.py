from typing import Optional
from fastapi import APIRouter, Depends, Body
from app_wr.core import (
    get_db, get_current_user, require_manager, TaskReq
)

router = APIRouter(prefix="/app_wr/tasks", tags=["WR - 업무"])

@router.get("")
def list_tasks(group_id: Optional[int] = None, user=Depends(get_current_user)):
    conn = get_db()
    if group_id:
        rows = conn.execute(
            "SELECT t.*, g.name as group_name FROM tasks t JOIN groups g ON g.id=t.group_id WHERE t.group_id=? ORDER BY t.sort_order, t.name",
            (group_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT t.*, g.name as group_name FROM tasks t JOIN groups g ON g.id=t.group_id ORDER BY g.name, t.sort_order, t.name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.put("/reorder")
def reorder_tasks(items: list[dict] = Body(...), user=Depends(require_manager)):
    conn = get_db()
    for item in items:
        conn.execute("UPDATE tasks SET sort_order=? WHERE id=?", (item["sort_order"], item["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}

@router.post("", status_code=201)
def create_task(req: TaskReq, user=Depends(require_manager)):
    conn = get_db()
    cur = conn.execute("INSERT INTO tasks(name,group_id) VALUES(?,?)", (req.name, req.group_id))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {"id": tid, "name": req.name, "group_id": req.group_id}

@router.put("/{tid}")
def update_task(tid: int, req: TaskReq, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE tasks SET name=?, group_id=? WHERE id=?", (req.name, req.group_id, tid))
    conn.commit()
    conn.close()
    return {"id": tid}

@router.delete("/{tid}", status_code=204)
def delete_task(tid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()

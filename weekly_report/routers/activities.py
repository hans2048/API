import io
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from weekly_report.core import (
    get_db, get_current_user,
    ActivityReq, ActivityUpdateReq
)

router = APIRouter(prefix="/wr", tags=["WR - Activity / 첨부"])


# ── Activity ──────────────────────────────────────────────────────────────────

ASSIGNEE_COLS = """
       (SELECT GROUP_CONCAT(u2.full_name, ', ') FROM activity_assignees aa2
        JOIN users u2 ON u2.id=aa2.user_id WHERE aa2.activity_id=a.id) as assignee_names,
       (SELECT GROUP_CONCAT(aa3.user_id) FROM activity_assignees aa3
        WHERE aa3.activity_id=a.id) as assignee_id_list
"""


def _set_assignees(conn, activity_id: int, assignee_ids):
    conn.execute("DELETE FROM activity_assignees WHERE activity_id=?", (activity_id,))
    for uid in assignee_ids or []:
        conn.execute(
            "INSERT OR IGNORE INTO activity_assignees(activity_id, user_id) VALUES(?,?)",
            (activity_id, uid),
        )


def _row_to_dict(row):
    d = dict(row)
    ids = d.pop("assignee_id_list", None)
    d["assignee_ids"] = [int(x) for x in ids.split(",")] if ids else []
    return d


@router.get("/activities")
def list_activities(
    week_label: Optional[str] = None,
    task_id: Optional[int] = None,
    group_id: Optional[int] = None,
    user=Depends(get_current_user),
):
    conn = get_db()
    q = f"""
        SELECT a.*, t.name as task_name, t.group_id,
               g.name as group_name,
               {ASSIGNEE_COLS}
        FROM activities a
        JOIN tasks t ON t.id=a.task_id
        JOIN groups g ON g.id=t.group_id
        WHERE 1=1
    """
    params = []
    if week_label:
        q += " AND a.week_label=?"
        params.append(week_label)
    if task_id:
        q += " AND a.task_id=?"
        params.append(task_id)
    if group_id:
        q += " AND t.group_id=?"
        params.append(group_id)
    q += " ORDER BY g.name, t.name, a.name"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# ★ copy-from-prev-week 는 반드시 /{aid} 보다 먼저 등록해야 경로 충돌 없음
@router.get("/activities/copy-from-prev-week")
def copy_from_prev_week(
    current_week: str,
    task_id: Optional[int] = None,
    group_id: Optional[int] = None,
    user=Depends(get_current_user),
):
    try:
        year, wnum = current_week.split("-W")
        year, wnum = int(year), int(wnum)
        prev_label = f"{year-1}-W52" if wnum == 1 else f"{year}-W{wnum-1:02d}"
    except Exception:
        raise HTTPException(status_code=400, detail="week_label 형식 오류 (예: 2024-W23)")

    conn = get_db()
    q = f"""
        SELECT a.*, t.name as task_name, t.group_id, g.name as group_name,
               {ASSIGNEE_COLS}
        FROM activities a
        JOIN tasks t ON t.id=a.task_id
        JOIN groups g ON g.id=t.group_id
        WHERE a.week_label=?
    """
    params = [prev_label]
    if task_id:
        q += " AND a.task_id=?"
        params.append(task_id)
    if group_id:
        q += " AND t.group_id=?"
        params.append(group_id)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return {"prev_week": prev_label, "activities": [_row_to_dict(r) for r in rows]}


@router.post("/activities", status_code=201)
def create_activity(req: ActivityReq, user=Depends(get_current_user)):
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        """INSERT INTO activities
           (task_id, name, week_label, status, schedule, note, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (req.task_id, req.name, req.week_label, req.status,
         req.schedule, req.note, now, now),
    )
    aid = cur.lastrowid
    _set_assignees(conn, aid, req.assignee_ids)
    conn.commit()
    conn.close()
    return {"id": aid}


@router.put("/activities/{aid}")
def update_activity(aid: int, req: ActivityUpdateReq, user=Depends(get_current_user)):
    conn = get_db()
    fields, vals = ["updated_at=?"], [datetime.utcnow().isoformat()]
    if req.name        is not None: fields.append("name=?");        vals.append(req.name)
    if req.status      is not None: fields.append("status=?");      vals.append(req.status)
    if req.schedule    is not None: fields.append("schedule=?");    vals.append(req.schedule)
    if req.note        is not None: fields.append("note=?");        vals.append(req.note)
    vals.append(aid)
    conn.execute(f"UPDATE activities SET {','.join(fields)} WHERE id=?", vals)
    if req.assignee_ids is not None:
        _set_assignees(conn, aid, req.assignee_ids)
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/activities/{aid}", status_code=204)
def delete_activity(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM activities WHERE id=?", (aid,))
    conn.commit()
    conn.close()


# ── 첨부파일 ──────────────────────────────────────────────────────────────────

@router.get("/activities/{aid}/attachments")
def list_attachments(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, activity_id, filename, content_type, uploaded_at FROM attachments WHERE activity_id=?",
        (aid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/activities/{aid}/attachments", status_code=201)
async def upload_attachment(
    aid: int, file: UploadFile = File(...), user=Depends(get_current_user)
):
    data = await file.read()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO attachments(activity_id, filename, content_type, data) VALUES(?,?,?,?)",
        (aid, file.filename, file.content_type, data),
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return {"id": fid, "filename": file.filename}


@router.get("/attachments/{fid}")
def download_attachment(fid: int, user=Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다")
    return StreamingResponse(
        io.BytesIO(row["data"]),
        media_type=row["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )


@router.delete("/attachments/{fid}", status_code=204)
def delete_attachment(fid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM attachments WHERE id=?", (fid,))
    conn.commit()
    conn.close()


# ── 주간 보고 트리 ────────────────────────────────────────────────────────────

@router.get("/weekly-report")
def weekly_report(
    week_label: str,
    group_id: Optional[int] = None,
    user=Depends(get_current_user),
):
    conn = get_db()
    g_q, g_p = "SELECT * FROM groups", []
    if group_id:
        g_q += " WHERE id=?"
        g_p.append(group_id)
    groups = conn.execute(g_q, g_p).fetchall()
    result = []
    for grp in groups:
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE group_id=? ORDER BY name", (grp["id"],)
        ).fetchall()
        task_list = []
        for t in tasks:
            acts = conn.execute(
                f"""SELECT a.*, {ASSIGNEE_COLS}
                   FROM activities a
                   WHERE a.task_id=? AND a.week_label=? ORDER BY a.name""",
                (t["id"], week_label),
            ).fetchall()
            task_list.append({
                "id": t["id"],
                "name": t["name"],
                "activities": [_row_to_dict(a) for a in acts],
            })
        result.append({"id": grp["id"], "name": grp["name"], "tasks": task_list})
    conn.close()
    return result

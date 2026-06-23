import io
import os
import re
import uuid
from urllib.parse import quote
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Body, Request
from fastapi.responses import StreamingResponse
from weekly_report.core import (
    get_db, get_current_user, require_manager,
    _enable_drm,
    ActivityReq, ActivityUpdateReq
)

# DRM 해제를 위한 임시 폴더 (서버 로컬 디스크)
_CASH_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.cash')


def _content_disposition(filename: str) -> str:
    """RFC 5987 인코딩으로 한글 파일명을 안전하게 처리."""
    ascii_name = re.sub(r'[^\x20-\x7e]', '_', filename)
    encoded = quote(filename, encoding='utf-8')
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _safe_tmp_name(filename: str) -> str:
    """임시 파일명: 한글 등 비ASCII 문자를 ASCII로 치환."""
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'tmp'
    return f"{uuid.uuid4().hex}.{ext}"


def _read_drm_free(raw: bytes, filename: str) -> bytes:
    """
    업로드된 바이트를 임시 파일로 저장 → _enable_drm() 상태에서 다시 읽기.
    Fasoo DRM 에이전트가 서버 프로세스를 인가 앱으로 처리하므로
    디스크에서 읽을 때 자동 복호화된 바이트가 반환됨.
    """
    os.makedirs(_CASH_DIR, exist_ok=True)
    tmp_path = os.path.join(_CASH_DIR, _safe_tmp_name(filename))
    try:
        # 1. 임시 저장 (DRM 암호화 상태 그대로)
        with open(tmp_path, 'wb') as f:
            f.write(raw)
        # 2. DRM 활성화 후 다시 읽기 → 복호화된 바이트
        _enable_drm()
        with open(tmp_path, 'rb') as f:
            return f.read()
    finally:
        # 3. 임시 파일 삭제
        try:
            os.remove(tmp_path)
        except OSError:
            pass

router = APIRouter(prefix="/app_wr", tags=["WR - Activity / 첨부"])


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
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    conn = get_db()
    q = f"""
        SELECT a.*, t.name as task_name, t.group_id,
               g.name as group_name, g.team_id, tm.name as team_name,
               {ASSIGNEE_COLS}
        FROM activities a
        JOIN tasks t ON t.id=a.task_id
        JOIN groups g ON g.id=t.group_id
        JOIN teams tm ON tm.id=g.team_id
        WHERE (a.is_deleted IS NULL OR a.is_deleted=0)
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
    if from_date:
        q += " AND DATE(a.created_at) >= DATE(?)"
        params.append(from_date)
    if to_date:
        q += " AND DATE(a.created_at) <= DATE(?)"
        params.append(to_date)
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
        WHERE a.week_label=? AND (a.is_deleted IS NULL OR a.is_deleted=0)
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
    conn.execute(
        "INSERT INTO activity_history(activity_id, user_id, action) VALUES(?,?,?)",
        (aid, user["id"], "create"),
    )
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
    conn.execute(
        "INSERT INTO activity_history(activity_id, user_id, action) VALUES(?,?,?)",
        (aid, user["id"], "update"),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/activities/{aid}/history")
def get_activity_history(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """SELECT h.id, h.action, h.changed_at, u.full_name, u.username
           FROM activity_history h
           JOIN users u ON u.id = h.user_id
           WHERE h.activity_id = ?
           ORDER BY h.changed_at DESC""",
        (aid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/activities/deleted")
def list_deleted_activities(user=Depends(require_manager)):
    conn = get_db()
    rows = conn.execute(
        f"""SELECT a.*, t.name as task_name, g.name as group_name,
                   g.team_id, tm.name as team_name, {ASSIGNEE_COLS}
            FROM activities a
            JOIN tasks t ON t.id=a.task_id
            JOIN groups g ON g.id=t.group_id
            JOIN teams tm ON tm.id=g.team_id
            WHERE a.is_deleted=1
            ORDER BY a.deleted_at DESC"""
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

@router.post("/activities/{aid}/restore", status_code=200)
def restore_activity(aid: int, user=Depends(require_manager)):
    conn = get_db()
    conn.execute("UPDATE activities SET is_deleted=0, deleted_at=NULL WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return {"ok": True}

@router.delete("/activities/{aid}", status_code=204)
def delete_activity(aid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("UPDATE activities SET is_deleted=1, deleted_at=datetime('now') WHERE id=?", (aid,))
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
    raw = await file.read()
    # 임시 파일 경유 → DRM 해제된 바이트로 변환
    data = _read_drm_free(raw, file.filename)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO attachments(activity_id, filename, content_type, data) VALUES(?,?,?,?)",
        (aid, file.filename, file.content_type, data),
    )
    conn.commit()
    fid = cur.lastrowid
    conn.close()
    return {"id": fid, "filename": file.filename}


@router.get("/attachments/{fid}/public")
def download_attachment_public(fid: int):
    """인증 없는 공개 첨부파일 다운로드 — PPT 하이퍼링크 전용 (사내망 한정)."""
    conn = get_db()
    row = conn.execute("SELECT * FROM attachments WHERE id=?", (fid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다")
    return StreamingResponse(
        io.BytesIO(row["data"]),
        media_type=row["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": _content_disposition(row["filename"])},
    )


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
        headers={"Content-Disposition": _content_disposition(row["filename"])},
    )


@router.delete("/attachments/{fid}", status_code=204)
def delete_attachment(fid: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM attachments WHERE id=?", (fid,))
    conn.commit()
    conn.close()


# ── 첨부파일 관리 (관리자) ──────────────────────────────────────────────────────

@router.get("/attachments")
def list_all_attachments(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(require_manager),
):
    conn = get_db()
    q = """SELECT a.id, a.activity_id, a.filename, a.content_type, a.uploaded_at,
                  LENGTH(a.data) as size,
                  act.name as activity_name, act.created_at as activity_created_at,
                  t.name as task_name, g.name as group_name
           FROM attachments a
           JOIN activities act ON act.id=a.activity_id
           JOIN tasks t ON t.id=act.task_id
           JOIN groups g ON g.id=t.group_id
           WHERE 1=1"""
    params = []
    if from_date:
        q += " AND DATE(act.created_at) >= DATE(?)"
        params.append(from_date)
    if to_date:
        q += " AND DATE(act.created_at) <= DATE(?)"
        params.append(to_date)
    q += " ORDER BY a.uploaded_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/attachments/bulk-delete")
def bulk_delete_attachments(ids: list[int] = Body(...), user=Depends(require_manager)):
    conn = get_db()
    conn.executemany("DELETE FROM attachments WHERE id=?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return {"deleted": len(ids)}


@router.post("/attachments/vacuum")
def vacuum_db(user=Depends(require_manager)):
    conn = get_db()
    conn.execute("VACUUM")
    conn.close()
    return {"ok": True}


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
            "SELECT * FROM tasks WHERE group_id=? ORDER BY sort_order, name", (grp["id"],)
        ).fetchall()
        task_list = []
        for t in tasks:
            acts = conn.execute(
                f"""SELECT a.*, {ASSIGNEE_COLS}
                   FROM activities a
                   WHERE a.task_id=? AND a.week_label=?
                     AND (a.is_deleted IS NULL OR a.is_deleted=0) ORDER BY a.name""",
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


# ── PPT 내보내기 ──────────────────────────────────────────────────────────────

@router.get("/export-ppt")
def export_weekly_report_ppt(
    request: Request,
    week_label: str,
    group_id: Optional[int] = None,
    user=Depends(get_current_user),
):
    from weekly_report.pptx_gen import build_pptx
    tree = weekly_report(week_label=week_label, group_id=group_id, user=user)

    # 서버 base_url 자동 감지 (환경변수 API_URL 우선, 없으면 request.base_url)
    import os
    base_url = os.environ.get("API_URL", str(request.base_url).rstrip("/"))

    # 각 Activity의 첨부파일 목록 추가 (blob 불필요, id+filename만)
    conn = get_db()
    for grp in tree:
        for task in grp["tasks"]:
            for act in task["activities"]:
                rows = conn.execute(
                    "SELECT id, filename FROM attachments WHERE activity_id=?",
                    (act["id"],),
                ).fetchall()
                act["attachments"] = [
                    {"id": r["id"], "filename": r["filename"],
                     "url": f"{base_url}/app_wr/attachments/{r['id']}/public"}
                    for r in rows
                ]
    conn.close()

    pptx_bytes = build_pptx(week_label, tree)
    filename = f"weekly_report_{week_label}.pptx"
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": _content_disposition(filename)},
    )

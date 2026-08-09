"""
Admin DB Viewer — 테이블 스키마·데이터 조회, 행 삭제, SQL 직접 실행.
admin 역할만 접근 가능.
"""
import sqlite3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app_wr.core import get_db, get_current_user

router = APIRouter(prefix="/app_wr/admin", tags=["app_wr: Admin DB"])

# 시스템 테이블 제외 목록
_SYSTEM_TABLES = {"sqlite_sequence", "sqlite_stat1"}


def _require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin 권한이 필요합니다")
    return user


@router.get("/db/tables")
def list_tables(user=Depends(_require_admin)):
    """모든 테이블 목록 + 각 컬럼 스키마 반환."""
    conn = get_db()
    tables = [
        r[0] for r in
        conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        if r[0] not in _SYSTEM_TABLES
    ]
    result = []
    for tbl in tables:
        cols = conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()
        fks  = conn.execute(f"PRAGMA foreign_key_list('{tbl}')").fetchall()
        count = conn.execute(f"SELECT COUNT(*) FROM \"{tbl}\"").fetchone()[0]
        result.append({
            "name": tbl,
            "row_count": count,
            "columns": [
                {
                    "cid": c[0], "name": c[1], "type": c[2],
                    "notnull": bool(c[3]), "default": c[4], "pk": bool(c[5])
                }
                for c in cols
            ],
            "foreign_keys": [
                {"from": f[3], "table": f[2], "to": f[4]}
                for f in fks
            ],
        })
    conn.close()
    return result


@router.get("/db/tables/{table}/rows")
def get_rows(
    table: str,
    page: int = 1,
    per_page: int = 50,
    user=Depends(_require_admin),
):
    """테이블 데이터 페이지네이션 조회."""
    conn = get_db()
    # 테이블 존재 확인
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="테이블을 찾을 수 없습니다")

    total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    offset = (page - 1) * per_page
    cur = conn.execute(f'SELECT rowid, * FROM "{table}" LIMIT ? OFFSET ?', (per_page, offset))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    conn.close()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "columns": cols,
        "rows": [list(r) for r in rows],
    }


@router.delete("/db/tables/{table}/rows/{rowid}", status_code=204)
def delete_row(table: str, rowid: int, user=Depends(_require_admin)):
    """특정 행 삭제 (rowid 기준)."""
    conn = get_db()
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="테이블을 찾을 수 없습니다")
    conn.execute(f'DELETE FROM "{table}" WHERE rowid=?', (rowid,))
    conn.commit()
    conn.close()


class SqlReq(BaseModel):
    sql: str
    params: Optional[list] = []


@router.post("/db/sql")
def execute_sql(req: SqlReq, user=Depends(_require_admin)):
    """SQL 직접 실행. SELECT는 결과 반환, DML은 affected rows 반환."""
    sql = req.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL을 입력하세요")
    conn = get_db()
    try:
        cur = conn.execute(sql, req.params or [])
        is_select = sql.upper().lstrip().startswith("SELECT")
        if is_select:
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            conn.close()
            return {"type": "select", "columns": cols, "rows": [list(r) for r in rows], "count": len(rows)}
        else:
            conn.commit()
            affected = cur.rowcount
            conn.close()
            return {"type": "dml", "affected_rows": affected, "message": f"{affected}행 영향받음"}
    except sqlite3.Error as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

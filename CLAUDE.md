# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Server

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Default admin credentials: `admin` / `admin1234`

Environment variables:
- `SECRET_KEY` — JWT signing key (default: `weekly-report-secret-key-2024`, change in production)
- `WR_DB_PATH` — SQLite file path (default: `weekly_report/weekly_report.sqlite`)

## Architecture

This is a FastAPI + SQLite backend with a single-file HTML frontend (`report.html`).

**Entry point:** `main.py` creates the FastAPI app, then calls `register_weekly_report(app)` which runs `init_db()` and mounts all five routers under the `/wr/` prefix.

**Package layout:**
- `weekly_report/core.py` — DB connection (`get_db`), auth helpers (`get_current_user`, `require_manager`), `init_db()` with schema + migrations, all Pydantic request models
- `weekly_report/routers/auth.py` — login, me
- `weekly_report/routers/org.py` — teams, groups, lines
- `weekly_report/routers/users.py` — user CRUD
- `weekly_report/routers/tasks.py` — task CRUD + `/reorder` endpoint
- `weekly_report/routers/activities.py` — activities, attachments, weekly-report tree, PPT export
- `weekly_report/pptx_gen.py` — `build_pptx()` generates the PowerPoint from the report tree

**Frontend:** `report.html` is a self-contained SPA served statically. It reads the API base URL from a cookie (set on first login). No build step needed.

## Key Patterns

**Authentication:** Custom HS256 JWT (no PyJWT dependency). `create_token()` / `_decode_token()` in `core.py`. Tokens expire in 12 hours. `require_manager` guards write operations and requires role `admin`, `team_leader`, `group_leader`, or `line_leader`.

**DB access:** Every handler calls `get_db()` which opens a new `sqlite3.Connection` (with `row_factory = sqlite3.Row`) and closes it manually. No ORM or connection pool.

**DB migrations:** `init_db()` uses `ALTER TABLE ... ADD COLUMN` inside a `try/except` block to add columns to existing databases safely (e.g., `sort_order` on `tasks`, `activity_assignees` table).

**Multiple assignees:** Activities use an `activity_assignees` junction table. The `ASSIGNEE_COLS` constant in `activities.py` is a SQL fragment using `GROUP_CONCAT` that is embedded in every activity query to return `assignee_names` and `assignee_ids` in a single pass.

**DRM (Fasoo):** `_enable_drm()` in `core.py` loads `f_nxldr.dll` (Windows only; silently skipped elsewhere). DRM-encrypted file uploads are handled by writing to a `.cash/` temp directory, calling `_enable_drm()`, re-reading (OS decrypts transparently for authorized processes), then storing decrypted bytes in the DB. The SQLite DB file itself is also DRM-protected in production.

**PPT export:** `GET /wr/export-ppt?week_label=YYYY-Www` calls `build_pptx()` in `pptx_gen.py`. Each activity row gets dynamic height based on content line count (`_estimate_lines()`). File attachments are embedded as OLE objects (`add_ole_object()`) floating above table cells; row heights are calculated explicitly so OLE y-coordinates line up with each row.

**Korean filenames:** `Content-Disposition` headers use RFC 5987 encoding (`filename*=UTF-8''%encoded`) via `_content_disposition()` in `activities.py`. Temp file paths use UUID names (`_safe_tmp_name()`) to avoid OS path issues with non-ASCII characters.

**Route ordering:** In `activities.py`, the `/activities/copy-from-prev-week` route is registered before `/{aid}` to avoid FastAPI treating `copy-from-prev-week` as a path parameter. Same pattern in `tasks.py` with `/reorder` before `/{tid}`.

## DB Schema

```
teams           id, name
groups          id, name, team_id → teams
lines           id, name, group_id → groups
users           id, username, password(sha256), full_name, role, team_id, group_id, line_id
tasks           id, name, group_id → groups, sort_order, created_at
activities      id, task_id → tasks, name, week_label(e.g. 2024-W23), status, schedule, note, created_at, updated_at
activity_assignees  activity_id → activities, user_id → users  (PK composite)
attachments     id, activity_id → activities, filename, content_type, data(BLOB), uploaded_at
```

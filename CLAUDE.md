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

FastAPI + SQLite backend with a single-file HTML frontend (`report.html`).

**Entry point:** `main.py` → `register_weekly_report(app)` → `init_db()` + 5 routers mounted under `/wr/`.

**Package layout:**
- `weekly_report/core.py` — DB, auth, `init_db()`, Pydantic models
- `weekly_report/routers/auth.py` — login, me
- `weekly_report/routers/org.py` — teams, groups, lines
- `weekly_report/routers/users.py` — user CRUD
- `weekly_report/routers/tasks.py` — task CRUD + `/reorder`
- `weekly_report/routers/activities.py` — activities, attachments, weekly-report tree, PPT export
- `weekly_report/pptx_gen.py` — `build_pptx()` PowerPoint generation
- `report.html` — self-contained SPA (inline JS/CSS, no build step)

## Custom Skills

작업 유형에 맞는 스킬을 참조하세요 (`.claude/skills/`):

| 스킬 | 사용 시점 |
|---|---|
| `weekly-report-feature` | DB 마이그레이션·백엔드 API·프론트엔드를 함께 수정하는 신규 기능 추가 |
| `weekly-report-db` | DB 스키마·테이블 구조·제약 조건·마이그레이션 (스키마 정본) |
| `weekly-report-auth` | JWT, 로그인, 역할(RBAC), 세션 관련 수정 |
| `weekly-report-ui` | `report.html` UI 컴포넌트·레이아웃·렌더링 수정 |
| `weekly-report-pptx` | PPT 내보내기·OLE 첨부·행 높이·한글 처리 수정 |
| `session-start-hook` | Claude Code 웹 세션 의존성 자동 설치 훅 설정 |

---
name: weekly-report-feature
description: >
  FastAPI + SQLite + 단일 HTML SPA 구조의 주간보고 시스템(hans2048/API, report_wk 브랜치)에
  새 기능을 추가할 때 사용. DB 컬럼/테이블 추가, 백엔드 API, 프론트엔드 UI 변경이 함께
  필요한 작업에 특화됨.
---

# Weekly Report 기능 추가 스킬

## 프로젝트 개요

- **저장소**: `hans2048/API`, 브랜치: `report_wk`
- **스택**: FastAPI + SQLite (`sqlite3`) + 단일 파일 HTML SPA (`report.html`)
- **진입점**: `main.py` → `register_weekly_report(app)` → `init_db()` + 5개 라우터 등록
- **API 접두사**: 모든 엔드포인트는 `/wr/` 로 시작

## 핵심 파일

| 파일 | 역할 |
|---|---|
| `weekly_report/core.py` | DB 연결(`get_db`), 인증(`get_current_user`, `require_manager`), `init_db()` 스키마+마이그레이션, Pydantic 모델 |
| `weekly_report/routers/activities.py` | Activity CRUD, 첨부파일, 주간보고 트리, PPT 내보내기 |
| `weekly_report/routers/tasks.py` | Task CRUD + `/reorder` |
| `weekly_report/routers/org.py` | teams, groups, lines |
| `weekly_report/routers/users.py` | 사용자 CRUD |
| `report.html` | 단일 파일 SPA (인라인 JS/CSS) |

## 기능 추가 워크플로

### 1. DB 변경 사항 파악

- 새 컬럼이 필요하면 `core.py`의 `init_db()` 안 `CREATE TABLE IF NOT EXISTS` 블록에 추가
- **기존 DB 호환 마이그레이션** 필수: `try/except` 블록으로 `ALTER TABLE` 실행

```python
# core.py — init_db() 끝부분에 추가
try:
    conn.execute("ALTER TABLE 테이블명 ADD COLUMN 컬럼명 타입 DEFAULT 값")
    conn.commit()
except Exception:
    pass  # 이미 존재하는 경우 무시
```

- 새 테이블이 필요하면 `executescript()` 블록에 `CREATE TABLE IF NOT EXISTS`로 추가하고, 기존 DB에도 적용되도록 마이그레이션 블록도 추가:

```python
try:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 새테이블 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ...
        )
    """)
    conn.commit()
except Exception:
    pass
```

### 2. Pydantic 모델 추가/수정

`core.py` 하단의 모델 섹션에 추가:

```python
class NewReq(BaseModel):
    field1: str
    field2: Optional[int] = None
```

### 3. 라우터에 API 엔드포인트 추가

**라우트 순서 주의**: 정적 경로(`/activities/copy-from-prev-week`, `/activities/{aid}/history`, `/tasks/reorder`)는 반드시 파라미터 경로(`/{aid}`, `/{tid}`) **앞에** 등록해야 FastAPI가 올바르게 매칭함.

```python
# 정적 경로 먼저
@router.get("/activities/새기능")
def new_feature(...):
    ...

# 파라미터 경로 나중에
@router.get("/activities/{aid}")
def get_activity(aid: int, ...):
    ...
```

**DB 접근 패턴**:
```python
@router.get("/경로")
def handler(user=Depends(get_current_user)):  # 로그인 필요
    conn = get_db()
    rows = conn.execute("SELECT ...", (params,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.post("/경로", status_code=201)
def handler(req: SomeReq, user=Depends(require_manager)):  # 관리자 이상 필요
    conn = get_db()
    ...
    conn.commit()
    conn.close()
    return {"ok": True}
```

**권한 구분**:
- `Depends(get_current_user)` — 로그인한 모든 사용자
- `Depends(require_manager)` — `admin`, `team_leader`, `group_leader`, `line_leader`만

### 4. 프론트엔드 수정 (report.html)

`report.html`은 단일 파일 SPA. JS 함수와 HTML이 모두 인라인.

**API 호출 패턴**:
```javascript
// GET
const data = await api('GET', '/wr/경로');

// POST
await api('POST', '/wr/경로', { field1: value1 });

// PUT
await api('PUT', `/wr/경로/${id}`, body);

// DELETE
await api('DELETE', `/wr/경로/${id}`);
```

**모달 열기/닫기**:
```javascript
openModal('modal-아이디');
closeModal('modal-아이디');
```

**한글 파일명/텍스트 처리 주의**:
- `innerHTML`로 한글 포함 동적 콘텐츠 렌더링 시 XSS·인코딩 오류 가능성 → `createElement` + `textContent` 방식 사용
- 이벤트 핸들러에 한글 변수를 `onclick="fn('한글')"` 형태로 직접 삽입 금지 → `addEventListener` + 클로저 사용

**note 필드**: `contenteditable` div (`#act-note`)를 사용하는 리치텍스트. 저장 시 `innerHTML`, 출력 시 HTML 그대로 렌더링.

### 5. 주요 패턴 참고

**Activity 복수 담당자**: `activity_assignees` 조인 테이블 + `ASSIGNEE_COLS` SQL 상수 사용.
모든 Activity 쿼리에 `ASSIGNEE_COLS`를 SELECT에 포함시켜야 `assignee_names`, `assignee_ids` 반환됨.

**저장 이력**: Activity 등록/수정마다 `activity_history` 테이블에 `user_id`, `action(create|update)` 기록.

**Task 순서**: `sort_order` 컬럼으로 정렬. 모든 Task 쿼리에 `ORDER BY sort_order, name` 사용.

### 6. 커밋 & 푸시

```bash
git add <변경파일>
git commit -m "feat: 기능 설명"
git push -u origin report_wk
```

## DB 스키마 (현재)

```
teams              id, name
groups             id, name, team_id → teams
lines              id, name, group_id → groups
users              id, username, password(sha256), full_name, role, team_id, group_id, line_id
tasks              id, name, group_id → groups, sort_order, created_at
activities         id, task_id → tasks, name, week_label, status, schedule, note, created_at, updated_at
activity_assignees activity_id → activities, user_id → users  (PK composite)
activity_history   id, activity_id → activities, user_id → users, action(create|update), changed_at
attachments        id, activity_id → activities, filename, content_type, data(BLOB), uploaded_at
```

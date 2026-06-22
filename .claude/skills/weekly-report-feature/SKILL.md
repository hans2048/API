---
name: weekly-report-feature
description: >
  FastAPI + SQLite + 단일 HTML SPA 구조의 주간보고 시스템(hans2048/API, report_wk 브랜치)에
  새 기능을 추가할 때 사용. DB 컬럼/테이블 추가, 백엔드 API, 프론트엔드 UI 변경이 함께
  필요한 작업에 특화됨.
---

# Weekly Report 기능 추가 스킬

> 프로젝트 구조·실행 명령은 `CLAUDE.md` 참조. 이 스킬은 기능 추가 절차에 집중.

## 기능 추가 워크플로

### 1. DB 변경 사항 파악

DB 스키마·컬럼 추가/삭제·마이그레이션 규칙·SQLite 제약은 `weekly-report-db` 스킬 참조.
요약: `core.py`의 `init_db()`에서 `CREATE TABLE IF NOT EXISTS` + `try/except ALTER TABLE`
마이그레이션 패턴으로 기존 DB와 호환되게 변경.

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
UI 컴포넌트(버튼, 카드, 모달, 테이블, 한글 렌더링 주의사항)는 `weekly-report-ui` 스킬 참조.

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

## DB 스키마

전체 스키마·제약·마이그레이션 규칙은 `weekly-report-db` 스킬 참조 (정본).

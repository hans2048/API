# Weekly Report System — 통합 가이드

## 1. 디렉토리 구조

```
your_project/                       ← API Gateway 루트
├── main.py                         ← 게이트웨이 진입점 (2줄만 추가)
├── requirements.txt
│
└── app_wr/                         ← 주간 보고 서비스 패키지 (통째로 복사)
    ├── __init__.py                 ← 단일 router 노출 + init_db() 호출
    ├── core.py                     ← DB 초기화 · 인증 · Pydantic 모델
    ├── pptx_gen.py                 ← PPT 내보내기 생성
    ├── templates/report.html       ← 프론트엔드 SPA (Jinja2 서빙)
    └── routers/
        ├── __init__.py
        ├── pages.py                ← /app_wr (HTML 페이지)
        ├── auth.py                 ← /app_wr/auth/login, /app_wr/auth/me
        ├── org.py                  ← /app_wr/teams, /app_wr/groups
        ├── users.py                ← /app_wr/users
        ├── tasks.py                ← /app_wr/tasks
        └── activities.py          ← /app_wr/activities, /app_wr/weekly-report, /app_wr/attachments
```

---

## 2. 게이트웨이 main.py에 추가할 코드 (단 2줄)

```python
# main.py 하단에 아래 두 줄 추가 (ADDING_NEW_SERVICE.md 규약)
from app_wr import router as app_wr_router
app.include_router(app_wr_router)
```

`app_wr/__init__.py`가 로드 시 `init_db()`를 호출하여  
**SQLite DB(`app_wr/app_wr.sqlite`)를 자동 생성**하고 모든 라우터를 단일 router로 등록합니다.

---

## 3. 설치 / 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행 (기존 명령과 동일)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 의존성 (requirements.txt)
```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pyjwt>=2.8.0
python-multipart>=0.0.9
```

---

## 4. 프론트엔드 사용법

`report.html` 파일을 브라우저에서 직접 열거나 정적 파일로 서빙합니다.

1. **최초 실행 시** → API 서버 주소 입력 (`http://서버IP:8000`)  
   입력한 주소는 **쿠키에 자동 저장**되어 다음 접속 시 자동 적용됩니다.
2. **기본 계정**: `admin` / `admin1234`

---

## 5. API 엔드포인트 목록

모든 엔드포인트는 `/app_wr` 접두사를 사용합니다 (기존 API와 충돌 방지).

| 메서드 | 경로 | 설명 | 권한 |
|--------|------|------|------|
| POST | `/app_wr/auth/login` | 로그인 (JWT 발급) | 공개 |
| GET | `/app_wr/auth/me` | 내 정보 조회 | 로그인 |
| GET/POST | `/app_wr/teams` | 팀 목록 / 추가 | 조회:전체, 수정:관리자 |
| PUT/DELETE | `/app_wr/teams/{id}` | 팀 수정 / 삭제 | 관리자 |
| GET/POST | `/app_wr/groups` | 그룹 목록 / 추가 | 조회:전체, 수정:관리자 |
| PUT/DELETE | `/app_wr/groups/{id}` | 그룹 수정 / 삭제 | 관리자 |
| GET/POST | `/app_wr/users` | 사용자 목록 / 추가 | 관리자 |
| PUT/DELETE | `/app_wr/users/{id}` | 사용자 수정 / 삭제 | 관리자 |
| GET/POST | `/app_wr/tasks` | 업무 목록 / 추가 | 조회:전체, 수정:관리자 |
| PUT/DELETE | `/app_wr/tasks/{id}` | 업무 수정 / 삭제 | 관리자 |
| GET/POST | `/app_wr/activities` | Activity 조회 / 추가 | 로그인 |
| PUT/DELETE | `/app_wr/activities/{id}` | Activity 수정 / 삭제 | 로그인 |
| GET | `/app_wr/activities/copy-from-prev-week` | 전주 Activity 불러오기 | 로그인 |
| GET/POST | `/app_wr/activities/{id}/attachments` | 첨부파일 목록 / 업로드 | 로그인 |
| GET/DELETE | `/app_wr/attachments/{id}` | 첨부파일 다운로드 / 삭제 | 로그인 |
| GET | `/app_wr/weekly-report` | 주간 보고 트리 조회 | 로그인 |

---

## 6. 역할(Role) 체계

| 역할 | 코드 | 권한 |
|------|------|------|
| 시스템 Admin | `admin` | 전체 |
| 팀장 | `team_leader` | 조직·업무 등록/수정/삭제 |
| 그룹장 | `group_leader` | 조직·업무 등록/수정/삭제 |
| 라인장 | `line_leader` | 조직·업무 등록/수정/삭제 |

> Activity 입력/수정은 **모든 로그인 사용자**가 가능합니다.

---

## 7. DB 스키마 (SQLite: app_wr/app_wr.sqlite)

```
teams        id, name
groups       id, name, team_id → teams
users        id, username, password(sha256), full_name, role, team_id, group_id
tasks        id, name, group_id → groups, sort_order, created_at
activities   id, task_id → tasks, name, week_label(예:2024-W23),
             status, schedule, assignee_id → users, note, created_at, updated_at
attachments  id, activity_id → activities, filename, content_type, data(BLOB), uploaded_at
```

---

## 8. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SECRET_KEY` | `weekly-report-secret-key-2024` | JWT 서명 키 (운영 시 반드시 변경) |
| `WR_DB_PATH` | `app_wr/app_wr.sqlite` | SQLite 파일 경로 |

```bash
# 운영 환경 예시
export SECRET_KEY="your-strong-random-key"
export WR_DB_PATH="/data/weekly_report.sqlite"
```

---

## 9. 기존 서버와의 충돌 방지 포인트

- 모든 URL은 `/app_wr/` 접두사 사용 → 기존 경로와 충돌 없음
- DB는 별도 파일(`app_wr/app_wr.sqlite`) → 기존 DB 영향 없음
- JWT `SECRET_KEY`는 환경 변수로 분리 가능
- `init_db()`는 `CREATE TABLE IF NOT EXISTS` 사용 → 중복 실행 안전

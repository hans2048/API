---
name: weekly-report-auth
description: >
  주간보고 시스템(hans2048/API)의 인증·로그인 관련 기능을 수정할 때 사용.
  JWT 발급/검증, 비밀번호 처리, 회원가입, 비밀번호 변경, 로그인 화면 UI,
  세션 유지(쿠키/localStorage), 역할 기반 접근제어(RBAC) 작업에 특화됨.
---

# Weekly Report 인증·로그인 스킬

## 백엔드 구조

**라우터**: `weekly_report/routers/auth.py` — prefix `/wr/auth`

| 엔드포인트 | 인증 | 설명 |
|---|---|---|
| `GET  /wr/auth/health` | 불필요 | 서버·DB 상태 확인 |
| `POST /wr/auth/login` | 불필요 | 로그인 → JWT 반환 |
| `GET  /wr/auth/me` | 필요 | 내 정보 조회 |

회원가입·비밀번호 변경은 `/wr/users` 라우터에서 처리 (`users.py`).

---

## JWT 구현 (`core.py`)

**PyJWT 미사용** — 직접 구현한 HS256 JWT.

```python
SECRET_KEY = os.environ.get("SECRET_KEY", "weekly-report-secret-key-2024")
TOKEN_EXPIRE_HOURS = 12  # 토큰 유효 시간

def create_token(user_id: int, role: str) -> str:
    """header.payload.sig 형태의 JWT 생성"""

def _decode_token(token: str) -> dict:
    """서명 검증 + 만료 확인. 실패 시 ValueError 발생."""
```

**비밀번호**: `hashlib.sha256(pw.encode()).hexdigest()` — 솔트 없는 SHA-256.  
변경 시 `hash_pw()` 함수 사용 (`core.py`).

**토큰 페이로드 구조**:
```json
{ "sub": "사용자id(str)", "role": "역할", "exp": 유닉스타임스탬프 }
```

---

## 역할(Role) 체계

| role 값 | 한국어 | 권한 |
|---|---|---|
| `admin` | 시스템Admin | 전체 |
| `team_leader` | 팀장 | 관리자급 (업무·조직 수정) |
| `group_leader` | 그룹장 | 관리자급 |
| `line_leader` | 라인장 | 관리자급 |
| `member` | 팀원/그룹원 | Activity 입력/수정만 |

> `member` 라벨은 **소속에 따라 동적 표시**: 팀 소속이면 "팀원", 그룹 소속이면 "그룹원".
> 프론트엔드 `roleLabel(role, user)`가 `user.team_id`/`user.group_id`로 판별.

### 소속(membership) 규칙

`admin`을 **제외한 모든 사용자**는 **팀(`team_id`) 또는 그룹(`group_id`) 중 정확히 하나**에
소속해야 함 (상호배타). 둘 다 비었거나 둘 다 설정되면 거부.

- 백엔드 검증: `users.py`의 `_validate_membership(role, team_id, group_id)` —
  `register`/`create`/`update`(관리자 전체수정 시)에서 호출.
- `update`는 관리자가 역할을 포함해 수정할 때 `team_id`/`group_id`를 **한 쌍으로 기록**
  (한쪽 null)하여 상호배타 유지.
- 프론트엔드: 팀·그룹 select가 상호배타(`onchange`로 다른 쪽 비움) + 저장 전 검증.

**백엔드 가드**:
```python
Depends(get_current_user)   # 로그인한 모든 사용자
Depends(require_manager)    # admin, team_leader, group_leader, line_leader
```

**프론트엔드 UI 제어** (`startApp()` 내):
```javascript
// admin만 보이는 메뉴
document.querySelectorAll('.admin-only').forEach(el => {
  if (ME.role !== 'admin') el.classList.add('hidden');
});
// 관리자급(팀장 이상)만 보이는 메뉴
document.querySelectorAll('.manager-only').forEach(el => {
  if (!['admin','team_leader','group_leader','line_leader'].includes(ME.role))
    el.classList.add('hidden');
});
```

---

## 프론트엔드 인증 흐름 (`report.html`)

### 전역 변수
```javascript
let API = '';    // API 서버 주소 (예: http://192.168.0.10:8000)
let TOKEN = '';  // 현재 Bearer 토큰
let ME = null;   // 로그인한 사용자 객체
```

### 세션 저장 방식
`localStorage` 우선, 없으면 쿠키 fallback:
```javascript
setCookie('api_url', url, 365);  // API 서버 주소 (1년)
setCookie('token', token, 1);    // JWT 토큰 (1일)
getCookie('name');               // localStorage → 쿠키 순으로 조회
```

### 초기화 흐름 (`window.onload`)
```
저장된 api_url + token 있음?
  → GET /wr/auth/me 호출
    → 성공: ME = 사용자 정보, startApp() 실행
    → 실패(토큰 만료 등): TOKEN 초기화, 로그인 화면 표시
```

### 로그인 (`doLogin()`)
```
1. api_url, username, password 입력 확인
2. POST /wr/auth/login → { token, user } 반환
3. TOKEN = token; ME = user
4. setCookie('api_url', ...) + setCookie('token', ..., 1)
5. startApp() → 앱 화면 전환
```

### 로그아웃 (`doLogout()`)
```javascript
TOKEN = ''; ME = null;
setCookie('token', '', -1);  // 쿠키 만료
// 로그인 화면으로 전환
```

### API 호출 공통 함수

`api(method, path, body)` — `report.html` 전역 함수. Bearer 토큰 자동 첨부.  
사용 패턴은 `weekly-report-ui` 스킬 참조.

---

## 로그인 화면 탭 구조

3개 탭: **로그인** / **회원가입** / **비밀번호 변경**

| 탭 id | 패널 id | 핸들러 함수 |
|---|---|---|
| `panel-login` | - | `doLogin()` |
| `panel-register` | - | `doRegister()` |
| `panel-chgpw` | - | `doChgPw()` (users.py) |

**회원가입 시 조직 선택**: 팀 → 그룹 → 라인 연동 드롭다운.  
`loadRegOrgData()` → `onRegTeamChange()` → `onRegGroupChange()` 순으로 필터링.  
인증 없이 `GET /wr/teams`, `/wr/groups`, `/wr/lines` 직접 호출 (공개 엔드포인트).

---

## 수정 시 주의사항

1. **토큰 만료 응답**: `_decode_token()`이 `ValueError("expired")` 발생 → `get_current_user()`에서 HTTP 401 반환. 프론트엔드는 `api()` 함수에서 `throw new Error(data.detail)`로 처리.

2. **비밀번호 변경**: `users.py`의 `PUT /wr/users/{id}` 엔드포인트 사용. `UserUpdateReq.password` 필드가 있으면 `hash_pw()` 적용 후 저장.

3. **기본 admin 계정**: `init_db()`에서 `INSERT OR IGNORE`로 생성. 비밀번호 `admin1234`.  
   운영 환경에서는 반드시 변경 필요.

4. **SECRET_KEY**: 환경변수 `SECRET_KEY` 미설정 시 기본값 사용 — 운영 환경에서 반드시 변경.

5. **CORS**: `main.py`에서 `allow_origins=["*"]`로 전체 허용 중. 운영 시 도메인 제한 권장.

6. **새 역할 추가 시**: `users` 테이블의 `CHECK(role IN (...))` 제약이 SQLite에서는 ALTER TABLE로 변경 불가. 기존 DB 호환을 위해 제약 우회가 필요하면 `init_db()`의 `_dummy` 컬럼 마이그레이션 패턴 참고.

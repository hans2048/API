# 신규 서비스(app_x) 개발 가이드

이 문서는 본 API Gateway 구조에 **새로운 독립 서비스**(예: `app_2`, `app_blog` 등)를
추가할 때 반드시 따라야 할 규약과 절차를 정리한 참조 문서입니다.
바이브 코딩(Claude) 으로 새 앱을 만들 때 가장 먼저 이 문서를 참조하세요.

> ⚠️ **유지보수 의무**: 아키텍처/인터페이스/규약/디렉토리 구조가 바뀌면
> 이 문서와 `CLAUDE.md`를 **즉시** 함께 갱신합니다. (코드와 문서가 어긋나면 안 됩니다.)

---

## 1. 핵심 원칙 (가장 중요)

1. **완전 격리(Isolation)**: 새 앱은 기존 코드를 절대 건드리지 않습니다.
   모든 코드/DB/템플릿은 `app_[name]/` 패키지 **안에서만** 구성합니다.
2. **게이트웨이 불변(main.py)**: `main.py`는 라우터를 마운트하는 한 줄만 추가합니다.
   비즈니스 로직을 `main.py`에 넣지 않습니다.
3. **단일 진입점(Single router)**: 각 앱 패키지의 `__init__.py`는
   내부 라우터를 모두 묶은 **하나의 `router`(APIRouter)** 만 외부에 노출합니다.
   게이트웨이는 이 `router` 하나만 마운트합니다.
4. **URL 네임스페이스**: 모든 경로는 `/app_[name]/...` 접두사로 시작해
   다른 앱과 충돌하지 않게 합니다.
5. **DB 격리**: 앱 전용 DB 파일(`app_[name]/xxx.db`)을 사용하고
   다른 앱과 테이블/세션을 공유하지 않습니다. (`.gitignore`에 `*.db`, `*.db-wal`, `*.db-shm` 포함됨)
6. **DRM 대응**: 사내 DRM 적용 PC와 미적용 PC 양쪽에서 동작해야 합니다.
   보호 파일(DB/템플릿) 접근 전에 공용 `drm.enable_drm()`을 호출합니다. (8장 참조)
7. **DRM 파일은 app_drm 경유**: 엑셀/CSV/JPG/PDF 등 사용자가 올린 DRM 보호 파일을
   다룰 때는 직접 처리하지 말고 **`app_drm` 서비스를 경유**해 DRM 해제본을 받아 사용합니다. (9장 참조)

---

## 2. 표준 디렉토리 구조

`app_1`이 레퍼런스 구현입니다. 신규 앱은 동일한 구조를 복제하세요.

```text
app_[name]/
├── __init__.py          # 내부 라우터를 묶은 단일 `router` 노출 + init_db() 호출
├── database.py          # 격리된 engine / SessionLocal / Base / get_db / init_db
├── models.py            # SQLAlchemy 모델 (테이블 정의)
├── schemas.py           # Pydantic 스키마 (요청/응답 검증)
├── crud.py              # DB 액세스 로직 (라우터를 가볍게 유지)
├── routers/
│   ├── __init__.py      # (빈 파일, 패키지 표시용)
│   ├── tasks.py         # REST API (JSON) 라우터  ← 도메인에 맞게 이름 변경
│   └── pages.py         # HTML 페이지(SSR) 라우터  ← HTML이 필요 없으면 생략 가능
└── templates/
    └── home.html        # 전용 템플릿 (HTML 앱일 때만)
```

> HTML 화면이 필요 없는 **순수 JSON API** 앱이면 `routers/pages.py`와
> `templates/`는 생략하고, `__init__.py`에서 API 라우터만 include 하면 됩니다.

---

## 3. 추가 절차 체크리스트

1. `app_[name]/` 패키지 디렉토리와 위 파일들을 생성한다.
2. `database.py`에서 **앱 전용 DB 경로**를 설정한다. (다른 앱과 파일명 충돌 금지)
3. `models.py`에 테이블, `schemas.py`에 입출력 스키마를 정의한다.
4. `crud.py`에 DB 조작 로직을 작성한다. (라우터는 얇게)
5. `routers/`에 라우터를 작성하되 **반드시 `prefix="/app_[name]/..."`** 를 지정한다.
6. `__init__.py`에서 `init_db()` 호출 후 내부 라우터를 묶어 `router`로 노출한다.
7. `main.py`에 **두 줄**만 추가한다:
   ```python
   from app_[name] import router as app_[name]_router
   app.include_router(app_[name]_router)
   ```
8. 필요한 신규 의존성이 있으면 `requirements.txt`에 추가한다.
9. `TestClient`로 동작을 검증한다. (아래 6장)
10. `CLAUDE.md`의 "현재 구현 현황"과 본 문서를 갱신한다.

---

## 4. 코드 스켈레톤 (복사해서 시작)

### `database.py`
```python
import os
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from drm import enable_drm   # 공용 DRM 모듈 (8장 참조)

# ⚠️ Path(__file__).resolve() 는 쓰지 말 것. Windows에서 매핑 드라이브(Z:\)/정션을
#    UNC(\\server\share)로 바꿔 SQLite WAL 이 'disk I/O error' 를 내는 원인이 됨.
DB_PATH = os.environ.get(
    "APPNAME_DB_PATH", os.path.join(os.path.dirname(__file__), "app_name.db")
)   # ← 앱마다 고유 파일명 / 고유 환경변수명
SQLALCHEMY_DATABASE_URL = "sqlite://"   # creator 사용 시 경로는 무시됨(다이얼렉트만)

def _connect():
    """DBAPI 연결 생성자. DRM 적용 PC를 위해 연결 직전 DRM을 활성화한다."""
    enable_drm()
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    # WAL 은 동시성에 유리하나 일부 네트워크/보호 경로에서 실패할 수 있어
    # 실패 시 안전 모드(TRUNCATE)로 폴백한다.
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode = TRUNCATE")
    return conn

# creator 로 연결 생성을 직접 제어 (DRM 활성화 + PRAGMA 적용)
engine = create_engine(SQLALCHEMY_DATABASE_URL, creator=_connect)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app_name import models  # noqa: F401  (테이블 등록)
    Base.metadata.create_all(bind=engine)
```

### `__init__.py`
```python
from fastapi import APIRouter
from app_name.database import init_db
from app_name.routers import items   # 필요한 라우터들

init_db()                            # 앱 로드 시 전용 테이블 생성

router = APIRouter()
router.include_router(items.router)
# router.include_router(pages.router)  # HTML 페이지가 있으면 추가
__all__ = ["router"]
```

### `routers/items.py` (REST API)
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app_name.database import get_db

router = APIRouter(prefix="/app_name/items", tags=["app_name: items (API)"])

@router.get("")
def list_items(db: Session = Depends(get_db)):
    ...
```

### `routers/pages.py` (HTML / SSR) — HTML 앱일 때만
```python
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app_name.database import get_db

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
router = APIRouter(prefix="/app_name", tags=["app_name: pages (HTML)"])

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # ⚠️ starlette 최신 시그니처: 첫 인자는 request 여야 함
    return templates.TemplateResponse(request, "home.html", {"items": []})
```

---

## 5. 규약 및 주의사항 (Gotchas)

- **URL 접두사**: API는 `/app_name/<resource>`, 페이지는 `/app_name/` 형태로 통일.
- **TemplateResponse 시그니처**: 반드시 `TemplateResponse(request, "name.html", {...})`.
  구 시그니처 `TemplateResponse("name.html", {"request": request, ...})`는
  최신 starlette에서 오류(`unhashable type: 'dict'`)를 일으킵니다.
- **폼 처리(PRG)**: HTML 폼 제출은 처리 후 `RedirectResponse(..., status_code=303)`로
  홈에 리다이렉트(Post/Redirect/Get)합니다. `Form` 사용 시 `python-multipart` 필요.
- **부분 수정(PATCH)**: 수정 스키마는 `Optional` 필드로 두고
  `data.model_dump(exclude_unset=True)`로 전달된 필드만 갱신합니다.
- **응답 모델 ORM 변환**: 응답 Pydantic 스키마에 `model_config = {"from_attributes": True}`.
- **DB 파일명 중복 금지**: 앱마다 `app_name.db`처럼 고유한 이름을 사용합니다.
- **DB 경로에 `Path.resolve()` 금지**: `database.py`의 DB 파일 경로는
  `os.path.join(os.path.dirname(__file__), ...)`로 잡습니다. Windows에서 `resolve()`는
  매핑 네트워크 드라이브/정션을 UNC 경로로 바꿔 SQLite WAL 이 `disk I/O error`를 냅니다.
  (템플릿 디렉토리 경로의 `resolve()`는 파일을 mmap 하지 않으므로 무관합니다.)
- **연결 수명(NullPool)**: 엔진은 `poolclass=NullPool`로 매 작업마다 연결을 새로
  만들고 닫습니다(검증된 raw-sqlite3 패턴과 동일). 풀에 오래 남은 연결로 인한 잠금 문제를 피합니다.
- **`disk I/O error` 가 나면**: 보통 경로(네트워크/UNC) 문제이거나 서버 PC의 일시적 문제입니다.
  경로 문제면 `APP1_DB_PATH`(앱별 고유 환경변수)로 로컬 경로를 지정하고,
  일시적 문제로 의심되면 서버를 재시작해 확인하세요.

---

## 6. 검증 방법

별도 서버 없이 `TestClient`로 빠르게 확인합니다.

```python
from fastapi.testclient import TestClient
from main import app

c = TestClient(app)
assert c.get("/").status_code == 200
assert c.get("/app_name/items").status_code == 200
# 생성/조회/수정/삭제 등 주요 흐름을 점검
```

실제 서버 실행:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Swagger 문서로 새 앱 엔드포인트 확인: http://localhost:8000/docs
```

---

## 8. 사내 DRM 대응 (Fasoo)

DRM이 적용된 PC에서는 보호된 파일(SQLite DB, 템플릿 등)에 접근하기 전에
프로세스를 DRM 인가 상태로 만들어야 합니다. 이를 위해 루트에 공용 모듈
`drm.py` 의 `enable_drm()` 을 사용합니다.

```python
# drm.py (공용 — 새로 만들 필요 없음, 그대로 import)
from ctypes import CDLL

def enable_drm():
    try:
        fasoo = CDLL("c:/windows/system32/f_nxldr.dll")
        return fasoo.EnableDRM()
    except OSError:
        return None   # DRM 미적용 PC / 비-Windows → 무시 (양쪽 환경 호환)
```

**호출 위치(2곳)**
1. **프로세스 시작 시 1회** — `main.py` 최상단에서 `enable_drm()` 호출.
   템플릿 등 모든 보호 파일 접근을 대비. **app_x import 보다 먼저** 호출해야 함
   (app import 시 `init_db()`가 DB를 열기 때문).
2. **DB 연결 생성마다** — 위 `database.py` 의 `_connect()` 생성자 안에서 호출.

**원칙**
- 새 앱은 `drm.py` 를 새로 만들 필요 없이 `from drm import enable_drm` 로 재사용.
- DRM 미적용 PC에서는 `enable_drm()` 이 `None` 을 반환하며 아무 동작도 하지 않으므로,
  **DRM PC / 비-DRM PC 모두에서 동일한 코드로** 동작합니다.
- DRM 로직(DLL 경로 등)이 바뀌면 `drm.py` 한 곳만 수정하면 전체 앱에 반영됩니다.

---

## 9. DRM 파일 사용 — `app_drm` 경유

업로드되는 **엑셀/CSV/JPG/PDF 등 DRM 보호 파일**은 프론트엔드(HTML)·백엔드(Python)
어디서든 그대로는 열 수 없습니다. 반드시 **`app_drm` 서비스를 경유**해 DRM이 해제된
사본을 받아 사용합니다. (DB의 DRM은 `database.py`에서 처리하지만, **DB 외 일반 파일**은
이 `app_drm` 을 통합니다.)

### 9.1 동작 원리
업로드 → 임시폴더 저장 → `enable_drm()` → 다시 로드(복호화) → **DRM 해제본 생성**.
DRM 미적용 PC에서는 원본이 그대로 복사되어 동일하게 동작합니다.

### 9.2 전송 방식 (Transport / 요청·응답 포맷)
파일을 주고받는 방식은 다음 규약을 따릅니다.

**① 업로드 (Client → Server)**
- 전송 형식: **`multipart/form-data`** (HTML `<form enctype="multipart/form-data">` 또는 JS `FormData`)
- 필드명: **`file`** (단일 파일). 서버는 FastAPI `UploadFile = File(...)` 로 수신.
- 바이너리 원본을 그대로 전송(base64 등 인코딩 안 함).

**② 메타데이터 응답 (Server → Client, JSON)**
- `POST /app_drm/files`: `application/json`, **201**, 본문 `{id, filename, content_type, size, download_url}`
- `POST /app_drm/upload`(HTML 폼): **303** 리다이렉트(PRG) → `/app_drm/`

**③ 파일 본문 다운로드 (Server → Client, binary)**
- `GET /app_drm/files/{id}`: **`FileResponse` 바이너리 스트림**.
- 헤더: `Content-Type` 은 업로드 시 보존한 MIME(예: `application/pdf`),
  `Content-Disposition: attachment; filename="원본파일명"`.
- 이미지·PDF는 브라우저에서 `<img src>`, `<iframe src>` 로 바로 미리보기 가능.

**④ 백엔드 간 사용(import) — 네트워크 전송 없음**
- 같은 프로세스 내 `strip_drm_*()` 호출은 전송 없이 **로컬 파일 경로(`Path`)** 를 주고받음.

```javascript
// 프론트엔드 업로드 예시 (fetch + FormData)
const fd = new FormData();
fd.append("file", fileInput.files[0]);          // 필드명은 반드시 "file"
const res  = await fetch("/app_drm/files", { method: "POST", body: fd });
const meta = await res.json();                  // {id, download_url, content_type, ...}
imgEl.src  = meta.download_url;                  // 다운로드/미리보기
```

### 9.3 백엔드(Python)에서 사용 — 직접 import (권장)
다른 서비스의 라우터에서 `app_drm` 헬퍼를 import 해 DRM 해제본 경로를 얻습니다.

```python
from app_drm import strip_drm_bytes, strip_drm_path, cleanup

# (a) 업로드 바이트를 DRM 해제본으로
@router.post("/app_name/import")
async def import_excel(file: UploadFile = File(...)):
    free_path = strip_drm_bytes(await file.read(), file.filename)  # DRM 해제본 경로
    try:
        import pandas as pd
        df = pd.read_excel(free_path)        # DRM 해제본이라 정상 로드
        ...
    finally:
        cleanup(free_path)                   # 사용 후 임시본 정리

# (b) 디스크의 보호 파일 경로를 해제
free_path = strip_drm_path("/some/protected.pdf")
```

- `strip_drm_bytes(data, filename) -> Path` : 업로드 바이트 → DRM 해제본 경로
- `strip_drm_path(src_path) -> Path` : 디스크 경로 → DRM 해제본 경로
- `cleanup(path)` : 사용이 끝난 해제본 임시 파일 삭제

### 9.4 프론트엔드(HTML)에서 사용 — HTTP 경유
- `POST /app_drm/files` (multipart `file`) → `{id, filename, content_type, size, download_url}`
- `GET  /app_drm/files/{id}` → DRM 해제본 다운로드/미리보기 (이미지·PDF 등 `<img>`, `<iframe>` 에 사용)
- `GET  /app_drm/files/{id}/preview` → 엑셀(.xlsx/.xlsm/.xls) 첫 시트 내용 JSON `{sheet, rows}` (해제 확인용)
- `GET  /app_drm/files` → 처리된 파일 목록
- `GET  /app_drm/` → 업로드 화면(HTML). 엑셀 업로드 시 재로드본의 첫 시트를 그리드로 표시(정상 표시 = DRM 해제 성공)

### 9.5 주의사항
- DRM 해제본은 임시 폴더(`app_drm/_tmp/`, 환경변수 `DRM_TMP_DIR` 로 변경)에 생성되며
  `.gitignore` 처리됩니다. 민감 데이터는 사용 후 `cleanup()` 으로 삭제하세요.
- 새 파일 타입 추가나 동작 변경 시 `app_drm/service.py` 한 곳만 수정하면 전체에 반영됩니다.

---

## 10. 현재 등록된 서비스

| 앱       | 도메인          | 데이터            | URL 접두사   | 비고                          |
|----------|-----------------|-------------------|--------------|-------------------------------|
| app_1    | Todo(할 일)     | SQLite+SQLAlchemy | `/app_1`     | REST API + HTML(SSR) 레퍼런스 |
| app_drm  | DRM 파일 해제   | 임시 파일(무DB)   | `/app_drm`   | 다른 서비스가 경유하는 파일 DRM 해제 유틸 |
| app_wr   | 주간보고        | SQLite(raw)       | `/app_wr`    | 주간보고 서비스. API `/app_wr/...`, 페이지 `/app_wr`. PPT 내보내기 포함 |

> 새 앱을 추가하면 이 표에 한 줄을 추가하세요.

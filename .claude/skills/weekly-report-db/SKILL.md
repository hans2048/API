---
name: weekly-report-db
description: >
  주간보고 시스템(hans2048/API)의 DB 스키마·테이블 구조·제약 조건·마이그레이션을
  다룰 때 사용. 전체 스키마 정의(single source of truth), 컬럼 추가/삭제,
  테이블 삭제, SQLite 제약(CHECK, FK) 관련 작업에 특화됨.
---

# Weekly Report DB 스키마 스킬

SQLite 단일 파일 DB. 스키마는 `app_wr/core.py`의 `init_db()`에서 정의·마이그레이션됨.
DB 경로는 환경변수 `WR_DB_PATH` (기본 `app_wr/weekly_report.sqlite`).

> 이 문서가 DB 스키마의 **정본(single source of truth)**. 다른 스킬·CLAUDE.md는 여기를 참조.

## 전체 스키마

```
teams              id PK, name UNIQUE NOT NULL

groups             id PK, name NOT NULL,
                   team_id → teams(id) CASCADE

users              id PK, username UNIQUE NOT NULL, password(sha256) NOT NULL,
                   full_name NOT NULL,
                   role NOT NULL CHECK(admin|team_leader|group_leader|line_leader|member),
                   team_id → teams(id), group_id → groups(id)

tasks              id PK, name NOT NULL,
                   group_id → groups(id) CASCADE,
                   sort_order INTEGER DEFAULT 0, created_at

activities         id PK, task_id → tasks(id) CASCADE, name NOT NULL,
                   week_label NOT NULL (예: 2024-W23),
                   status, schedule, assignee_id → users(id) [레거시·미사용],
                   note, created_at, updated_at

activity_assignees activity_id → activities(id) CASCADE,
                   user_id → users(id) CASCADE,
                   PRIMARY KEY(activity_id, user_id)

activity_history   id PK, activity_id → activities(id) CASCADE,
                   user_id → users(id),
                   action NOT NULL CHECK(create|update), changed_at

attachments        id PK, activity_id → activities(id) CASCADE,
                   filename NOT NULL, content_type, data(BLOB) NOT NULL, uploaded_at
```

## 역할(role) 체계

`users.role` CHECK 제약: `admin`, `team_leader`, `group_leader`, `line_leader`, `member`.

> `line_leader`(라인장) 역할은 유지되지만, 조직 단위 `lines` 테이블은 제거됨.
> 역할의 권한 동작은 `weekly-report-auth` 스킬 참조.

## 주요 설계 포인트

- **복수 담당자**: Activity의 담당자는 `activity_assignees` 조인 테이블로 관리.
  `activities.assignee_id`는 구버전 단일 담당자 컬럼으로 남아 있으나 현재 미사용
  (마이그레이션 시 `activity_assignees`로 이전됨).
- **저장 이력**: `activity_history`가 Activity 생성/수정 이력을 기록.
- **업무 정렬**: `tasks.sort_order`로 표시 순서 제어 (드래그 앤 드롭).
- **첨부파일**: BLOB로 DB 내부 저장 (외부 파일시스템 미사용).
- **CASCADE 삭제**: 상위 행 삭제 시 하위 행 자동 삭제 (teams→groups→tasks→activities→attachments).

## 마이그레이션 규칙

`init_db()`는 항상 실행되며, 기존 DB와 호환되어야 함.

### 컬럼 추가
```python
try:
    conn.execute("ALTER TABLE 테이블 ADD COLUMN 컬럼 타입 DEFAULT 값")
    conn.commit()
except Exception:
    pass  # 이미 존재 시 무시
```

### 컬럼 삭제 (SQLite 3.35+)
```python
try:
    conn.execute("ALTER TABLE 테이블 DROP COLUMN 컬럼")
    conn.commit()
except Exception:
    pass  # 이미 없을 시 무시
```

### 테이블 삭제
```python
try:
    conn.execute("DROP TABLE IF EXISTS 테이블")
    conn.commit()
except Exception:
    pass
```

### 새 테이블 추가
`executescript()` 블록의 `CREATE TABLE IF NOT EXISTS`에 추가하고,
기존 DB에도 반영되도록 마이그레이션 블록에도 `CREATE TABLE IF NOT EXISTS` 중복 작성.

## SQLite 제약 주의사항

- **CHECK 제약은 ALTER로 변경 불가**: `role` CHECK 같은 제약을 바꾸려면 테이블 재생성 필요.
  단, 값만 추가하는 경우 기존 제약이 새 값을 막지 않으면 INSERT는 그대로 동작.
- **FK는 `PRAGMA foreign_keys = ON` 필요**: `get_db()`에서 매 연결마다 설정함.
- **DROP COLUMN 제약**: PK·UNIQUE·FK·인덱스에 관여하는 컬럼은 삭제 불가할 수 있음.

## 스키마 확인 명령

```bash
python3 -c "
import sqlite3
from weekly_report.core import DB_PATH
conn = sqlite3.connect(DB_PATH)
for name, sql in conn.execute(\"SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name\"):
    print(sql, '\n')
"
```

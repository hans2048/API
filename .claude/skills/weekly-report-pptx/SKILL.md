---
name: weekly-report-pptx
description: >
  주간보고 시스템(hans2048/API)의 PPT 내보내기 기능을 수정할 때 사용.
  python-pptx 기반 슬라이드 생성, OLE 첨부파일 삽입, 동적 행 높이 계산,
  한글 처리 등 PPT 출력 관련 작업에 특화됨.
---

# Weekly Report PPT 수정 스킬

## 핵심 파일

- **`weekly_report/pptx_gen.py`** — `build_pptx(week_label, tree)` 함수. 전체 PPT 생성 로직.
- **`weekly_report/routers/activities.py`** — `GET /app_wr/export-ppt` 엔드포인트. tree 데이터 조립 후 `build_pptx()` 호출.

## 데이터 구조 (tree)

`build_pptx()`에 전달되는 `tree`는 아래 구조:

```python
[
  {
    "id": 1, "name": "그룹명",
    "tasks": [
      {
        "id": 1, "name": "업무명",
        "activities": [
          {
            "id": 1, "name": "Activity명",
            "status": "진행중", "schedule": "2024-W23",
            "note": "<p>HTML 내용</p>",
            "assignee_names": "홍길동, 김철수",
            "attachments": [
              {"filename": "파일.xlsx", "content_type": "...", "data": b"..."}
            ]
          }
        ]
      }
    ]
  }
]
```

## 주요 함수 및 상수

### 텍스트 처리

```python
def _strip_html(text) -> str:
    """HTML → 평문 변환. <br>/<p>/<div> → \n, 나머지 태그 제거."""

def _cell_text(cell, text, font_size=Pt(9), bold=False, color=C_DARK, align=PP_ALIGN.LEFT):
    """셀에 텍스트 설정. \n 기준으로 단락 분리. 기존 단락 전부 삭제 후 재작성."""

def _estimate_lines(text: str, col_w_emu: int, font_pt: float = 9.0) -> int:
    """텍스트가 몇 줄 차지하는지 추정. 동적 행 높이 계산에 사용."""
```

### 동적 행 높이

```python
LINE_H    = int(Pt(11))   # 줄 높이
CELL_PAD  = int(Pt(8))    # 셀 상하 패딩
OLE_EXTRA = int(Inches(0.16))  # 첨부파일 있을 때 추가 높이 (첨부당)
MIN_ROW_H = int(Pt(32))   # 최소 행 높이

# 행 높이 계산 후 반드시 tbl.rows[i].height 에 직접 할당
tbl.rows[0].height = header_h_emu
for ri, rh in enumerate(row_heights):
    tbl.rows[ri + 1].height = rh
```

### OLE 첨부파일 삽입

OLE 객체는 테이블 **셀 안에 삽입 불가** → 슬라이드 위에 floating shape으로 배치.
따라서 행 높이를 정확히 계산해야 OLE의 y 좌표가 해당 행과 일치함.

```python
from pptx.util import Inches
from pptx.enum.shapes import PROG_ID

# 확장자 → PROG_ID 매핑
_EXT_INFO = {
    'xlsx': (PROG_ID.XLSX, icon_color),
    'csv':  (PROG_ID.XLSX, icon_color),
    'docx': (PROG_ID.DOCX, icon_color),
    'txt':  (PROG_ID.DOCX, icon_color),
    'pptx': (PROG_ID.PPTX, icon_color),
    'pdf':  ('AcroExch.Document', icon_color),
    'hwp':  ('HWPFile', icon_color),
}
_DEFAULT_INFO = (PROG_ID.XLSX, gray_color)  # 미정의 확장자 fallback

# OLE 삽입
slide.shapes.add_ole_object(
    object_file=tmp_path,      # 반드시 실제 파일 경로 (bytes 직접 불가)
    prog_id=prog_id,
    left=x, top=y,
    width=int(Inches(0.10)),   # 아이콘 크기: 0.10" × 0.10"
    height=int(Inches(0.10)),
)

# 파일명 레이블 (아이콘 오른쪽)
txBox = slide.shapes.add_textbox(x + icon_w + gap, y, label_w, label_h)
```

**OLE 임시 파일 처리**: `add_ole_object()`는 파일 경로를 받으므로 DB에서 읽은 `bytes`를
반드시 임시 파일로 저장 후 경로 전달. 사용 후 삭제.

```python
tmp = tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False)
tmp.write(att['data'])
tmp.close()
try:
    slide.shapes.add_ole_object(tmp.name, ...)
finally:
    os.unlink(tmp.name)
```

### y 좌표 누적 계산

테이블과 OLE가 독립적인 z-레이어이므로, y 좌표는 테이블 상단 + 헤더 행 높이 +
이전 Activity 행 높이들의 합으로 계산:

```python
y_cursor = TABLE_TOP + header_h_emu
for ri, act in enumerate(activities):
    row_h = row_heights[ri]
    # 이 Activity의 OLE y 좌표 = y_cursor (행 상단)
    y_cursor += row_h
```

## 한글 처리

**PPT 내 한글**: `run.font.name = '맑은 고딕'` 으로 폰트 지정 필수.

**다운로드 파일명**: `Content-Disposition` RFC 5987 인코딩 (`activities.py`의 `_content_disposition()` 함수 사용).

**DRM 파일 업로드**: 업로드 시 `.cash/` 임시 디렉토리에 저장 → `_enable_drm()` 호출 → 재읽기(복호화) → DB 저장. `_safe_tmp_name()`으로 UUID 기반 임시 파일명 생성 (한글 파일명 OS 경로 오류 방지).

## 수정 절차

1. `pptx_gen.py` 수정
2. 서버 재시작: `uvicorn main:app --reload`
3. `GET /app_wr/export-ppt?week_label=YYYY-Www` 호출 → PPT 다운로드 후 직접 확인
4. 문제 있으면 행 높이 계산(`_estimate_lines`) 또는 y 좌표 누적 로직 재검토
5. 커밋: `git commit -m "fix(pptx): ..." && git push -u origin report_wk`

## 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| PPT 열리지 않음 / 복구 모드 | lxml이 XML 네임스페이스를 재직렬화하면서 구조 깨짐 | `add_ole_object()` API 사용, 직접 XML 조작 금지 |
| OLE가 슬라이드 최하단에 몰림 | 행 높이 미설정으로 테이블이 자동 축소됨 | `tbl.rows[i].height` 명시적 설정 |
| OLE 더블클릭 시 오류 | 확장자 미정의 or PROG_ID 불일치 | `_EXT_INFO` 매핑 확인, fallback 사용 |
| 비고 줄바꿈 PPT 미반영 | `_strip_html()`이 `</p>`, `</div>` 미처리 | `</p>` → `\n`, `</div>` → `\n` 변환 추가 |
| 첨부파일 이중 표시 | 셀 텍스트 `📎 filename` + OLE 아이콘 동시 출력 | 셀에서 텍스트 제거, OLE 아이콘만 사용 |

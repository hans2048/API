# RVM Parser & 3D Tiles Converter

AVEVA Marine에서 생성되는 `.rvm` 3D 모델 교환 파일을 파싱하여
데스크탑에서 즉시 시각화하고 **3D Tiles** 포맷으로 변환하는 데스크탑 애플리케이션.

---

## 개발 현황 요약

| 항목 | 내용 |
|------|------|
| 입력 | AVEVA Marine `.rvm` + `.att` 바이너리/텍스트 파일 |
| 출력 | 3D Tiles (`tileset.json` + `model.b3dm`) ZIP |
| 실행 환경 | **pywebview 데스크탑 앱** (Windows / macOS / Linux) |
| 개발 언어 | Python 3.10+ (백엔드) + HTML / Vanilla JavaScript (프론트엔드) |
| 3D 렌더링 | Three.js r160 (CDN) |
| 최종 수정 | 2026-06-11 |

---

## 프로젝트 구조

```
├── main.py                    # pywebview 앱 진입점
├── requirements.txt           # 의존성 목록
├── build.spec                 # PyInstaller exe 빌드 설정
├── api/
│   ├── app_api.py             # pywebview JS API 클래스
│   ├── rvm_parser.py          # RVM 바이너리 파서 (Python)
│   ├── att_parser.py          # ATT 텍스트 파서 (Python)
│   └── geometry_export.py     # GLB / b3dm / 3D Tiles 생성 (Python)
└── ui/
    └── index.html             # UI 전용 (Three.js 뷰어 + pywebview.api 호출)
```

### 역할 분리 원칙

| 영역 | 담당 | 내용 |
|------|------|------|
| Python 백엔드 | `api/` | RVM/ATT 파싱, 3D Tiles 변환, 파일 다이얼로그 |
| HTML 프론트엔드 | `ui/` | Three.js 3D 렌더링, UI 표시만 담당 |

변환 알고리즘은 Python 코드에만 존재하므로 사용자가 UI에서 로직을 볼 수 없습니다.

---

## 실행 방법

### 개발 환경에서 실행

```bash
pip install -r requirements.txt
python main.py
```

### exe 빌드 (Windows)

```bash
pip install pyinstaller
pyinstaller build.spec --clean
# 결과물: dist/RVMParser/RVMParser.exe
```

> **배포 시 주의**: 배포 대상 PC에 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 설치 필요

---

## 사용 방법

### 파일 로드

1. 앱 실행 후 **📂 파일 열기** 버튼 클릭
2. `.rvm` / `.att` 파일 선택 (복수 선택 가능)
3. 같은 이름의 `.rvm` + `.att` 는 자동으로 **쌍(pair)으로 연결**
4. 여러 쌍을 함께 선택하면 **단일 씬에 머지**되어 통합 리뷰 가능

### 다중 파일 예시

```
ship_hull.rvm  ←┐ 자동 쌍 연결
ship_hull.att  ←┘
engine_room.rvm  ←┐ 자동 쌍 연결
engine_room.att  ←┘
                ↓
         통합 3D 씬 (두 모델 머지)
```

### 3D 뷰어 조작

| 동작 | 방법 |
|------|------|
| 회전 | 좌클릭 드래그 |
| 이동 | 우클릭 드래그 |
| 줌 | 마우스 휠 |
| 전체 보기 | ⟳ 전체 버튼 |
| 뷰 전환 | 위 / 정면 / 측면 버튼 |
| 와이어프레임 | ⊞ 와이어 버튼 |

### 3D Tiles 내보내기

- **🗂 3D Tiles 내보내기** 버튼 클릭 → 저장 경로 선택
- 로드된 모든 모델이 단일 `model.b3dm` 으로 머지되어 ZIP 저장
- 출력물은 CesiumJS / Cesium ion 에서 바로 로드 가능

---

## 데이터 흐름

```
[파일 열기 버튼]
      │
      ▼
[Python] open_file_dialog() → 파일 경로 반환
      │
      ▼
[Python] RVMParser.parse() → model dict (JSON)
      │
      ▼
[JS / Three.js] GeometryBuilder → 3D 렌더링
      │
      ▼
[Python] TilesExporter.export_all() → ZIP 저장
```

---

## UI 구성

### 사이드바 탭

| 탭 | 내용 |
|----|------|
| 📁 파일 | 로드된 RVM+ATT 쌍 목록, 색상 피커, On/Off 토글, 상태 배지, 개별 제거 버튼 |
| 📊 통계 | 전체 모델 통합 통계 (그룹 / 프리미티브 / ATT 속성 노드 수) |
| 🌲 트리 | 모델별 계층 트리뷰 (그룹 접기/펼치기, ATT 배지) |
| 🔩 청크 | 마지막 파싱된 파일의 청크 목록 (오프셋, next 포인터) |
| 🐛 로그 | 파싱 상세 로그 |

### 파일 목록 컨트롤

```
[색상 스와치] [ON/OFF]  파일명    [그룹 42] [프리미티브 1234] [ATT ✓ (87)]  [✕]
```

- **색상 스와치**: 클릭하여 모델 색상 즉시 변경
- **ON/OFF 버튼**: 모델을 씬에서 숨기거나 다시 표시 (제거 없이 visibility 토글)
- ATT 미연결: `[ATT —]` / 파싱 오류: `[RVM ✗]` + 오류 메시지

---

## RVM 파일 포맷 스펙

### 기본 구조

- AVEVA Marine / PDMS 독자적 바이너리 3D 교환 포맷
- **빅 엔디안(Big-Endian)** 바이트 순서
- 파일은 **청크(Chunk)** 단위로 구성

### 청크 헤더 구조 (24 bytes)

```
[16 bytes] 청크 이름 — 4 × uint32 BE, 각 uint32의 LSB가 ASCII 문자
           예) "HEAD" = 00 00 00 48  00 00 00 45  00 00 00 41  00 00 00 44
[4 bytes]  next_chunk_offset (uint32 BE)
[4 bytes]  dunno (uint32 BE, 용도 미상)
```

### 청크 종류

| 청크명 | 설명 |
|--------|------|
| `HEAD` | 파일 헤더 (버전, 정보, 날짜, 작성자) |
| `MODL` | 모델 이름, 프로젝트명 |
| `CNTB` | 그룹(컨테이너) 시작 — 이름, translation(mm), materialId |
| `CNTE` | 그룹 종료 |
| `PRIM` | 3D 프리미티브 |
| `OBST` | Obstruction 프리미티브 |
| `INSU` | Insulation 프리미티브 |
| `COLR` | 색상 정보 (RGB) |
| `END:` | 파일 종료 |

### 지원 프리미티브 타입

| 타입 | 이름 | 파라미터 |
|------|------|----------|
| 1 | Pyramid | bx, by, tx, ty, ox, oy, height |
| 2 | Box | xlen, ylen, zlen (half-extents) |
| 3 | RectTorus | rinside, routside, height, angle |
| 4 | CircTorus | offset, radius, angle |
| 5 | EllDish | baseRadius, height |
| 6 | SphDish | baseRadius, height |
| 7 | Snout | rbottom, rtop, height, ox, oy, bsx, bsy, tsx, tsy |
| 8 | Cylinder | radius, height |
| 9 | Sphere | diameter |
| 10 | Line | a, b |
| 11 | FacetGroup | 폴리곤 데이터 (가변 길이) |

### 좌표계

| 항목 | AVEVA Marine RVM | Three.js |
|------|-----------------|----------|
| 상향(Up) | **Z축** | Y축 |
| 우측 | X축 | X축 |
| 전방 | Y축 | -Z축 |

**변환**: `scene.root.rotation.x = -π/2` — 모든 프리미티브 일괄 변환

---

## ATT 파일 포맷 스펙

PDMS / AVEVA Marine 텍스트 속성 파일:

```
/SITE/ZONE/EQUI-001
NAMT 'Equipment Name'
TAGN 'TAG-001'
BORE 150

/SITE/ZONE/PIPE-001
NAMT 'Pipe 001'
BORE 100
```

ATT 경로의 마지막 요소와 RVM 그룹 이름을 **퍼지 매칭**하여 속성 자동 연결.

---

## 3D Tiles 출력 스펙

```
export.zip
├── tileset.json      ← 타일셋 메타데이터
└── model.b3dm        ← Batched 3D Model (GLB 포함)
```

---

## 기능 구현 현황

### Phase 1 ~ 5 ✅ 완료

- [x] RVM 바이너리 파싱 (HEAD, MODL, CNTB/CNTE, PRIM, OBST, INSU, COLR, END:)
- [x] 모든 프리미티브 타입 파라미터 파싱 (type 1~11)
- [x] ATT 파서 (PDMS 텍스트 포맷, 퍼지 그룹 매칭)
- [x] Three.js 3D 뷰어 (orbit / pan / zoom)
- [x] 다중 모델 단일 씬 머지
- [x] GLB → b3dm → 3D Tiles ZIP 생성
- [x] 모델별 색상 선택, On/Off 토글
- [x] FacetGroup Earcut 삼각분할 + 홀 처리
- [x] NHOLE/PHOLE 홀 마커 그룹 렌더링 생략
- [x] **pywebview 데스크탑 앱 전환** (Phase 5)
  - 변환 로직 전체를 Python 백엔드로 이전
  - HTML에는 렌더링/UI만 존재, 알고리즘 비공개
  - 네이티브 파일 다이얼로그 적용
  - PyInstaller exe 빌드 지원

### Phase 6 — 고도화 (예정)

- [ ] Snout shear (bsx/bsy/tsx/tsy) 형상 정확도 개선
- [ ] 프리미티브 클릭 시 ATT 속성 팝업
- [ ] 대용량 모델 LOD 처리
- [ ] 파일별 색상 3D Tiles 내보내기 반영
- [ ] Cesium ion / CesiumJS 연동 뷰어

---

## 알려진 제한사항

| 항목 | 내용 |
|------|------|
| Snout shear | bsx/bsy/tsx/tsy 기울기 근사만 가능 |
| ATT 매칭 | 퍼지 매칭 — 동명 그룹 오매칭 가능성 |
| 대용량 | 수십만 프리미티브 시 성능 저하 가능 |
| 문자열 인코딩 | Latin-1 디코딩 (일부 파일은 다른 인코딩 사용 가능) |
| 색상 내보내기 | 3D Tiles 내보내기 시 파일별 지정 색상 미반영 (Phase 6 예정) |

---

## 참조

- [cdyk/rvmparser](https://github.com/cdyk/rvmparser) — RVM 청크 파싱 스펙
- [3D Tiles Specification](https://github.com/CesiumGS/3d-tiles) — b3dm / tileset.json 포맷
- [glTF 2.0 Specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) — GLB 바이너리 포맷
- [pywebview](https://pywebview.flowrl.com/) — Python 데스크탑 WebView 라이브러리

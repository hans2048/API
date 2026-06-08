# RVM Parser & 3D Tiles Converter

AVEVA Marine에서 생성되는 `.rvm` 3D 모델 교환 파일을 파싱하여,
웹 브라우저에서 즉시 시각화하고 **3D Tiles** 포맷으로 변환하는 HTML 단일 파일 애플리케이션.

---

## 개발 현황 요약

| 항목 | 내용 |
|------|------|
| 입력 | AVEVA Marine `.rvm` + `.att` 바이너리/텍스트 파일 |
| 출력 | 3D Tiles (`tileset.json` + `model.b3dm`) ZIP |
| 실행 환경 | 브라우저 단독 실행 (서버 불필요, 단일 HTML 파일) |
| 개발 언어 | HTML + Vanilla JavaScript |
| 3D 렌더링 | Three.js r160 (CDN) |
| 압축/내보내기 | JSZip 3.10 (CDN) |
| 최종 수정 | 2026-06-08 |

---

## 사용 방법

### 파일 로드
1. `rvm_parser.html` 을 브라우저에서 열기
2. RVM / ATT 파일을 **드래그 앤 드롭** 하거나 **📂 파일 열기** 버튼 클릭
3. **복수 파일 동시 드롭 가능** — 같은 이름의 `.rvm` + `.att` 는 자동으로 쌍(pair)으로 연결
4. 여러 쌍을 함께 드롭하면 **단일 씬에 머지**되어 통합 리뷰 가능

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
- **🗂 3D Tiles 내보내기** 버튼 클릭
- 로드된 모든 모델이 단일 `model.b3dm` 으로 머지되어 ZIP 다운로드
- 출력물은 CesiumJS / Cesium ion 에서 바로 로드 가능

---

## UI 구성

### 사이드바 탭

| 탭 | 내용 |
|----|------|
| 📁 파일 | 로드된 RVM+ATT 쌍 목록, 색상 피커, On/Off 토글, 상태 배지, 개별 제거 버튼 |
| 📊 통계 | 전체 모델 통합 통계 (그룹 / 프리미티브 / ATT 속성 노드 수) |
| 🌲 트리 | 모델별 계층 트리뷰 (그룹 접기/펼치기, ATT 배지) |
| 🔩 청크 | 마지막 파싱된 파일의 청크 목록 (오프셋, next 포인터) |
| 🐛 로그 | 파싱 상세 로그 (헥스 덤프, 청크별 파싱 결과) |

### 파일 목록 컨트롤

```
[색상 스와치] [ON/OFF]  파일명    [그룹 42] [프리미티브 1234] [ATT ✓ (87)]  [✕]
```
- **색상 스와치**: 클릭하여 브라우저 내장 컬러 피커로 모델 색상 즉시 변경
- **ON/OFF 버튼**: 모델을 씬에서 숨기거나 다시 표시 (제거 없이 visibility 토글)
- ATT 미연결: `[ATT —]`
- 파싱 오류: `[RVM ✗]` + 오류 메시지
- 숨김 상태: 파일 엔트리 반투명 표시

---

## 시각화 방식

RVM 파일 로드 후 **별도 변환 없이 즉시 렌더링**됩니다.

```
RVM 바이너리
    │
    ▼ 파싱 (RVMParser)
내부 JS 모델 객체
(groups → primitives → matrix/params/bbox)
    │
    ▼ 지오메트리 빌드 (GeometryBuilder)
Three.js BufferGeometry
    │
    ▼ GPU 렌더링
3D 뷰어 (즉시 표시)
```

**3D Tiles 내보내기는 별도 단계** — 버튼 클릭 시에만 GLB → b3dm → ZIP 변환 수행.

---

## RVM 파일 포맷 스펙

### 기본 구조

- AVEVA Marine / PDMS에서 생성하는 독자적 바이너리 3D 교환 포맷
- **빅 엔디안(Big-Endian)** 바이트 순서
- 파일은 **청크(Chunk)** 단위로 구성

### 실제 청크 헤더 구조 (24 bytes)

```
[16 bytes] 청크 이름 — 4 × uint32 BE, 각 uint32의 LSB(최하위 바이트)가 ASCII 문자
           예) "HEAD" = 00 00 00 48  00 00 00 45  00 00 00 41  00 00 00 44
[4 bytes]  next_chunk_offset — 다음 청크의 절대 바이트 오프셋 (uint32 BE)
[4 bytes]  dunno — 용도 미상 (uint32 BE)
```

> 청크 이름이 4바이트가 아닌 **4 × 4 = 16바이트**임에 주의.  
> 참조: [cdyk/rvmparser ParserRVM.cpp](https://github.com/cdyk/rvmparser)

### 청크 종류

| 청크명 | 설명 |
|--------|------|
| `HEAD` | 파일 헤더 (버전, 정보, 날짜, 작성자) |
| `MODL` | 모델 이름, 프로젝트명 |
| `CNTB` | 그룹(컨테이너) 시작 — 이름, translation(mm), materialId |
| `CNTE` | 그룹 종료 |
| `PRIM` | 3D 프리미티브 (도형) |
| `OBST` | Obstruction 프리미티브 |
| `INSU` | Insulation 프리미티브 |
| `COLR` | 색상 정보 (RGB, version 필드 없음) |
| `END:` | 파일 종료 |

### 청크 데이터 공통 구조

```
[4 bytes]  버전 번호 (uint32 BE) — COLR 청크만 예외: version 필드 없음
[N bytes]  청크별 데이터
```

### 문자열 인코딩

```
[4 bytes] word_count (uint32 BE) — 실제 데이터 크기 = word_count × 4 bytes
[N bytes] 문자열 데이터 (null 패딩 포함, Latin-1 인코딩)
```

### CNTB 데이터 구조

```
[4 bytes]  버전 (uint32 BE)
[N bytes]  그룹 이름 (문자열)
[4 bytes]  tx (float32 BE, mm 단위 → ×0.001 = model 단위)
[4 bytes]  ty (float32 BE)
[4 bytes]  tz (float32 BE)
[4 bytes]  materialId (uint32 BE)
[4 bytes]  transparency (uint8, 버전 > 2 시만 존재, 나머지 3바이트 padding)
```

### 프리미티브 구조 (`PRIM` 청크 내부)

```
[4 bytes]  버전 (uint32 BE)
[4 bytes]  프리미티브 타입 (uint32 BE)
[48 bytes] 변환 행렬 (3×4, float32 × 12, big-endian)
[24 bytes] 바운딩 박스 (min XYZ + max XYZ, float32 × 6)
[N bytes]  타입별 파라미터
```

### 변환 행렬 레이아웃

12개의 float32로 구성된 3×4 행렬 (column-major):
```
[ix, iy, iz,  jx, jy, jz,  kx, ky, kz,  tx, ty, tz]
 ↑ X축 방향   ↑ Y축 방향   ↑ Z축 방향   ↑ 이동(Translation)
```

Three.js Matrix4 변환:
```javascript
matrix4.set(
  ix, jx, kx, tx,
  iy, jy, ky, ty,
  iz, jz, kz, tz,
   0,  0,  0,  1
);
```

### 지원 프리미티브 타입

| 타입 번호 | 이름 | 파라미터 (float32 × N) |
|-----------|------|------------------------|
| 1 | Pyramid | bx, by, tx, ty, ox, oy, height (7개) |
| 2 | Box | xlen, ylen, zlen — half-extents (3개) |
| 3 | RectTorus | rinside, routside, height, angle (4개) |
| 4 | CircTorus | offset, radius, angle (3개) |
| 5 | EllDish | baseRadius, height (2개) |
| 6 | SphDish | baseRadius, height (2개) |
| 7 | Snout | rbottom, rtop, height, ox, oy, bsx, bsy, tsx, tsy (9개) |
| 8 | Cylinder | radius, height (2개) |
| 9 | Sphere | **diameter** (반지름 아닌 지름, 1개) |
| 10 | Line | a, b (로컬 축 스칼라, 2개) |
| 11 | FacetGroup | 폴리곤 데이터 (가변 길이, 아래 참조) |

### FacetGroup (type 11) 구조

```
[4 bytes]  numPolygons (uint32 BE)
  [4 bytes]  numContours (uint32 BE)
    [4 bytes]  numVertices (uint32 BE)
      [12 bytes] position (float32×3 BE)
      [12 bytes] normal   (float32×3 BE)
```

### 좌표계

- AVEVA 좌표계: **Z축 상향 (Z-up)**
- Three.js 좌표계: **Y축 상향 (Y-up)**
- 현재: 변환 미적용 (Phase 4 예정)

---

## ATT 파일 포맷 스펙

PDMS / AVEVA Marine 속성 파일 (텍스트 기반):

```
/SITE/ZONE/EQUI-001
NAMT 'Equipment Name'
TAGN 'TAG-001'
BORE 150
SPEC 'A5A'

/SITE/ZONE/PIPE-001
NAMT 'Pipe 001'
BORE 100
```

### 파싱 규칙

| 패턴 | 의미 |
|------|------|
| `/`로 시작하는 줄 | 경로(path) 선언 |
| `KEY 'string'` | 문자열 속성 |
| `KEY number` | 숫자 속성 |
| `KEY WORD` | 워드 속성 |
| `!`, `#`, `*` 로 시작 | 주석 (무시) |

### RVM 그룹 매칭

ATT 경로의 마지막 요소와 RVM 그룹 이름을 **퍼지 매칭**하여 속성 자동 연결.  
매칭된 그룹은 트리뷰에 `ATT` 배지로 표시.

---

## 3D Tiles 출력 스펙

### 출력 파일 구조

```
<modelname>_3dtiles.zip   (복수 모델 시: merged_3dtiles.zip)
├── tileset.json      ← 타일셋 메타데이터
└── model.b3dm        ← Batched 3D Model (GLB 포함)
```

### tileset.json 구조

```json
{
  "asset": { "version": "1.0" },
  "geometricError": <모델 최대 크기>,
  "root": {
    "boundingVolume": { "box": [cx, cy, cz, hx,0,0, 0,hy,0, 0,0,hz] },
    "geometricError": 0,
    "refine": "ADD",
    "content": { "uri": "model.b3dm" }
  }
}
```

### b3dm 파일 구조

```
[4 bytes]  magic: "b3dm"
[4 bytes]  version: 1 (uint32 LE)
[4 bytes]  byteLength (uint32 LE)
[4 bytes]  featureTableJSONByteLength
[4 bytes]  featureTableBinaryByteLength (0)
[4 bytes]  batchTableJSONByteLength (0)
[4 bytes]  batchTableBinaryByteLength (0)
[N bytes]  featureTable JSON: {"BATCH_LENGTH": 0}
[N bytes]  GLB 바이너리 데이터
```

### GLB (binary glTF 2.0) 구조

```
GLB Header (12 bytes)
  magic: 0x46546C67 ('glTF')
  version: 2
  length: 전체 크기

JSON Chunk
  chunkLength, chunkType: 0x4E4F534A ('JSON')
  glTF JSON (positions, normals, indices, material)

BIN Chunk
  chunkLength, chunkType: 0x004E4942 ('BIN\0')
  Float32 positions + Float32 normals + Uint16/Uint32 indices
```

---

## 기능 구현 현황

### Phase 1 — RVM 파싱 + 3D 시각화 ✅

- [x] RVM 바이너리 파일 읽기 (File API + ArrayBuffer)
- [x] 청크 헤더 파싱 (24바이트: 16 이름 + 4 nextOff + 4 dunno)
- [x] 청크 파싱 (HEAD, MODL, CNTB/CNTE, PRIM, OBST, INSU, COLR, END:)
- [x] 모든 프리미티브 타입 파라미터 파싱 (type 1~11)
- [x] FacetGroup (type 11) fan triangulation
- [x] Three.js 3D 뷰어 (마우스 orbit/pan/zoom)
- [x] 그룹 계층 트리뷰 (접기/펼치기)
- [x] 프리미티브 유형별 통계 표시
- [x] 바이너리 헥스 덤프 디버그 뷰어
- [x] 뷰 컨트롤 (위/정면/측면, 와이어프레임, 전체 맞춤)

### Phase 2 — 3D Tiles 변환 ✅

- [x] 프리미티브 → Three.js 지오메트리 변환 (type 1~11)
- [x] 그룹 누적 변환 행렬 계산
- [x] GLB 바이너리 생성 (positions, normals, indices)
- [x] b3dm 래퍼 생성
- [x] tileset.json 생성 (바운딩 박스 자동 계산)
- [x] ZIP으로 묶어 다운로드

### Phase 3 — 다중 파일 + ATT 연동 ✅

- [x] 드래그 앤 드롭 (복수 파일 동시)
- [x] RVM + ATT 파일 stem 이름 기반 자동 쌍 매칭
- [x] ATT 파서 (PDMS 텍스트 포맷, 퍼지 그룹 매칭)
- [x] 다중 모델 단일 씬 머지 (각 모델별 고유 색상)
- [x] 모델별 개별 추가/제거
- [x] 통합 3D Tiles 내보내기 (모든 모델 단일 b3dm)
- [x] 📁 파일 탭 (로드 현황, 상태 배지)
- [x] 📊 통합 통계 탭

### Phase 4 — 형상 정확도 개선 ✅

- [x] **Cylinder / Snout 축 보정**: Three.js CylinderGeometry(Y축) → RVM Z축, +90° X 회전 적용
- [x] **CNTB 이중 변환 제거**: M_3x4 행렬이 절대 월드 좌표임을 확인(rvmparser 소스 검증), CNTB translation 미적용
- [x] **Sphere/Torus 시각화**: 타입 3·4·9 정상 렌더링
- [x] **DoubleSide 재질**: 음수 행렬식(inverted normal) 프리미티브 양면 렌더링
- [x] **NaN/빈 파라미터 가드**: 잘못된 지오메트리 스킵 후 bbox 폴백
- [x] **FacetGroup 홀 삼각분할 수정**: `THREE.ShapeUtils.triangulateShape`에 `THREE.Vector2` 전달  
      (plain `{x,y}` 전달 시 내부 `.equals()` TypeError → fan fallback → 홀 채움 현상 해결)
- [x] **Earcut 정합성**: 외부 윤곽 CCW, 홀 윤곽 CW winding 보장 + 중복 점 제거(`dedupSync`) 2D/3D 동기화
- [x] **NHOLE/PHOLE 마커 그룹**: AVEVA Marine 구조적 홀 마커 그룹 렌더링 완전 생략

### Phase 5 — UX 개선 ✅

- [x] **파일별 색상 선택**: 파일 목록에서 색상 스와치 클릭 → 컬러 피커로 즉시 변경
- [x] **파일별 On/Off 토글**: 개별 모델 숨기기/표시 (씬에서 제거 없이 visibility만 변경)
- [x] 파싱 로그 O(n²) DOM 업데이트 개선 (배치 flush)
- [x] 대용량 파일 파싱 중 브라우저 프리즈 방지 (비동기 yield)

### Phase 6 — 고도화 (예정)

- [ ] Z-up → Y-up 좌표계 변환 옵션
- [ ] Snout shear (bsx/bsy/tsx/tsy) 형상 정확도 개선
- [ ] 프리미티브 클릭 시 속성 정보 팝업 (ATT 데이터 표시)
- [ ] 대용량 모델 LOD (Level of Detail) 처리
- [ ] 여러 b3dm 타일로 분할 (공간 분할)
- [ ] Cesium ion / CesiumJS 연동 뷰어 (별도 페이지)
- [ ] 모델 단위 자동 감지 및 변환 (mm → m)
- [ ] 프리미티브별 COLR 색상 3D Tiles 반영
- [ ] 파일별 색상 3D Tiles 내보내기 반영

---

## 알려진 제한사항

| 항목 | 내용 |
|------|------|
| 좌표계 | Z-up/Y-up 자동 변환 미적용 |
| Snout shear | bsx/bsy/tsx/tsy 기울기 Three.js CylinderGeometry로 근사만 가능 |
| ATT 매칭 | 경로 전체 일치 대신 퍼지 매칭 사용 — 동명 그룹 오매칭 가능성 |
| 대용량 | 수십만 프리미티브 시 브라우저 성능 저하 가능 |
| 문자열 인코딩 | Latin-1 디코딩 적용 (일부 파일은 다른 인코딩 사용 가능) |
| CesiumJS | 이 앱에 내장 불가 (50MB+ 번들, HTTPS 필요) — 3D Tiles 출력 후 별도 사용 권장 |
| 색상 내보내기 | 3D Tiles 내보내기 시 파일별 지정 색상 미반영 (Phase 6 예정) |

---

## 개발 환경

- 브라우저에서 HTML 파일 직접 열기 (로컬 서버 불필요)
- Three.js r160 (CDN)
- JSZip 3.10 (CDN)
- 외부 의존성 없음 (순수 Vanilla JS)

## 참조

- [cdyk/rvmparser](https://github.com/cdyk/rvmparser) — 청크 헤더/파라미터 파싱 스펙 확인
- [3D Tiles Specification](https://github.com/CesiumGS/3d-tiles) — b3dm / tileset.json 포맷
- [glTF 2.0 Specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) — GLB 바이너리 포맷

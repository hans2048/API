# RVM Parser & 3D Tiles Converter

AVEVA Marine에서 생성되는 `.rvm` 3D 모델 교환 파일을 파싱하여,
웹 브라우저에서 시각화하고 **3D Tiles** 포맷으로 변환하는 HTML 단일 파일 애플리케이션.

---

## 개발 목표

| 항목 | 내용 |
|------|------|
| 입력 | AVEVA Marine `.rvm` 바이너리 파일 |
| 출력 | 3D Tiles (`tileset.json` + `model.b3dm`) ZIP |
| 실행 환경 | 브라우저 단독 실행 (서버 불필요, 단일 HTML 파일) |
| 개발 언어 | HTML + Vanilla JavaScript |
| 3D 렌더링 | Three.js (CDN) |
| 압축/내보내기 | JSZip (CDN) |

---

## RVM 파일 포맷 스펙

### 기본 구조

- AVEVA Marine / PDMS에서 생성하는 독자적 바이너리 3D 교환 포맷
- **빅 엔디안(Big-Endian)** 바이트 순서
- 파일은 **청크(Chunk)** 단위로 구성

### 청크 구조

```
[4 bytes] 청크 이름 (ASCII, 예: HEAD, MODL, CNTB ...)
[4 bytes] 버전 번호 (uint32, big-endian)
[4 bytes] 데이터 크기 (uint32, big-endian)
[N bytes] 청크 데이터
```

### 청크 종류

| 청크명 | 설명 |
|--------|------|
| `HEAD` | 파일 헤더 (버전, 정보, 날짜, 작성자) |
| `MODL` | 모델 이름, 날짜 |
| `CNTB` | 그룹(컨테이너) 시작 — 이름, 위치(translation) |
| `CNTE` | 그룹 종료 |
| `PRIM` | 3D 프리미티브 (도형) |
| `COLR` | 색상 정보 (RGB float) |
| `END:` | 파일 종료 |

### 문자열 인코딩

```
[4 bytes] 워드 수 (uint32) — 실제 데이터 크기 = 워드수 × 4 bytes
[N bytes] 문자열 데이터 (null 패딩 포함)
```

### 프리미티브 구조 (`PRIM` 청크 내부)

```
[4 bytes]  프리미티브 타입 (uint32)
[48 bytes] 변환 행렬 (3×4, float32 × 12, big-endian)
[24 bytes] 바운딩 박스 (min XYZ + max XYZ, float32 × 6)
[N bytes]  타입별 파라미터
```

### 변환 행렬 레이아웃

12개의 float로 구성된 3×4 행렬:
```
[ix, iy, iz,  jx, jy, jz,  kx, ky, kz,  tx, ty, tz]
 ↑ X축 방향   ↑ Y축 방향   ↑ Z축 방향   ↑ 이동(Translation)
```

### 지원 프리미티브 타입

| 타입 번호 | 이름 | 파라미터 |
|-----------|------|----------|
| 1 | Pyramid | xbottom, ybottom, xtop, ytop, height, xoffset, yoffset |
| 2 | Box | xlen, ylen, zlen (half-extents) |
| 3 | RectTorus | rinside, routside, height, angle |
| 4 | CircTorus | offset, radius, angle |
| 5 | EllDish | xdiameter, ydiameter, height |
| 6 | SphDish | diameter, height |
| 7 | Snout | rbottom, rtop, height, xoffset, yoffset, xbshear, ybshear, xtshear, ytshear |
| 8 | Cylinder | radius, height |
| 9 | Sphere | radius |
| 10 | Line | x1, y1, z1, x2, y2, z2 |
| 11 | FacetGroup | 폴리곤 데이터 (복잡, 별도 파싱 필요) |

### 좌표계

- AVEVA 좌표계: **Z축 상향 (Z-up)**
- Three.js 좌표계: **Y축 상향 (Y-up)**
- 변환 필요: Y ↔ Z 축 스왑

---

## 3D Tiles 출력 스펙

### 출력 파일 구조

```
rvm_3dtiles.zip
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
[4 bytes]  featureTableBinaryByteLength
[4 bytes]  batchTableJSONByteLength
[4 bytes]  batchTableBinaryByteLength
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
  chunkLength, chunkType: 0x4E4F534A
  glTF JSON (positions, normals, indices, material)

BIN Chunk
  chunkLength, chunkType: 0x004E4942
  Float32 positions + Float32 normals + Uint16/Uint32 indices
```

---

## 기능 요구사항

### Phase 1 — RVM 파싱 + 3D 시각화 ✅

- [x] RVM 바이너리 파일 읽기 (FileReader API)
- [x] 청크 파싱 (HEAD, MODL, CNTB/CNTE, PRIM, COLR, END:)
- [x] 모든 프리미티브 타입 파라미터 파싱 (type 1~10)
- [x] Three.js 3D 뷰어 (마우스 orbit/pan/zoom)
- [x] 그룹 계층 트리뷰 (접기/펼치기)
- [x] 프리미티브 유형별 통계 표시
- [x] 바이너리 헥스 덤프 디버그 뷰어
- [x] 뷰 컨트롤 (위/정면/측면, 와이어프레임)

### Phase 2 — 3D Tiles 변환 ✅

- [x] 프리미티브 → Three.js 지오메트리 변환
- [x] 그룹 누적 변환 행렬 계산
- [x] GLB 바이너리 생성 (positions, normals, indices)
- [x] b3dm 래퍼 생성
- [x] tileset.json 생성
- [x] ZIP으로 묶어 다운로드

### Phase 3 — 고도화 (예정)

- [ ] Z-up → Y-up 좌표계 변환 옵션
- [ ] FacetGroup (type 11) 폴리곤 파싱
- [ ] ATT 속성 파일 연동 (태그 정보 표시)
- [ ] 프리미티브별 색상 지정 (COLR 청크 활용)
- [ ] 대용량 모델 LOD (Level of Detail) 처리
- [ ] 여러 b3dm 타일로 분할 (공간 분할)
- [ ] Cesium ion / CesiumJS 연동 테스트
- [ ] 모델 단위 변환 (mm → m)
- [ ] 프리미티브 클릭 시 속성 정보 팝업

---

## 알려진 제한사항

| 항목 | 내용 |
|------|------|
| FacetGroup | type 11 폴리곤 데이터 미파싱 (건너뜀) |
| 좌표계 | Z-up/Y-up 자동 변환 미적용 |
| Snout shear | xbshear/ybshear 기울기 형상 미반영 |
| 대용량 | 수십만 프리미티브 시 브라우저 성능 저하 가능 |
| 문자열 인코딩 | UTF-8 가정 (일부 파일은 Latin-1 사용) |

---

## 개발 환경

- 브라우저에서 HTML 파일 직접 열기 (로컬 서버 불필요)
- Three.js r160 (CDN)
- JSZip 3.10 (CDN)
- 외부 의존성 없음 (순수 Vanilla JS)

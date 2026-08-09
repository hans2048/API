# SVG Inspector

단일 HTML 파일로 동작하는 인터랙티브 SVG 분석·선택 도구입니다.  
외부 의존성 없이 브라우저에서 직접 실행됩니다.

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **SVG 로드** | 파일 선택으로 SVG를 캔버스에 렌더링 |
| **줌 / 팬** | 휠 줌, Shift+드래그 또는 가운데 버튼 패닝 |
| **3가지 선택 모드** | 최상위 그룹 / 단일 객체 / Tag 그룹 |
| **Hierarchy 탭** | Tag 속성 기반 순차 계층 구조 (접기/펼치기) |
| **Topology 탭** | `ItemType="PipeRun"` 기반 병합 계층 + Seq 하위 항목 |
| **Zoom-fit** | 계층 항목 선택 시 해당 요소로 자동 줌 |
| **하이라이트** | 선택 요소 및 연관 순차 형제 요소 일괄 강조 |
| **SVG 소스 뷰어** | 들여쓰기·구문 강조가 적용된 SVG 텍스트 팝업 |

---

## 사용 방법

1. `test_svg_parse.html`을 브라우저에서 엽니다.
2. 상단 **SVG 열기** 버튼으로 SVG 파일을 로드합니다.
3. 상단 **선택 모드** 세그먼트 버튼으로 선택 단위를 조절합니다.
4. 왼쪽 사이드바의 **Hierarchy / Topology** 탭에서 항목을 클릭하면  
   해당 요소가 하이라이트되고 화면이 Zoom-fit됩니다.
5. 캔버스에서 직접 요소를 클릭해도 선택됩니다.
6. **소스 보기** 버튼으로 들여쓰기된 SVG 소스를 확인하거나 복사합니다.

### 조작 단축키

| 동작 | 방법 |
|------|------|
| 줌 인/아웃 | 마우스 휠 |
| 패닝 | Shift+드래그 또는 가운데 버튼 드래그 |
| 패닝 해제 | 우클릭 메뉴 비활성화(contextmenu 차단) |

---

## 파일 구조

```
test_svg_parse.html   # 모든 기능이 포함된 단일 HTML 파일
README.md             # 이 문서
```

---

## 기술 상세

### 선택 모드

| 모드 | 동작 |
|------|------|
| **최상위 그룹** | SVG 루트의 직계 `<g>` 자식을 단위로 선택 |
| **단일 객체** | 클릭된 요소 자체를 선택 |
| **Tag 그룹** | `Tag` 속성을 가진 `<g>`를 단위로 선택. 없으면 현재 요소 선택 |

### Hierarchy 탭 — 순차 그룹화 로직

`Tag` 속성을 가진 `<g>` 요소를 기준으로 그룹을 생성합니다.  
다음 `Tag <g>` 이전까지의 형제 요소들은 앞선 그룹에 포함됩니다.

```
<g Tag="Line-A">  →  그룹 "Line-A" 생성
<path ...>         →  "Line-A" 그룹에 포함 (data-tag-group 마킹)
<text ...>         →  "Line-A" 그룹에 포함
<g Tag="Line-B">  →  그룹 "Line-B" 생성
```

- `Tag` 없는 `<g>`는 투명하게 통과(자식을 같은 레벨로 처리)
- 그룹은 ▼/▶ 토글로 접기/펼치기 가능
- 그룹 선택 시 `data-tag-group` 속성으로 연관 형제 요소까지 일괄 하이라이트

### Topology 탭 — PipeRun 기반 계층 + Seq 하위 항목

#### PipeRun 그룹 생성
`ItemType="PipeRun"` 속성을 가진 `<g>` 요소를 Topology 그룹으로 사용합니다.

- 동일한 `Tag` 값을 가진 PipeRun은 **하나의 그룹으로 병합**
- 병합된 모든 PipeRun 요소는 `data-pr-group`으로 연결되어 일괄 하이라이트

#### Seq 하위 항목
`Seq` 속성(`"TopologyName:sortOrder"` 형식)을 가진 `<g>` 요소를 파싱하여  
해당 Topology 그룹 하부에 정렬된 연결 구성요소로 표시합니다.

```
Seq="250-PL-24048-1S81CR-C:16"
      └── TopologyName  └── 정렬 순서(오름차순)
```

- `ItemType="PipeRun"`인 요소는 Seq 수집에서 제외(이미 PipeRun 그룹으로 사용)
- "── 연결 구성요소" 구분선 아래에 정렬순서 기준 오름차순 표시

### 하이라이트 & Zoom-fit

```
선택 요소
  + querySelectorAll('*')           → 자식 요소 전체
  + [data-tag-group="id"]           → Hierarchy 순차 형제
  + [data-pr-group="id"]            → Topology 병합 요소
  → 모든 BBox 합산 → 15% 여백 → viewBox 계산 → Zoom-fit
```

---

## 개발 이력 (요구사항 순서)

### 1단계 — 초기 구성
- SVG 파일 로드 및 캔버스 렌더링
- 요소 클릭 선택 및 Inspector(속성 표시) 구현
- 선택 모드 3종: 최상위 그룹 / 단일 객체 / Name 속성 그룹

### 2단계 — Zoom-fit & 하이라이트 개선
- Hierarchy 항목 선택 시 해당 요소로 자동 Zoom-fit
- `name` 속성 값을 계층 표시명으로 사용
- 하이라이트 선 굵기 축소(가시성 개선, `stroke-width: 0.5px`)

### 3단계 — Tag 속성 기반 Hierarchy
- 선택 모드를 `Tag` 속성 기반으로 변경
- `Tag <g>` 하부의 모든 자식(`<g>`, `<text>` 등) 포함 재귀 처리
- 최상위 `Tag` 없는 `<g>`는 Hierarchy에서 제외

### 4단계 — SVG 소스 뷰어
- "소스 보기" 버튼 클릭 시 팝업 모달 표시
- SVG 텍스트를 들여쓰기 + 구문 강조(태그명/속성명/속성값 색상 구분)로 렌더링
- 클립보드 복사 기능

### 5단계 — 순차 그룹화 & 접기/펼치기
- Tag `<g>` 기준으로 다음 Tag `<g>` 이전까지의 형제 요소를 같은 그룹에 포함(순차 그룹화)
- 그룹을 ▼/▶ 토글로 접기/펼치기 가능한 트리 구조로 표시

### 6단계 — 순차 형제 하이라이트 수정
- 기존: Tag `<g>` 내부 DOM 자식만 하이라이트
- 수정: `data-tag-group` 속성으로 순차 형제 요소에도 마킹 → 그룹 선택 시 일괄 하이라이트

### 7단계 — Topology 탭 추가
- 사이드바를 Hierarchy / Topology 2-탭 구조로 변경
- `ItemType="PipeRun"` 필터링 기반 Topology 계층 구현

### 8단계 — Topology 그룹 병합 & Zoom-fit
- 동일 이름의 PipeRun 그룹 병합(`data-pr-group`으로 연결)
- Zoom-fit 시 `data-tag-group` + `data-pr-group` 양쪽 BBox 합산

### 9단계 — Seq 기반 하위 계층
- `Seq="TopologyName:sortOrder"` 속성 파싱
- 해당 Topology 그룹 하부에 정렬순서 기준 연결 구성요소 표시
- `ItemType="PipeRun"` 제외 처리

### 10단계 — UI 리디자인
- 앱 쉘 레이아웃(헤더 + 사이드바 + 캔버스 + Inspector)
- CSS 변수 기반 일관된 디자인 시스템
- 선택 모드를 라디오 버튼 → 세그먼트 컨트롤로 교체
- 모달 HTML을 `<script>` 이전으로 이동(DOM 접근 버그 수정)

---

## 브라우저 지원

최신 Chrome / Edge / Firefox / Safari (SVG `getBBox()` API 필요)

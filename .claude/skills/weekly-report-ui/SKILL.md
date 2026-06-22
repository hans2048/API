---
name: weekly-report-ui
description: >
  주간보고 시스템(hans2048/API)의 프론트엔드 UI를 수정할 때 사용.
  report.html은 빌드 없이 동작하는 단일 파일 SPA. 디자인 토큰, 공용 컴포넌트,
  모달/페이지 전환, 테이블·카드·배지·폼 패턴, 한글 동적 렌더링 주의사항 포함.
---

# Weekly Report UI 스킬

## 파일 구조

`report.html` 한 파일에 CSS(`<style>`), HTML, JavaScript(`<script>`)가 모두 포함됨.
빌드 도구 없음. 브라우저에서 직접 열거나 정적 파일로 서빙.

**외부 의존**:
- Google Fonts `Inter` (CDN)
- SortableJS 1.15.2 (CDN, 업무 순서 드래그용)

---

## 디자인 토큰 (CSS 변수)

```css
:root {
  --primary:      #4f46e5;   /* 인디고 — 버튼, 링크, 활성 상태 */
  --primary-dark: #4338ca;   /* 호버 */
  --secondary:    #64748b;   /* 레이블, 보조 텍스트 */
  --success:      #16a34a;
  --danger:       #dc2626;
  --warning:      #d97706;
  --bg:           #f5f6fa;   /* 페이지 배경 */
  --card:         #ffffff;
  --border:       #e5e7eb;
  --text:         #1e293b;
  --muted:        #9ca3af;
  --sidebar-bg:   #1a1f2e;   /* 딥 네이비 사이드바 */
  --sidebar-w:    260px;
}
```

색상 변경 시 `:root`의 변수만 수정하면 전체 반영됨.

---

## 레이아웃 구조

```
#login-screen          ← 로그인 전 전체 화면 (display:flex/none으로 토글)
#app                   ← 로그인 후 앱 화면 (display:block/none으로 토글)
  .topbar              ← 상단 바 (높이 56px, --primary 배경)
  .sidebar             ← 좌측 고정 내비 (너비 260px, --sidebar-bg)
  .main                ← 콘텐츠 영역 (margin-left: 260px, margin-top: 56px)
    .page#page-xxx     ← 각 페이지 (display:none, .active일 때만 표시)
```

**페이지 전환**:
```javascript
function showPage(name) {
  // 모든 .page에서 .active 제거 → #page-{name}에 추가
  // 사이드바 링크 활성화
  // 해당 페이지 데이터 로드 함수 호출
}
// 사용: showPage('weekly') | 'dashboard' | 'org' | 'tasks' | 'users' | 'attachments'
```

**역할별 메뉴 노출**:
```html
<a class="admin-only">...</a>    <!-- admin만 표시 -->
<a class="manager-only">...</a>  <!-- 팀장 이상 표시 -->
```
`startApp()`에서 `ME.role` 기준으로 `.hidden` 클래스 토글.

---

## 공용 컴포넌트

### 버튼
```html
<button class="btn btn-primary">저장</button>
<button class="btn btn-secondary">취소</button>
<button class="btn btn-danger">삭제</button>
<button class="btn btn-outline">편집</button>
<button class="btn btn-success btn-sm">작은 버튼</button>
<button class="btn btn-primary btn-block">전체 너비</button>
```

### 카드
```html
<div class="card">
  <div class="card-header">
    <h3>제목</h3>
    <button class="btn btn-primary btn-sm">+ 추가</button>
  </div>
  <div class="card-body">내용</div>
</div>
```

### 테이블
```html
<div class="table-wrap">
  <table>
    <thead><tr><th>컬럼</th></tr></thead>
    <tbody id="목록-id"></tbody>
  </table>
</div>
```
빈 데이터: `<tr class="empty-row"><td colspan="N">데이터 없음</td></tr>`

### 배지 (badge)
```html
<!-- 역할 배지 -->
<span class="badge badge-admin">시스템Admin</span>
<span class="badge badge-team">팀장</span>
<span class="badge badge-group">그룹장</span>
<span class="badge badge-line">라인장</span>
<span class="badge badge-member">라인원</span>

<!-- Activity 상태 배지 (statusBadge() 함수 사용) -->
<span class="badge badge-done">완료</span>
<span class="badge badge-progress">진행중</span>
<span class="badge badge-pending">예정</span>
<span class="badge badge-hold">보류</span>
```

```javascript
// JS에서 상태 배지 생성
function statusBadge(s) {
  const map = {'완료':'done','진행중':'progress','예정':'pending','보류':'hold'};
  return s ? `<span class="badge badge-${map[s]||'pending'}">${s}</span>` : '-';
}
```

### 폼
```html
<div class="form-group">
  <label>레이블</label>
  <input type="text" id="input-id" />
</div>
<div class="form-group">
  <label>선택</label>
  <select id="select-id"><option value="">선택</option></select>
</div>
```

### 알림 메시지
```html
<div id="err-msg" class="alert alert-error hidden">오류 메시지</div>
<div id="ok-msg"  class="alert alert-success hidden">성공 메시지</div>
```
```javascript
// 표시/숨기기
errEl.textContent = '오류 내용';
errEl.classList.remove('hidden');
okEl.classList.add('hidden');
```

---

## 모달

### HTML 구조
```html
<div class="modal-overlay" id="modal-이름">
  <div class="modal" style="max-width:480px">  <!-- 기본 640px, 필요시 조정 -->
    <div class="modal-header">
      <h3 class="modal-title">제목</h3>
      <button class="modal-close" onclick="closeModal('modal-이름')">×</button>
    </div>
    <div class="modal-body">
      <!-- 폼 내용 -->
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary btn-sm" onclick="closeModal('modal-이름')">취소</button>
      <button class="btn btn-primary btn-sm" onclick="saveXxx()">저장</button>
    </div>
  </div>
</div>
```

### 열기/닫기
```javascript
openModal('modal-이름');   // .open 클래스 추가
closeModal('modal-이름');  // .open 클래스 제거
```

---

## 삭제 공통 함수

```javascript
async function deleteItem(resource, id, reload) {
  if (!confirm('삭제할까요?')) return;
  await api('DELETE', `/wr/${resource}/${id}`).catch(e => alert(e.message));
  reload();
  loadMasterData();
}
// 사용: onclick="deleteItem('tasks', ${r.id}, loadTasks)"
```

---

## 동적 렌더링 주의사항

### 한글 포함 시 DOM 방식 사용

한글이 포함된 데이터를 `innerHTML` 템플릿 리터럴에 직접 삽입하면  
인코딩 오류 또는 `onclick` 문자열 이스케이프 문제 발생.

**금지 패턴** (한글 변수가 onclick에 들어갈 때):
```javascript
// ❌ 한글 파일명이 onclick 속성에 직접 삽입 → 이스케이프 오류
html += `<button onclick="fn('${koreanText}')">클릭</button>`;
```

**권장 패턴** (DOM + addEventListener):
```javascript
const btn = document.createElement('button');
btn.textContent = item.filename;          // 한글 안전
btn.addEventListener('click', () => fn(item.filename));  // 클로저로 캡처
container.appendChild(btn);
```

### note 필드 (리치텍스트)

Activity의 `note`는 `contenteditable` div에서 HTML로 저장됨.
- **저장 시**: `document.getElementById('act-note').innerHTML`
- **화면 출력**: `td.innerHTML = act.note || '-'` (HTML 그대로 렌더링)
- **PPT 변환**: `_strip_html(note)`으로 평문 변환 후 사용

---

## 유틸리티 함수

```javascript
// 역할 레이블
roleLabel('admin')         // → '시스템Admin'
roleLabel('team_leader')   // → '팀장'
roleLabel('group_leader')  // → '그룹장'
roleLabel('line_leader')   // → '라인장'
roleLabel('member')        // → '라인원'

// 그룹 필터 셀렉트 채우기
fillGroupFilter('filter-group-weekly');  // 특정 <select>를 allGroups로 채움

// 숨기기 토글
el.classList.add('hidden');      // display:none
el.classList.remove('hidden');   // 표시
```

---

## 새 페이지/섹션 추가 체크리스트

1. `<div class="page" id="page-이름">` HTML 추가
2. 사이드바에 `<a href="#" onclick="showPage('이름')" id="nav-이름">` 추가
3. `showPage()` 함수에 `if (name==='이름') loadXxx();` 추가
4. 역할 제한 필요 시 `admin-only` 또는 `manager-only` 클래스 추가
5. `startApp()` 호출 흐름에 영향 없는지 확인

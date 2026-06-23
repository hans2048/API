"""
python-pptx 기반 주간보고 PPT 생성.
- 커버 슬라이드 없음
- 그룹별 슬라이드 (업무, Activity, 비고, 일정, 상태, 담당자 순서)
- 첨부파일: 하이퍼링크 텍스트박스로 표시 (클릭 → 서버에서 다운로드)
"""
import re
import datetime
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from lxml import etree

# ── 상수 ─────────────────────────────────────────────────────────────────────
C_HEADER_BG  = RGBColor(0x2E, 0x75, 0xB6)
C_ROW_ODD    = RGBColor(0xD6, 0xE4, 0xF7)
C_ROW_EVEN   = RGBColor(0xFF, 0xFF, 0xFF)
C_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
C_DARK       = RGBColor(0x1F, 0x1F, 0x1F)
C_TITLE_TEXT = RGBColor(0x1F, 0x38, 0x64)
C_MUTED      = RGBColor(0x59, 0x59, 0x59)

STATUS_COLORS = {
    '완료':   RGBColor(0x70, 0xAD, 0x47),
    '진행중': RGBColor(0xFF, 0xC0, 0x00),
    '지연':   RGBColor(0xC0, 0x00, 0x00),
    '예정':   RGBColor(0x5A, 0x96, 0xC8),
}

# 첨부파일 하이퍼링크 색상
C_LINK = RGBColor(0x1F, 0x5C, 0x99)


def _short_name(filename: str, max_len: int = 10) -> str:
    """첨부 표기용 파일명 축약. 확장자는 보존하고 본문이 길면 …로 줄임.
    전체 길이(확장자 포함)를 max_len 이내로 맞춘다."""
    if len(filename) <= max_len:
        return filename
    if '.' in filename:
        base, ext = filename.rsplit('.', 1)
        ext_part = '.' + ext
        # 확장자 + … 를 제외한 본문 가용 길이
        keep = max_len - len(ext_part) - 1   # 1 = '…'
        if keep >= 1:
            return base[:keep] + '…' + ext_part
        # 확장자가 너무 길면 통째로 자름
        return filename[:max_len - 1] + '…'
    return filename[:max_len - 1] + '…'


def _strip_html(text) -> str:
    if not text:
        return ''
    # 블록 태그 닫힘/열림을 줄바꿈으로 변환
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<div[^>]*>', '', text, flags=re.IGNORECASE)
    # 나머지 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 연속 줄바꿈 정리 (3개 이상 → 2개)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _week_date_range(week_label: str) -> str:
    try:
        year_s, wnum_s = week_label.split('-W')
        year, wnum = int(year_s), int(wnum_s)
        mon = datetime.date.fromisocalendar(year, wnum, 1)
        sun = mon + datetime.timedelta(days=6)
        return f"{mon.year}/{mon.month:02d}/{mon.day:02d} ~ {sun.month:02d}/{sun.day:02d}"
    except Exception:
        return ''


# ── 셀 유틸 ──────────────────────────────────────────────────────────────────

def _set_cell_bg(cell, color: RGBColor):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('a:solidFill')):
        tcPr.remove(old)
    sf = etree.SubElement(tcPr, qn('a:solidFill'))
    clr = etree.SubElement(sf, qn('a:srgbClr'))
    clr.set('val', f'{color[0]:02X}{color[1]:02X}{color[2]:02X}')


def _cell_text(cell, text, font_size=Pt(10), bold=False,
               color=C_DARK, align=PP_ALIGN.LEFT):
    """셀에 텍스트 설정. \\n 기준으로 단락 분리."""
    tf = cell.text_frame
    tf.word_wrap = True
    # 기존 단락 모두 제거 후 재생성
    for i in range(len(tf.paragraphs) - 1, -1, -1):
        p_elem = tf.paragraphs[i]._p
        p_elem.getparent().remove(p_elem)

    lines = (str(text) if text is not None else '').split('\n')
    for i, line in enumerate(lines):
        p = tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size = font_size
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = '맑은 고딕'


def _estimate_lines(text: str, col_w_emu: int, font_pt: float = 10.0) -> int:
    """컬럼 폭과 폰트 크기 기반으로 렌더링 줄 수 추정."""
    if not text:
        return 1
    col_inch = col_w_emu / 914400
    chars_per_line = max(8, int(col_inch / (font_pt * 0.007)))  # 경험치
    total = 0
    for line in text.split('\n'):
        total += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
    return total


# ── 슬라이드 생성 ─────────────────────────────────────────────────────────────

def _build_slide(prs: Presentation, grp_name: str, week_label: str, tasks: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    W, H = prs.slide_width, prs.slide_height
    mx = Inches(0.4)
    table_w = W - mx * 2

    date_range = _week_date_range(week_label)
    title_text = f'{grp_name}   |   {week_label}'
    if date_range:
        title_text += f'  ({date_range})'

    # 제목
    tb = slide.shapes.add_textbox(mx, Inches(0.12), table_w, Inches(0.48))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title_text
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = C_TITLE_TEXT
    run.font.name = '맑은 고딕'

    # 구분선
    ln = slide.shapes.add_shape(1, mx, Inches(0.62), table_w, Emu(0))
    ln.line.color.rgb = C_HEADER_BG
    ln.line.width = Pt(1.5)

    # 행 데이터 수집 (첨부파일 리스트 포함, 셀 텍스트에는 📎 파일명 표기)
    rows_data = []
    for task in tasks:
        acts = task.get('activities', [])
        if not acts:
            rows_data.append({
                'task': task['name'], 'name': '', 'note': '',
                'schedule': '', 'status': '', 'assignees': '',
                'attachments': [],
            })
        else:
            for i, act in enumerate(acts):
                att = act.get('attachments', [])
                act_text = act.get('name', '')
                # 📎 텍스트 제거 — OLE 아이콘으로만 표시
                rows_data.append({
                    'task': task['name'] if i == 0 else '',
                    'name': act_text,
                    'note': _strip_html(act.get('note', '')),
                    'schedule': act.get('schedule') or '',
                    'status': act.get('status') or '',
                    'assignees': act.get('assignee_names') or '',
                    'attachments': att,
                })

    n_rows = max(len(rows_data), 1) + 1
    table_top = Inches(0.70)

    # 컬럼 비율: 업무(1.5), Activity(1.5), 비고(5), 일정(1), 상태(1), 담당자(1)
    ratios = [1.5, 1.5, 5, 1, 1, 1]
    total_r = sum(ratios)
    col_widths = [int(table_w * r / total_r) for r in ratios]
    col_widths[-1] = table_w - sum(col_widths[:-1])

    # ── 행 높이를 내용 기반으로 동적 계산 ──────────────────────────────────────
    # OLE 배치를 위해 각 행의 y좌표를 정확히 알아야 하므로
    # 자동높이 대신 내용 줄 수로 추정한 높이를 명시적으로 설정
    LINE_H   = int(Pt(11))
    CELL_PAD = int(Pt(8))
    OLE_EXTRA = int(Inches(0.16))   # 첨부 아이콘 + 레이블 확보 공간 (항목당 0.13")
    MIN_ROW_H = int(Pt(32))

    header_h_emu = int(Pt(20))

    row_heights = []
    for row in rows_data:
        has_att = bool(row.get('attachments'))
        task_lines = _estimate_lines(row['task'],  col_widths[0])
        name_lines = _estimate_lines(row['name'],  col_widths[1])
        note_lines = _estimate_lines(row['note'],  col_widths[2])
        sche_lines = _estimate_lines(row['schedule'], col_widths[3])
        content_h  = max(task_lines, name_lines, note_lines, sche_lines) * LINE_H + CELL_PAD
        if has_att:
            content_h += OLE_EXTRA
        row_heights.append(max(MIN_ROW_H, content_h))

    if not row_heights:
        row_heights = [MIN_ROW_H]

    table_h = header_h_emu + sum(row_heights)
    # 슬라이드 하단을 넘지 않도록 클리핑
    max_table_h = int(H - table_top - Inches(0.10))
    if table_h > max_table_h:
        scale = max_table_h / table_h
        row_heights = [max(MIN_ROW_H, int(h * scale)) for h in row_heights]
        table_h = header_h_emu + sum(row_heights)

    tbl_shape = slide.shapes.add_table(n_rows, 6, mx, table_top, table_w, table_h)
    tbl = tbl_shape.table

    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = cw

    tbl.rows[0].height = header_h_emu
    for ri, rh in enumerate(row_heights):
        tbl.rows[ri + 1].height = rh

    headers = ['업무', 'Activity', '비고', '일정', '상태', '담당자']
    for ci, h in enumerate(headers):
        cell = tbl.cell(0, ci)
        _set_cell_bg(cell, C_HEADER_BG)
        _cell_text(cell, h, font_size=Pt(10), bold=True,
                   color=C_WHITE, align=PP_ALIGN.CENTER)
        cell.margin_top = Pt(2)
        cell.margin_bottom = Pt(2)
        cell.margin_left = Pt(3)
        cell.margin_right = Pt(3)

    for ri, row in enumerate(rows_data, start=1):
        bg = C_ROW_ODD if ri % 2 == 1 else C_ROW_EVEN
        vals = [row['task'], row['name'], row['note'], row['schedule'],
                row['status'], row['assignees']]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri, ci)
            _set_cell_bg(cell, bg)
            if ci == 4 and val in STATUS_COLORS:
                _cell_text(cell, val, font_size=Pt(10), bold=True,
                           color=STATUS_COLORS[val], align=PP_ALIGN.CENTER)
            elif ci in (3, 4):
                _cell_text(cell, val, font_size=Pt(10), align=PP_ALIGN.CENTER)
            else:
                _cell_text(cell, val, font_size=Pt(10))
            cell.margin_top = Pt(2)
            cell.margin_bottom = Pt(2)
            cell.margin_left = Pt(3)
            cell.margin_right = Pt(3)

    if not rows_data:
        cell = tbl.cell(1, 0)
        _cell_text(cell, '등록된 Activity가 없습니다',
                   color=C_MUTED, align=PP_ALIGN.CENTER)

    # ── 첨부파일 하이퍼링크: Activity 행 하단에 세로로 나열 ──────────────────────
    # Activity 컬럼 좌표 (인덱스 1)
    act_col_x = int(mx) + col_widths[0]
    act_col_w = col_widths[1]
    lnk_h     = int(Inches(0.13))   # 링크 텍스트박스 높이
    lnk_gap   = int(Inches(0.02))   # 항목 간격
    lnk_x     = act_col_x + int(Inches(0.04))
    lnk_w     = act_col_w - int(Inches(0.08))

    y_cursor = int(table_top) + header_h_emu
    for di, row in enumerate(rows_data):
        rh = row_heights[di]
        att_list = row.get('attachments', [])

        if att_list:
            att_block_h = len(att_list) * (lnk_h + lnk_gap)
            att_y = y_cursor + rh - att_block_h - lnk_gap

            for att in att_list:
                tb = slide.shapes.add_textbox(lnk_x, att_y, lnk_w, lnk_h)
                tf = tb.text_frame
                tf.word_wrap = False
                tf.margin_left = 0
                tf.margin_right = 0
                tf.margin_top = 0
                tf.margin_bottom = 0
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                run = p.add_run()
                run.text = '📎 ' + _short_name(att['filename'], 10)
                run.font.size = Pt(7)
                run.font.color.rgb = C_LINK
                run.font.underline = True
                run.font.name = '맑은 고딕'
                # 하이퍼링크 연결
                run.hyperlink.address = att.get('url', '')

                att_y += lnk_h + lnk_gap

        y_cursor += rh

    return slide


# ── 메인 빌더 ─────────────────────────────────────────────────────────────────

def build_pptx(week_label: str, groups: list) -> bytes:
    prs = Presentation()
    prs.slide_width  = Inches(13.33)
    prs.slide_height = Inches(7.5)

    for grp in groups:
        _build_slide(prs, grp['name'], week_label, grp['tasks'])

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()

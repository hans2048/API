"""
python-pptx 기반 주간보고 PPT 생성.
- 커버 슬라이드 없음
- 그룹별 슬라이드 (Activity, 비고, 일정, 상태, 담당자 순서)
- 첨부파일: Activity 셀에 파일명 텍스트로 표기 (📎 filename)
"""
import re
import io
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


def _ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _strip_html(text) -> str:
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _week_date_range(week_label: str) -> str:
    """'2026-W24' → '2026/06/08 ~ 06/14'"""
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


def _cell_text(cell, text, font_size=Pt(9), bold=False,
               color=C_DARK, align=PP_ALIGN.LEFT):
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    for r in p.runs:
        p._p.remove(r._r)
    run = p.add_run()
    run.text = str(text) if text is not None else ''
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = '맑은 고딕'


# ── python-pptx 슬라이드 생성 ────────────────────────────────────────────────

def _build_slide(prs: Presentation, grp_name: str, week_label: str, tasks: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    W, H = prs.slide_width, prs.slide_height
    mx = Inches(0.4)
    table_w = W - mx * 2

    # 날짜 범위
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

    # 행 데이터 수집
    rows_data = []
    for task in tasks:
        acts = task.get('activities', [])
        if not acts:
            rows_data.append({
                'task': task['name'], 'name': '', 'note': '',
                'schedule': '', 'status': '', 'assignees': '',
            })
        else:
            for i, act in enumerate(acts):
                att = act.get('attachments', [])
                act_text = act.get('name', '')
                if att:
                    fnames = ', '.join(a['filename'] for a in att)
                    act_text += f'\n📎 {fnames}'
                rows_data.append({
                    'task': task['name'] if i == 0 else '',
                    'name': act_text,
                    'note': _strip_html(act.get('note', '')),
                    'schedule': act.get('schedule') or '',
                    'status': act.get('status') or '',
                    'assignees': act.get('assignee_names') or '',
                })

    n_rows = max(len(rows_data), 1) + 1

    # 테이블 높이 (슬라이드 전체에서 제목/구분선 영역 제외)
    table_top = Inches(0.70)
    table_h = H - table_top - Inches(0.15)

    # 컬럼 비율: Activity(2), 비고(5), 일정(1.5), 상태(1), 담당자(1)
    ratios = [2, 5, 1.5, 1, 1]
    total_r = sum(ratios)
    col_widths = [int(table_w * r / total_r) for r in ratios]
    col_widths[-1] = table_w - sum(col_widths[:-1])

    tbl_shape = slide.shapes.add_table(n_rows, 5, mx, table_top, table_w, table_h)
    tbl = tbl_shape.table

    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = cw
    tbl.rows[0].height = Pt(16)

    headers = ['Activity', '비고', '일정', '상태', '담당자']
    for ci, h in enumerate(headers):
        cell = tbl.cell(0, ci)
        _set_cell_bg(cell, C_HEADER_BG)
        _cell_text(cell, h, font_size=Pt(9), bold=True,
                   color=C_WHITE, align=PP_ALIGN.CENTER)
        cell.margin_top = Pt(2)
        cell.margin_bottom = Pt(2)
        cell.margin_left = Pt(3)
        cell.margin_right = Pt(3)

    for ri, row in enumerate(rows_data, start=1):
        bg = C_ROW_ODD if ri % 2 == 1 else C_ROW_EVEN
        vals = [row['name'], row['note'], row['schedule'],
                row['status'], row['assignees']]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri, ci)
            _set_cell_bg(cell, bg)
            if ci == 3 and val in STATUS_COLORS:
                _cell_text(cell, val, font_size=Pt(9), bold=True,
                           color=STATUS_COLORS[val], align=PP_ALIGN.CENTER)
            elif ci in (2, 3):
                _cell_text(cell, val, font_size=Pt(9), align=PP_ALIGN.CENTER)
            else:
                _cell_text(cell, val, font_size=Pt(9))
            cell.margin_top = Pt(2)
            cell.margin_bottom = Pt(2)
            cell.margin_left = Pt(3)
            cell.margin_right = Pt(3)

    if not rows_data:
        cell = tbl.cell(1, 0)
        _cell_text(cell, '등록된 Activity가 없습니다',
                   color=C_MUTED, align=PP_ALIGN.CENTER)


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

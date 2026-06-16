"""
python-pptx 기반 주간보고 PPT 생성.
"""
import re
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


# ── 컬러 팔레트 ───────────────────────────────────────────────────────────────
C_TITLE_BG   = RGBColor(0x1F, 0x38, 0x64)   # 진남색 (타이틀 배경)
C_HEADER_BG  = RGBColor(0x2E, 0x75, 0xB6)   # 헤더 파란색
C_ROW_ODD    = RGBColor(0xD6, 0xE4, 0xF7)   # 홀수행 옅은 파랑
C_ROW_EVEN   = RGBColor(0xFF, 0xFF, 0xFF)   # 짝수행 흰색
C_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
C_DARK       = RGBColor(0x1F, 0x1F, 0x1F)
C_MUTED      = RGBColor(0x59, 0x59, 0x59)
C_ACCENT     = RGBColor(0x4A, 0x72, 0xC4)

# 상태별 색상
STATUS_COLORS = {
    '완료':   RGBColor(0x70, 0xAD, 0x47),
    '진행중': RGBColor(0xFF, 0xC0, 0x00),
    '지연':   RGBColor(0xFF, 0x00, 0x00),
    '예정':   RGBColor(0x5A, 0x96, 0xC8),
}


def _strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _set_cell_bg(cell, color: RGBColor):
    from pptx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    solidFill = etree.SubElement(tcPr, qn('a:solidFill'))
    srgbClr = etree.SubElement(solidFill, qn('a:srgbClr'))
    srgbClr.set('val', f'{color[0]:02X}{color[1]:02X}{color[2]:02X}')


def _cell_text(cell, text, font_size=Pt(9), bold=False,
               color=C_DARK, align=PP_ALIGN.LEFT, wrap=True):
    tf = cell.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = str(text) if text else ''
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = '맑은 고딕'


def _add_title_slide(prs: Presentation, week_label: str, group_names: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    # 배경 전체 색
    from pptx.oxml.ns import qn
    from lxml import etree
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = C_TITLE_BG

    W, H = prs.slide_width, prs.slide_height
    margin = Inches(0.8)

    # 주 제목
    tb = slide.shapes.add_textbox(margin, H * 35 // 100, W - margin * 2, Inches(1.2))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = '주간 업무 보고'
    run.font.size = Pt(40)
    run.font.bold = True
    run.font.color.rgb = C_WHITE
    run.font.name = '맑은 고딕'

    # 주차 레이블
    tb2 = slide.shapes.add_textbox(margin, H * 55 // 100, W - margin * 2, Inches(0.7))
    tf2 = tb2.text_frame
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run()
    r2.text = week_label
    r2.font.size = Pt(28)
    r2.font.color.rgb = C_ACCENT
    r2.font.name = '맑은 고딕'

    # 그룹명
    if group_names:
        tb3 = slide.shapes.add_textbox(margin, H * 68 // 100, W - margin * 2, Inches(0.5))
        tf3 = tb3.text_frame
        p3 = tf3.paragraphs[0]
        p3.alignment = PP_ALIGN.CENTER
        r3 = p3.add_run()
        r3.text = ' · '.join(group_names)
        r3.font.size = Pt(16)
        r3.font.color.rgb = RGBColor(0xBD, 0xCE, 0xE8)
        r3.font.name = '맑은 고딕'


def _add_group_slide(prs: Presentation, grp_name: str, week_label: str, tasks: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    W, H = prs.slide_width, prs.slide_height
    margin_x = Inches(0.4)
    table_w = W - margin_x * 2

    # ── 헤더 제목 텍스트박스 ──────────────────────────────────────────────────
    tb = slide.shapes.add_textbox(margin_x, Inches(0.15), table_w, Inches(0.55))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = f'{grp_name}   |   {week_label}'
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = C_TITLE_BG
    run.font.name = '맑은 고딕'

    # ── 구분선 ──────────────────────────────────────────────────────────────
    from pptx.oxml.ns import qn
    from lxml import etree
    ln_shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.LINE is not directly importable; use connector
        margin_x, Inches(0.72), table_w, Emu(0)
    )
    ln_shape.line.color.rgb = C_HEADER_BG
    ln_shape.line.width = Pt(2)

    # ── 행 데이터 수집 ────────────────────────────────────────────────────────
    rows_data = []
    for task in tasks:
        task_name = task['name']
        acts = task.get('activities', [])
        if not acts:
            rows_data.append({
                'task': task_name, 'name': '', 'schedule': '',
                'status': '', 'assignees': '', 'note': '', 'first': True
            })
        else:
            for i, act in enumerate(acts):
                rows_data.append({
                    'task': task_name if i == 0 else '',
                    'name': act.get('name', ''),
                    'schedule': act.get('schedule') or '',
                    'status': act.get('status') or '',
                    'assignees': act.get('assignee_names') or '',
                    'note': _strip_html(act.get('note', '')),
                    'first': i == 0,
                })

    n_rows = len(rows_data) + 1  # +1 헤더
    if n_rows < 2:
        n_rows = 2

    table_top = Inches(0.82)
    table_h = H - table_top - Inches(0.15)

    # ── 컬럼 너비 (비율 업무:2 Activity:4 일정:1.5 상태:1 담당자:1.5 비고:3) ──
    total = 13.0
    col_widths = [
        int(table_w * 2   / total),
        int(table_w * 4   / total),
        int(table_w * 1.5 / total),
        int(table_w * 1   / total),
        int(table_w * 1.5 / total),
        int(table_w - int(table_w*2/total) - int(table_w*4/total)
            - int(table_w*1.5/total) - int(table_w*1/total) - int(table_w*1.5/total)),
    ]

    tbl = slide.shapes.add_table(n_rows, 6, margin_x, table_top, table_w, table_h).table

    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = cw

    # 헤더
    headers = ['업무', 'Activity명', '일정', '상태', '담당자', '비고']
    for ci, h in enumerate(headers):
        cell = tbl.cell(0, ci)
        _set_cell_bg(cell, C_HEADER_BG)
        _cell_text(cell, h, font_size=Pt(10), bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        cell.margin_top = Pt(3)
        cell.margin_bottom = Pt(3)

    # 데이터 행
    for ri, row in enumerate(rows_data, start=1):
        bg = C_ROW_ODD if ri % 2 == 1 else C_ROW_EVEN
        vals = [row['task'], row['name'], row['schedule'],
                row['status'], row['assignees'], row['note']]
        for ci, val in enumerate(vals):
            cell = tbl.cell(ri, ci)
            _set_cell_bg(cell, bg)
            # 상태 컬럼은 색상 강조
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

    # 데이터가 없을 때
    if len(rows_data) == 0:
        cell = tbl.cell(1, 0)
        _cell_text(cell, '등록된 Activity가 없습니다', color=C_MUTED, align=PP_ALIGN.CENTER)


def build_pptx(week_label: str, groups: list) -> bytes:
    prs = Presentation()
    prs.slide_width  = Inches(13.33)   # 와이드 16:9
    prs.slide_height = Inches(7.5)

    group_names = [g['name'] for g in groups]
    _add_title_slide(prs, week_label, group_names)

    for grp in groups:
        _add_group_slide(prs, grp['name'], week_label, grp['tasks'])

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()

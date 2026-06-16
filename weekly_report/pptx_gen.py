"""
python-pptx 기반 주간보고 PPT 생성.
- 커버 슬라이드 없음
- 그룹별 슬라이드 (Activity, 비고, 일정, 상태, 담당자 순서)
- 첨부파일: add_ole_object() API로 OLE 삽입, Activity 컬럼 하단 배치
"""
import re
import io
import struct
import zlib
import datetime
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import PROG_ID
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

# 확장자 → (PROG_ID 또는 prog_id 문자열, 아이콘 RGB)
_EXT_INFO = {
    'xlsx':  (PROG_ID.XLSX,          (0x21, 0x7B, 0x45)),  # 초록
    'xls':   ('Excel.Sheet.8',       (0x21, 0x7B, 0x45)),
    'csv':   (PROG_ID.XLSX,          (0x21, 0x7B, 0x45)),  # Excel로 열기
    'docx':  (PROG_ID.DOCX,          (0x18, 0x5A, 0xBD)),  # 파랑
    'doc':   ('Word.Document.8',     (0x18, 0x5A, 0xBD)),
    'pptx':  (PROG_ID.PPTX,          (0xC4, 0x3E, 0x00)),  # 주황
    'ppt':   ('PowerPoint.Show.8',   (0xC4, 0x3E, 0x00)),
    'pdf':   ('AcroExch.Document',   (0xD0, 0x22, 0x1B)),  # 빨강
    'hwp':   ('HWPFile',             (0x00, 0x5B, 0x99)),  # 하늘
    'hwpx':  ('HWPX.Document',       (0x00, 0x5B, 0x99)),
    'txt':   ('txtfile',             (0x60, 0x60, 0x60)),  # 회색
    'png':   ('PBrush',              (0x88, 0x44, 0xBB)),  # 보라
    'jpg':   ('PBrush',              (0x88, 0x44, 0xBB)),
    'jpeg':  ('PBrush',              (0x88, 0x44, 0xBB)),
    'gif':   ('PBrush',              (0x88, 0x44, 0xBB)),
    'bmp':   ('PBrush',              (0x88, 0x44, 0xBB)),
}
_DEFAULT_INFO = (PROG_ID.XLSX, (0x80, 0x80, 0x80))  # 알 수 없는 형식은 Excel 컨테이너


def _ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _strip_html(text) -> str:
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _week_date_range(week_label: str) -> str:
    try:
        year_s, wnum_s = week_label.split('-W')
        year, wnum = int(year_s), int(wnum_s)
        mon = datetime.date.fromisocalendar(year, wnum, 1)
        sun = mon + datetime.timedelta(days=6)
        return f"{mon.year}/{mon.month:02d}/{mon.day:02d} ~ {sun.month:02d}/{sun.day:02d}"
    except Exception:
        return ''


def _make_icon_png(r: int, g: int, b: int, w: int = 48, h: int = 48) -> bytes:
    """순색 PNG 아이콘을 메모리에서 생성 (외부 파일 불필요)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    raw = b''.join(b'\x00' + bytes([r, g, b] * w) for _ in range(h))
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', zlib.compress(raw))
        + chunk(b'IEND', b'')
    )


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

    # 행 데이터 수집
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
                    'attachments': att,
                })

    n_rows = max(len(rows_data), 1) + 1

    # 첨부파일 존재 여부 미리 파악 → 테이블 높이 조정
    all_att = []
    for task in tasks:
        for act in task.get('activities', []):
            all_att.extend(act.get('attachments', []))

    obj_h   = Inches(0.9)
    ole_gap = Inches(0.08)
    table_top = Inches(0.70)
    if all_att:
        table_h = H - table_top - obj_h - ole_gap * 2
    else:
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

    # OLE 첨부 삽입 — 테이블 바로 아래, Activity 컬럼 x 범위 내
    if all_att:
        obj_w     = Inches(1.0)
        act_col_x = int(mx)
        act_col_w = col_widths[0]
        tbl_bottom = int(table_top) + int(table_h)
        x_pos = act_col_x
        y_pos = tbl_bottom + int(ole_gap)

        label_h = Inches(0.22)
        for att in all_att:
            if x_pos + int(obj_w) > act_col_x + act_col_w:
                x_pos = act_col_x
                y_pos += int(obj_h) + int(label_h) + int(ole_gap)

            ext = _ext(att['filename'])
            prog_id, (ir, ig, ib) = _EXT_INFO.get(ext, _DEFAULT_INFO)
            icon_png = _make_icon_png(ir, ig, ib)

            try:
                slide.shapes.add_ole_object(
                    object_file=io.BytesIO(bytes(att['data'])),
                    prog_id=prog_id,
                    left=x_pos,
                    top=y_pos,
                    width=int(obj_w),
                    height=int(obj_h),
                    icon_file=io.BytesIO(icon_png),
                )
            except Exception:
                pass

            # 파일명 레이블
            tb = slide.shapes.add_textbox(
                x_pos, y_pos + int(obj_h), int(obj_w), int(label_h)
            )
            tf = tb.text_frame
            tf.word_wrap = False
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = att['filename']
            run.font.size = Pt(7)
            run.font.color.rgb = C_DARK
            run.font.name = '맑은 고딕'

            x_pos += int(obj_w) + int(ole_gap)

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

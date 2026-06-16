"""
python-pptx 기반 주간보고 PPT 생성.
- 커버 슬라이드 없음
- 그룹별 슬라이드 (Activity, 비고, 일정, 상태, 담당자 순서)
- 첨부파일: 이미지는 사진으로, 기타 파일은 OLE 객체 삽입
"""
import re
from io import BytesIO

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from lxml import etree

# ── 컬러 팔레트 ───────────────────────────────────────────────────────────────
C_HEADER_BG  = RGBColor(0x2E, 0x75, 0xB6)
C_ROW_ODD    = RGBColor(0xD6, 0xE4, 0xF7)
C_ROW_EVEN   = RGBColor(0xFF, 0xFF, 0xFF)
C_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
C_DARK       = RGBColor(0x1F, 0x1F, 0x1F)
C_TITLE_TEXT = RGBColor(0x1F, 0x38, 0x64)
C_MUTED      = RGBColor(0x59, 0x59, 0x59)
C_ATTACH_BG  = RGBColor(0xF2, 0xF2, 0xF2)

STATUS_COLORS = {
    '완료':   RGBColor(0x70, 0xAD, 0x47),
    '진행중': RGBColor(0xFF, 0xC0, 0x00),
    '지연':   RGBColor(0xC0, 0x00, 0x00),
    '예정':   RGBColor(0x5A, 0x96, 0xC8),
}

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp'}

# OLE progId 매핑
OLE_PROG_IDS = {
    'pdf':  'AcroExch.Document',
    'docx': 'Word.Document.12',
    'doc':  'Word.Document.8',
    'xlsx': 'Excel.Sheet.12',
    'xls':  'Excel.Sheet.8',
    'pptx': 'PowerPoint.Show.12',
    'ppt':  'PowerPoint.Show.8',
    'hwp':  'HWPFile',
    'hwpx': 'HWPX.Document',
    'txt':  'txtfile',
}

OLE_CONTENT_TYPES = {
    'pdf':  'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc':  'application/msword',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls':  'application/vnd.ms-excel',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'hwp':  'application/x-hwp',
    'txt':  'text/plain',
}


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


# ── 셀 유틸 ──────────────────────────────────────────────────────────────────

def _set_cell_bg(cell, color: RGBColor):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # 기존 solidFill 제거
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
    # 기존 런 제거
    for r in p.runs:
        p._p.remove(r._r)
    run = p.add_run()
    run.text = str(text) if text is not None else ''
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = '맑은 고딕'


# ── OLE 객체 삽입 ─────────────────────────────────────────────────────────────

def _add_ole_object(slide, data: bytes, filename: str, x, y, cx, cy, sp_id: int):
    """python-pptx 내부 API로 OLE 객체를 슬라이드에 삽입."""
    from pptx.opc.part import Part
    from pptx.opc.packuri import PackURI

    ext = _ext(filename)
    content_type = OLE_CONTENT_TYPES.get(ext, 'application/octet-stream')
    prog_id = OLE_PROG_IDS.get(ext, 'Package')

    # 안전한 파트 이름 생성 (공백·특수문자 제거)
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    part_uri = PackURI(f'/ppt/embeddings/{sp_id}_{safe}')

    emb_part = Part(part_uri, content_type, data)
    rId = slide.part.relate_to(
        emb_part,
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject',
    )

    ns_p = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    xml = (
        f'<p:graphicFrame xmlns:p="{ns_p}" xmlns:a="{ns_a}" xmlns:r="{ns_r}">'
        f'<p:nvGraphicFramePr>'
        f'<p:cNvPr id="{sp_id}" name="{filename}"/>'
        f'<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
        f'<p:nvPr/>'
        f'</p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic>'
        f'<a:graphicData uri="http://schemas.openxmlformats.org/presentationml/2006/ole">'
        f'<p:oleObj name="{filename}" showAsIcon="1" r:id="{rId}"'
        f' imgW="{cx}" imgH="{cy}" progId="{prog_id}">'
        f'<p:embed/>'
        f'</p:oleObj>'
        f'</a:graphicData>'
        f'</a:graphic>'
        f'</p:graphicFrame>'
    )
    slide.shapes._spTree.append(etree.fromstring(xml))


# ── 슬라이드 생성 ─────────────────────────────────────────────────────────────

def _add_group_slide(prs: Presentation, grp_name: str, week_label: str,
                     tasks: list, slide_no: int):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    W, H = prs.slide_width, prs.slide_height
    mx = Inches(0.4)          # 좌우 여백
    table_w = W - mx * 2

    # ── 제목 ───────────────────────────────────────────────────────────────
    tb = slide.shapes.add_textbox(mx, Inches(0.12), table_w, Inches(0.48))
    tf = tb.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = f'{grp_name}   |   {week_label}'
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = C_TITLE_TEXT
    run.font.name = '맑은 고딕'

    # 구분선
    ln = slide.shapes.add_shape(1, mx, Inches(0.62), table_w, Emu(0))
    ln.line.color.rgb = C_HEADER_BG
    ln.line.width = Pt(1.5)

    # ── 행 데이터 수집 ─────────────────────────────────────────────────────
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
                rows_data.append({
                    'task': task['name'] if i == 0 else '',
                    'name': act.get('name', ''),
                    'note': _strip_html(act.get('note', '')),
                    'schedule': act.get('schedule') or '',
                    'status': act.get('status') or '',
                    'assignees': act.get('assignee_names') or '',
                    'attachments': act.get('attachments', []),
                })

    n_rows = max(len(rows_data), 1) + 1  # +1 헤더

    # ── 테이블 ─────────────────────────────────────────────────────────────
    table_top = Inches(0.70)

    # 첨부 섹션에 필요한 높이 계산
    all_attachments = [a for r in rows_data for a in r['attachments']]
    attach_section_h = Inches(1.6) * len(all_attachments) if all_attachments else Emu(0)
    attach_section_h = min(attach_section_h, Inches(3.0))  # 최대 3인치

    table_h = H - table_top - Inches(0.15) - attach_section_h

    # 컬럼 비율: Activity(2), 비고(5), 일정(1.5), 상태(1), 담당자(1) 합계 10.5
    ratios = [2, 5, 1.5, 1, 1]
    total_r = sum(ratios)
    col_widths = [int(table_w * r / total_r) for r in ratios]
    # 마지막 컬럼에 나머지 할당
    col_widths[-1] = table_w - sum(col_widths[:-1])

    tbl_shape = slide.shapes.add_table(n_rows, 5, mx, table_top, table_w, table_h)
    tbl = tbl_shape.table

    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = cw

    # 헤더 행 높이 자동맞춤 (작게 고정)
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

    # 데이터 행
    for ri, row in enumerate(rows_data, start=1):
        bg = C_ROW_ODD if ri % 2 == 1 else C_ROW_EVEN
        # 첨부파일이 있는 경우 Activity 셀에 📎 표시
        act_text = row['name']
        if row['attachments']:
            act_text += f"\n📎 {len(row['attachments'])}개 첨부"

        vals = [act_text, row['note'], row['schedule'], row['status'], row['assignees']]
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
        _cell_text(cell, '등록된 Activity가 없습니다', color=C_MUTED,
                   align=PP_ALIGN.CENTER)

    # ── 첨부파일 삽입 ───────────────────────────────────────────────────────
    if all_attachments:
        attach_y = H - attach_section_h - Inches(0.05)

        # "첨부파일" 레이블
        lbl = slide.shapes.add_textbox(mx, attach_y, table_w, Inches(0.28))
        lf = lbl.text_frame.paragraphs[0]
        r = lf.add_run()
        r.text = '첨부파일'
        r.font.size = Pt(10)
        r.font.bold = True
        r.font.color.rgb = C_TITLE_TEXT
        r.font.name = '맑은 고딕'
        attach_y += Inches(0.30)

        obj_w = Inches(1.4)
        obj_h = Inches(1.2)
        gap   = Inches(0.15)
        x_pos = mx
        sp_counter = 200 + slide_no * 50  # 고유 sp_id

        for att in all_attachments:
            fname   = att['filename']
            data    = att['data']
            ext     = _ext(fname)

            if x_pos + obj_w > W - mx:
                x_pos = mx
                attach_y += obj_h + gap

            if ext in IMAGE_EXTS:
                try:
                    pic = slide.shapes.add_picture(
                        BytesIO(data), x_pos, attach_y, obj_w, obj_h
                    )
                    # 파일명 라벨
                    lb = slide.shapes.add_textbox(
                        x_pos, attach_y + obj_h, obj_w, Inches(0.22)
                    )
                    lr = lb.text_frame.paragraphs[0]
                    lr.alignment = PP_ALIGN.CENTER
                    rn = lr.add_run()
                    rn.text = fname[:20] + ('…' if len(fname) > 20 else '')
                    rn.font.size = Pt(7)
                    rn.font.color.rgb = C_MUTED
                    rn.font.name = '맑은 고딕'
                except Exception:
                    pass
            else:
                try:
                    _add_ole_object(
                        slide, data, fname,
                        x_pos, attach_y, obj_w, obj_h, sp_counter
                    )
                    sp_counter += 1
                    # 파일명 라벨
                    lb = slide.shapes.add_textbox(
                        x_pos, attach_y + obj_h, obj_w, Inches(0.22)
                    )
                    lr = lb.text_frame.paragraphs[0]
                    lr.alignment = PP_ALIGN.CENTER
                    rn = lr.add_run()
                    rn.text = fname[:20] + ('…' if len(fname) > 20 else '')
                    rn.font.size = Pt(7)
                    rn.font.color.rgb = C_MUTED
                    rn.font.name = '맑은 고딕'
                except Exception:
                    pass

            x_pos += obj_w + gap


# ── 메인 빌더 ─────────────────────────────────────────────────────────────────

def build_pptx(week_label: str, groups: list) -> bytes:
    prs = Presentation()
    prs.slide_width  = Inches(13.33)
    prs.slide_height = Inches(7.5)

    for idx, grp in enumerate(groups, start=1):
        _add_group_slide(prs, grp['name'], week_label, grp['tasks'], idx)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()

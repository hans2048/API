"""
python-pptx 기반 주간보고 PPT 생성.
- 커버 슬라이드 없음
- 그룹별 슬라이드 (Activity, 비고, 일정, 상태, 담당자 순서)
- 첨부파일: 모두 OLE 객체 삽입 (zipfile 직접 조작으로 확실히 embed)
- 첨부 아이콘은 Activity 컬럼 영역 내 테이블 아래 배치
"""
import re
import io
import zipfile
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

# OLE 관련 매핑
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
    'jpg':  'PBrush',
    'jpeg': 'PBrush',
    'png':  'PBrush',
    'gif':  'PBrush',
    'bmp':  'PBrush',
}

OLE_CONTENT_TYPES = {
    'pdf':  'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc':  'application/msword',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls':  'application/vnd.ms-excel',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'hwp':  'application/x-hwp',
    'hwpx': 'application/x-hwpx',
    'txt':  'text/plain',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'png':  'image/png',
    'gif':  'image/gif',
    'bmp':  'image/bmp',
}

NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
OLE_RELTYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject'


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


# ── python-pptx 슬라이드 생성 (첨부 없이) ────────────────────────────────────

def _build_slide(prs: Presentation, grp_name: str, week_label: str, tasks: list):
    """슬라이드를 추가하고, Activity 컬럼 영역 정보(x, y_bottom, col_w)를 반환."""
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

    # Activity 컬럼 영역 정보 반환 (OLE 배치용)
    act_col_x = int(mx)
    act_col_w = col_widths[0]
    return slide, act_col_x, act_col_w


# ── zipfile 직접 조작으로 OLE 삽입 (바이트 치환 — XML 재직렬화 없음) ──────────

def _inject_ole_objects(pptx_bytes: bytes, slide_ole_map: dict) -> bytes:
    """
    lxml 재직렬화 없이 바이트 문자열 치환으로 OLE 삽입.
    (재직렬화 시 네임스페이스 변경으로 PPT 손상되는 문제 방지)
    """
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(pptx_bytes), 'r') as zin:
        for name in zin.namelist():
            files[name] = zin.read(name)

    for slide_num, ole_items in slide_ole_map.items():
        if not ole_items:
            continue

        slide_key = f'ppt/slides/slide{slide_num}.xml'
        rels_key  = f'ppt/slides/_rels/slide{slide_num}.xml.rels'
        if slide_key not in files:
            continue

        slide_bytes = files[slide_key]
        rels_bytes  = files[rels_key]

        # 기존 최대 id / rId를 정규식으로 파악
        max_sp_id = max(
            (int(m) for m in re.findall(rb' id="(\d+)"', slide_bytes)),
            default=100,
        )
        max_rid = max(
            (int(m) for m in re.findall(rb'Id="rId(\d+)"', rels_bytes)),
            default=10,
        )

        new_shapes = b''
        new_rels   = b''

        for item in ole_items:
            fname = item['filename']
            data  = bytes(item['data'])
            x, y, cx, cy = item['x'], item['y'], item['cx'], item['cy']

            ext      = _ext(fname)
            ct       = OLE_CONTENT_TYPES.get(ext, 'application/octet-stream')
            prog_id  = OLE_PROG_IDS.get(ext, 'Package')
            safe     = re.sub(r'[^A-Za-z0-9._-]', '_', fname)
            fname_e  = fname.replace('&', '&amp;').replace('"', '&quot;')

            max_rid   += 1
            max_sp_id += 1
            rId      = f'rId{max_rid}'
            emb_rel  = f'../embeddings/slide{slide_num}_{max_rid}_{safe}'
            emb_key  = f'ppt/embeddings/slide{slide_num}_{max_rid}_{safe}'
            files[emb_key] = data

            # Relationship 엔트리
            new_rels += (
                f'<Relationship Id="{rId}"' +
                f' Type="{OLE_RELTYPE}"' +
                f' Target="{emb_rel}"/>' 
            ).encode('utf-8')

            # graphicFrame (부모 <p:sld>에서 네임스페이스 이미 선언됨)
            new_shapes += (
                f'<p:graphicFrame>' +
                f'<p:nvGraphicFramePr>' +
                f'<p:cNvPr id="{max_sp_id}" name="{fname_e}"/>' +
                f'<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>' +
                f'<p:nvPr/>' +
                f'</p:nvGraphicFramePr>' +
                f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>' +
                f'<a:graphic><a:graphicData' +
                f' uri="http://schemas.openxmlformats.org/presentationml/2006/ole">' +
                f'<p:oleObj name="{fname_e}" showAsIcon="1" r:id="{rId}"' +
                f' imgW="{cx}" imgH="{cy}" progId="{prog_id}"><p:embed/></p:oleObj>' +
                f'</a:graphicData></a:graphic>' +
                f'</p:graphicFrame>'
            ).encode('utf-8')

            # [Content_Types].xml 에 Extension 등록 (중복 방지)
            ct_bytes = files['[Content_Types].xml']
            if f'Extension="{ext}"'.encode() not in ct_bytes:
                files['[Content_Types].xml'] = ct_bytes.replace(
                    b'</Types>',
                    f'<Default Extension="{ext}" ContentType="{ct}"/>'.encode() + b'</Types>',
                    1,
                )

        # </p:spTree> 직전에 새 도형 삽입
        slide_bytes = slide_bytes.replace(b'</p:spTree>', new_shapes + b'</p:spTree>', 1)
        # </Relationships> 직전에 새 관계 삽입
        rels_bytes  = rels_bytes.replace(b'</Relationships>', new_rels + b'</Relationships>', 1)

        files[slide_key] = slide_bytes
        files[rels_key]  = rels_bytes

    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)
    return out.getvalue()



# ── 메인 빌더 ─────────────────────────────────────────────────────────────────

def build_pptx(week_label: str, groups: list) -> bytes:
    prs = Presentation()
    prs.slide_width  = Inches(13.33)
    prs.slide_height = Inches(7.5)

    # (slide_num → OLE item list) 수집
    slide_ole_map: dict[int, list] = {}

    for slide_num, grp in enumerate(groups, start=1):
        slide, act_col_x, act_col_w = _build_slide(
            prs, grp['name'], week_label, grp['tasks']
        )

        # 이 슬라이드에 필요한 OLE 목록 수집
        all_att = []
        for task in grp['tasks']:
            for act in task.get('activities', []):
                for att in act.get('attachments', []):
                    all_att.append(att)

        if not all_att:
            continue

        # OLE 아이콘 배치: Activity 컬럼 x 범위 내, 슬라이드 하단
        obj_w = Inches(1.1)
        obj_h = Inches(0.9)
        gap   = Inches(0.1)
        slide_h = int(prs.slide_height)
        x_pos = act_col_x
        y_pos = slide_h - int(obj_h) - int(Inches(0.15))

        ole_items = []
        for att in all_att:
            if x_pos + int(obj_w) > act_col_x + act_col_w:
                # Activity 컬럼 폭을 넘으면 다음 줄
                x_pos = act_col_x
                y_pos -= int(obj_h) + int(gap)

            ole_items.append({
                'filename': att['filename'],
                'data':     bytes(att['data']),
                'x':        x_pos,
                'y':        y_pos,
                'cx':       int(obj_w),
                'cy':       int(obj_h),
            })
            x_pos += int(obj_w) + int(gap)

        slide_ole_map[slide_num] = ole_items

    # python-pptx 로 기본 PPTX 생성
    buf = BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    # zipfile 직접 조작으로 OLE embed
    if slide_ole_map:
        pptx_bytes = _inject_ole_objects(pptx_bytes, slide_ole_map)

    return pptx_bytes

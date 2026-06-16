"""
stdlib만으로 최소한의 유효한 .pptx 파일 생성.
python-pptx 등 외부 라이브러리 불필요.
"""
import io
import re
import zipfile

# ── EMU 단위 상수 (1 inch = 914400 EMU) ─────────────────────────
_W = 9144000   # 10 inch (slide width)
_H = 5143500   # 7.5 inch (slide height) - actually standard 6858000, using this for wider

_NS = {
    'ct': 'http://schemas.openxmlformats.org/package/2006/content-types',
    'r':  'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p':  'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a':  'http://schemas.openxmlformats.org/drawingml/2006/main',
}


def _esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def _strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    return re.sub(r'<[^>]+>', '', text).strip()


def _content_types(slide_count):
    overrides = ''
    for i in range(1, slide_count + 1):
        overrides += (
            f'<Override PartName="/ppt/slides/slide{i}.xml"'
            f' ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>\n'
        )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml"
   ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml"
   ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml"
   ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml"
   ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  {overrides}
</Types>"""


def _root_rels():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
   Target="ppt/presentation.xml"/>
</Relationships>"""


def _presentation_xml(slide_count):
    slide_ids = ''.join(
        f'<p:sldId id="{256+i}" r:id="rId{i}"/>\n' for i in range(1, slide_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rIdM1"/>
  </p:sldMasterIdLst>
  <p:sldSz cx="{_W}" cy="{_H}" type="custom"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:sldIdLst>
    {slide_ids}
  </p:sldIdLst>
</p:presentation>"""


def _presentation_rels(slide_count):
    slide_rels = ''.join(
        f'<Relationship Id="rId{i}"'
        f' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"'
        f' Target="slides/slide{i}.xml"/>\n'
        for i in range(1, slide_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdM1"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
   Target="slideMasters/slideMaster1.xml"/>
  {slide_rels}
</Relationships>"""


def _theme():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Theme1">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr lastClr="000000" val="windowText"/></a:dk1>
      <a:lt1><a:sysClr lastClr="FFFFFF" val="window"/></a:lt1>
      <a:dk2><a:srgbClr val="1F3864"/></a:dk2>
      <a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
      <a:accent1><a:srgbClr val="4472C4"/></a:accent1>
      <a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A9D18E"/></a:accent3>
      <a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5A96C8"/></a:accent5>
      <a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink>
      <a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont><a:latin typeface="맑은 고딕"/><a:ea typeface="맑은 고딕"/><a:cs typeface="맑은 고딕"/></a:majorFont>
      <a:minorFont><a:latin typeface="맑은 고딕"/><a:ea typeface="맑은 고딕"/><a:cs typeface="맑은 고딕"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>"""


def _slide_master():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle><a:lstStyle/></p:titleStyle>
    <p:bodyStyle><a:lstStyle/></p:bodyStyle>
    <p:otherStyle><a:lstStyle/></p:otherStyle>
  </p:txStyles>
</p:sldMaster>"""


def _slide_master_rels():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
   Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
   Target="../theme/theme1.xml"/>
</Relationships>"""


def _slide_layout():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
  </p:spTree></p:cSld>
</p:sldLayout>"""


def _slide_layout_rels():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
   Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""


def _slide_rels():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
   Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""


def _txbox(sp_id, x, y, cx, cy, text, sz=1400, bold=False, color='000000'):
    """단순 텍스트박스 XML 생성 (줄바꿈 지원)"""
    b_attr = ' b="1"' if bold else ''
    paras = ''
    for line in str(text).split('\n'):
        paras += f"""<a:p><a:r><a:rPr lang="ko-KR" sz="{sz}"{b_attr} dirty="0">
      <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
      <a:latin typeface="맑은 고딕"/><a:ea typeface="맑은 고딕"/>
    </a:rPr><a:t>{_esc(line)}</a:t></a:r></a:p>"""
    if not paras:
        paras = '<a:p/>'
    return f"""<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sp_id}" name="sp{sp_id}"/>
    <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:noFill/>
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" rtlCol="0"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    {paras}
  </p:txBody>
</p:sp>"""


def _line(sp_id, x, y, cx, color='CCCCCC', w=12700):
    return f"""<p:sp>
  <p:nvSpPr>
    <p:cNvPr id="{sp_id}" name="ln{sp_id}"/>
    <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
    <p:nvPr/>
  </p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="0"/></a:xfrm>
    <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
    <a:noFill/>
    <a:ln w="{w}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>"""


def _build_title_slide(week_label, group_names):
    shapes = []
    shapes.append(_txbox(2, 457200, 1600000, 8229600, 600000,
                         f'주간 업무 보고', sz=3600, bold=True, color='1F3864'))
    shapes.append(_txbox(3, 457200, 2300000, 8229600, 500000,
                         week_label, sz=2400, bold=False, color='4472C4'))
    if group_names:
        shapes.append(_txbox(4, 457200, 2900000, 8229600, 400000,
                             '그룹: ' + ', '.join(group_names), sz=1600, color='595959'))
    return '\n'.join(shapes)


def _build_group_slide(grp_name, week_label, tasks):
    shapes = []
    sp_id = 2
    # 그룹 제목 (헤더 배경처럼 느낌)
    shapes.append(_txbox(sp_id, 457200, 200000, 8229600, 500000,
                         f'{grp_name}  |  {week_label}', sz=2400, bold=True, color='1F3864'))
    sp_id += 1
    shapes.append(_line(sp_id, 457200, 680000, 8229600, '4472C4', 25400))
    sp_id += 1

    # 컬럼 헤더
    col_x  = [457200, 1600000, 4800000, 5700000, 6600000, 7800000]
    col_cx = [1100000, 3150000, 860000,  860000,  1170000, 889200]
    col_labels = ['업무', 'Activity', '일정', '상태', '담당자', '비고']
    y = 740000
    for i, (lbl, x, cx) in enumerate(zip(col_labels, col_x, col_cx)):
        shapes.append(_txbox(sp_id, x, y, cx, 300000, lbl, sz=1200, bold=True, color='FFFFFF'))
        sp_id += 1
    # 헤더 배경 (사각형)
    shapes.insert(2, f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="99" name="hdr"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="457200" y="730000"/><a:ext cx="8229600" cy="300000"/></a:xfrm>
    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
    <a:solidFill><a:srgbClr val="1F3864"/></a:solidFill>
    <a:ln><a:noFill/></a:ln>
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>""")
    sp_id += 1

    y = 1080000
    row_h = 340000
    for task in tasks:
        task_name = task['name']
        for act in task.get('activities', []):
            if y + row_h > _H - 200000:
                break
            vals = [
                task_name,
                act.get('name', ''),
                act.get('schedule') or '',
                act.get('status') or '',
                act.get('assignee_names') or '',
                _strip_html(act.get('note', '')),
            ]
            for i, (val, x, cx) in enumerate(zip(vals, col_x, col_cx)):
                shapes.append(_txbox(sp_id, x, y, cx, row_h, val, sz=1000))
                sp_id += 1
            shapes.append(_line(sp_id, 457200, y + row_h, 8229600, 'DDDDDD', 9525))
            sp_id += 1
            y += row_h
            task_name = ''  # 동일 업무 이후 행은 빈 칸

    return '\n'.join(shapes)


def _slide_xml(body_shapes):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {body_shapes}
    </p:spTree>
  </p:cSld>
</p:sld>"""


def build_pptx(week_label: str, groups: list) -> bytes:
    """
    groups: list of {name, tasks:[{name, activities:[{name,schedule,status,assignee_names,note}]}]}
    반환: .pptx 바이너리
    """
    slides = []
    # 타이틀 슬라이드
    group_names = [g['name'] for g in groups]
    slides.append(_slide_xml(_build_title_slide(week_label, group_names)))
    # 그룹별 슬라이드
    for grp in groups:
        slides.append(_slide_xml(_build_group_slide(grp['name'], week_label, grp['tasks'])))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', _content_types(len(slides)))
        z.writestr('_rels/.rels', _root_rels())
        z.writestr('ppt/presentation.xml', _presentation_xml(len(slides)))
        z.writestr('ppt/_rels/presentation.xml.rels', _presentation_rels(len(slides)))
        z.writestr('ppt/theme/theme1.xml', _theme())
        z.writestr('ppt/slideMasters/slideMaster1.xml', _slide_master())
        z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels', _slide_master_rels())
        z.writestr('ppt/slideLayouts/slideLayout1.xml', _slide_layout())
        z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', _slide_layout_rels())
        for i, slide_xml in enumerate(slides, 1):
            z.writestr(f'ppt/slides/slide{i}.xml', slide_xml)
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', _slide_rels())
    return buf.getvalue()

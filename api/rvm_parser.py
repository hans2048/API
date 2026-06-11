"""
RVM Binary Parser — ported from rvm_parser.html (JS RVMParser class)

Chunk header (24 bytes):
  4 × uint32 BE : chunk name (each uint32 holds one ASCII char in LSB)
  1 × uint32 BE : next_chunk_offset (absolute byte offset of next chunk)
  1 × uint32 BE : dunno (unknown)

Strings: uint32 BE word_count, then word_count×4 bytes (null-padded)
"""

import struct


PRIM_NAMES = {
    1: 'Pyramid', 2: 'Box', 3: 'RectTorus', 4: 'CircTorus',
    5: 'EllDish', 6: 'SphDish', 7: 'Snout', 8: 'Cylinder',
    9: 'Sphere', 10: 'Line', 11: 'FacetGroup',
}


class RVMParser:

    def parse(self, file_path: str) -> dict:
        with open(file_path, 'rb') as f:
            data = f.read()

        self.data = data
        self.pos  = 0
        self.logs = []

        model = {
            'header': {}, 'project': '', 'name': 'Unknown',
            'date': '', 'user': '',
            'groups': [], 'primitiveCount': 0, 'groupCount': 0,
            'stats': {}, 'rawChunks': [],
        }

        stack   = []
        current = None

        while self.pos + 24 <= len(data):
            chunk_start = self.pos

            cname    = self._read_name()
            next_off = self._read_u32()
            _dunno   = self._read_u32()

            data_end = (next_off if (next_off > self.pos and next_off <= len(data))
                        else len(data))

            model['rawChunks'].append({
                'name': cname, 'offset': chunk_start, 'nextOff': next_off
            })

            try:
                if cname == 'HEAD':
                    ver = self._read_u32()
                    model['header']['info'] = self._read_str()
                    model['header']['note'] = self._read_str()
                    model['header']['date'] = self._read_str()
                    model['header']['user'] = self._read_str()
                    if ver >= 2 and self.pos < data_end:
                        model['header']['encoding'] = self._read_str()
                    model['date'] = model['header']['date']
                    model['user'] = model['header']['user']

                elif cname == 'MODL':
                    _ver = self._read_u32()
                    model['project'] = self._read_str()
                    model['name']    = self._read_str()

                elif cname == 'CNTB':
                    ver   = self._read_u32()
                    gname = self._read_str()
                    tx = self._read_f32() * 0.001
                    ty = self._read_f32() * 0.001
                    tz = self._read_f32() * 0.001
                    mat = self._read_u32()
                    transparency = 0
                    if ver > 2 and self.pos + 4 <= data_end:
                        transparency = data[self.pos]
                        self.pos += 4
                    g = {
                        'type': 'group', 'name': gname,
                        'translation': [tx, ty, tz], 'materialId': mat,
                        'color': None, 'transparency': transparency,
                        'children': [], 'primitives': [], 'attributes': None,
                    }
                    if current:
                        current['children'].append(g)
                    else:
                        model['groups'].append(g)
                    stack.append(current)
                    current = g
                    model['groupCount'] += 1

                elif cname == 'CNTE':
                    _ver    = self._read_u32()
                    current = stack.pop() if stack else None

                elif cname in ('PRIM', 'OBST', 'INSU'):
                    p = self._parse_prim(cname, data_end)
                    if p and current:
                        current['primitives'].append(p)
                        model['primitiveCount'] += 1
                        model['stats'][p['typeName']] = (
                            model['stats'].get(p['typeName'], 0) + 1
                        )

                elif cname == 'COLR':
                    _kind  = self._read_u32()
                    _index = self._read_u32()
                    r = data[self.pos]
                    g2 = data[self.pos + 1]
                    b2 = data[self.pos + 2]
                    self.pos += 4
                    if current:
                        current['color'] = [r / 255, g2 / 255, b2 / 255]

                elif cname == 'END:':
                    self.pos = len(data)
                    break

            except Exception as e:
                self.logs.append(f'✗ "{cname}" @0x{chunk_start:06x} 오류: {e}')

            if cname == 'END:':
                break
            if next_off == 0 or next_off <= chunk_start or next_off >= len(data):
                break
            self.pos = next_off

        model['logs'] = self.logs
        return model

    def _parse_prim(self, chunk_type: str, data_end: int) -> dict | None:
        ver  = self._read_u32()
        kind = self._read_u32()
        matrix = [self._read_f32() for _ in range(12)]
        bbox = {
            'min': [self._read_f32(), self._read_f32(), self._read_f32()],
            'max': [self._read_f32(), self._read_f32(), self._read_f32()],
        }
        transparency = 0
        if chunk_type in ('OBST', 'INSU') and self.pos + 4 <= data_end:
            transparency = self.data[self.pos]
            self.pos += 4

        prim = {
            'type': kind,
            'typeName': PRIM_NAMES.get(kind, f'Type{kind}'),
            'matrix': matrix,
            'bbox': bbox,
            'params': {},
            'transparency': transparency,
        }

        rem = lambda: data_end - self.pos

        if kind == 1 and rem() >= 28:
            prim['params'] = {
                'bx': self._read_f32(), 'by': self._read_f32(),
                'tx': self._read_f32(), 'ty': self._read_f32(),
                'ox': self._read_f32(), 'oy': self._read_f32(),
                'height': self._read_f32(),
            }
        elif kind == 2 and rem() >= 12:
            prim['params'] = {
                'xlen': self._read_f32(),
                'ylen': self._read_f32(),
                'zlen': self._read_f32(),
            }
        elif kind == 3 and rem() >= 16:
            prim['params'] = {
                'rinside':  self._read_f32(), 'routside': self._read_f32(),
                'height':   self._read_f32(), 'angle':    self._read_f32(),
            }
        elif kind == 4 and rem() >= 12:
            prim['params'] = {
                'offset': self._read_f32(),
                'radius': self._read_f32(),
                'angle':  self._read_f32(),
            }
        elif kind in (5, 6) and rem() >= 8:
            prim['params'] = {
                'baseRadius': self._read_f32(),
                'height':     self._read_f32(),
            }
        elif kind == 7 and rem() >= 36:
            prim['params'] = {
                'rbottom': self._read_f32(), 'rtop':    self._read_f32(),
                'height':  self._read_f32(),
                'ox':      self._read_f32(), 'oy':      self._read_f32(),
                'bsx':     self._read_f32(), 'bsy':     self._read_f32(),
                'tsx':     self._read_f32(), 'tsy':     self._read_f32(),
            }
        elif kind == 8 and rem() >= 8:
            prim['params'] = {
                'radius': self._read_f32(),
                'height': self._read_f32(),
            }
        elif kind == 9 and rem() >= 4:
            prim['params'] = {'diameter': self._read_f32()}
        elif kind == 10 and rem() >= 8:
            prim['params'] = {
                'a': self._read_f32(),
                'b': self._read_f32(),
            }
        elif kind == 11:
            prim['params'] = self._parse_facet_group(data_end)

        return prim

    def _parse_facet_group(self, data_end: int) -> dict:
        polygons = []
        if self.pos + 4 > data_end:
            return {'polygons': polygons}
        num_poly = self._read_u32()
        for _ in range(num_poly):
            if self.pos + 4 > data_end:
                break
            num_cont = self._read_u32()
            contours = []
            for _ in range(num_cont):
                if self.pos + 4 > data_end:
                    break
                num_vert = self._read_u32()
                verts = []
                for _ in range(num_vert):
                    if self.pos + 24 > data_end:
                        break
                    verts.append({
                        'pos':  [self._read_f32(), self._read_f32(), self._read_f32()],
                        'norm': [self._read_f32(), self._read_f32(), self._read_f32()],
                    })
                contours.append(verts)
            polygons.append(contours)
        return {'polygons': polygons}

    def _read_name(self) -> str:
        name = ''
        for _ in range(4):
            u32 = self._read_u32()
            name += chr(u32 & 0xFF)
        return name

    def _read_u32(self) -> int:
        val = struct.unpack_from('>I', self.data, self.pos)[0]
        self.pos += 4
        return val

    def _read_f32(self) -> float:
        val = struct.unpack_from('>f', self.data, self.pos)[0]
        self.pos += 4
        return val

    def _read_str(self) -> str:
        wc = self._read_u32()
        if wc == 0:
            return ''
        bl = wc * 4
        if self.pos + bl > len(self.data):
            self.pos += bl
            return ''
        raw = self.data[self.pos: self.pos + bl]
        self.pos += bl
        end = raw.find(b'\x00')
        if end == -1:
            end = bl
        return raw[:end].decode('latin-1', errors='replace')

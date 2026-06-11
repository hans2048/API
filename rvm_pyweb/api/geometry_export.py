"""
GLB / b3dm / 3D Tiles exporter — ported from rvm_parser.html
(JS GLBBuilder + TilesExporter classes)

Coordinate convention:
  RVM: mm units, Z-up
  Output GLB: m units (×0.001)
"""

import json
import math
import struct
import io
from zipfile import ZipFile, ZIP_DEFLATED


# ---------------------------------------------------------------------------
# Primitive → triangle mesh (CPU-side, mirrors GeometryBuilder in JS)
# ---------------------------------------------------------------------------

SEG = 16  # circle segments (matches JS)


def _cylinder_mesh(r_bottom: float, r_top: float, height: float,
                   segs: int = SEG) -> tuple[list, list, list]:
    """Returns (positions, normals, indices) for a cone/cylinder along Z axis."""
    pos, norm, idx = [], [], []
    h2 = height / 2

    # Side vertices
    for i in range(segs + 1):
        angle = 2 * math.pi * i / segs
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        # bottom ring
        pos.extend([r_bottom * cos_a, r_bottom * sin_a, -h2])
        slope = (r_bottom - r_top) / height if height > 0 else 0
        nx = cos_a / math.sqrt(1 + slope * slope)
        ny = sin_a / math.sqrt(1 + slope * slope)
        nz = slope / math.sqrt(1 + slope * slope)
        norm.extend([nx, ny, nz])
        # top ring
        pos.extend([r_top * cos_a, r_top * sin_a, h2])
        norm.extend([nx, ny, nz])

    # Side indices
    for i in range(segs):
        b0, b1 = i * 2, (i + 1) * 2
        t0, t1 = b0 + 1, b1 + 1
        idx.extend([b0, b1, t0, b1, t1, t0])

    # Caps
    def add_cap(z: float, radius: float, flip: bool) -> None:
        base = len(pos) // 3
        pos.extend([0.0, 0.0, z])
        norm.extend([0.0, 0.0, -1.0 if flip else 1.0])
        center_i = base
        for i in range(segs):
            angle = 2 * math.pi * i / segs
            pos.extend([radius * math.cos(angle), radius * math.sin(angle), z])
            norm.extend([0.0, 0.0, -1.0 if flip else 1.0])
        ring_start = center_i + 1
        for i in range(segs):
            a, b = ring_start + i, ring_start + (i + 1) % segs
            if flip:
                idx.extend([center_i, b, a])
            else:
                idx.extend([center_i, a, b])

    if r_bottom > 1e-6:
        add_cap(-h2, r_bottom, flip=True)
    if r_top > 1e-6:
        add_cap(h2, r_top, flip=False)

    return pos, norm, idx


def _sphere_mesh(radius: float, segs: int = SEG) -> tuple[list, list, list]:
    pos, norm, idx = [], [], []
    rings = segs // 2
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segs + 1):
            theta = 2 * math.pi * j / segs
            x = math.sin(phi) * math.cos(theta)
            y = math.sin(phi) * math.sin(theta)
            z = math.cos(phi)
            pos.extend([x * radius, y * radius, z * radius])
            norm.extend([x, y, z])
    for i in range(rings):
        for j in range(segs):
            a = i * (segs + 1) + j
            b = a + segs + 1
            idx.extend([a, b, a + 1, b, b + 1, a + 1])
    return pos, norm, idx


def _box_mesh(xlen: float, ylen: float, zlen: float) -> tuple[list, list, list]:
    hx, hy, hz = xlen / 2, ylen / 2, zlen / 2
    faces = [
        # normal,      4 corners
        ([0, 0, 1],  [(-hx,-hy, hz),( hx,-hy, hz),( hx, hy, hz),(-hx, hy, hz)]),
        ([0, 0,-1],  [(-hx, hy,-hz),( hx, hy,-hz),( hx,-hy,-hz),(-hx,-hy,-hz)]),
        ([0, 1, 0],  [(-hx, hy,-hz),(-hx, hy, hz),( hx, hy, hz),( hx, hy,-hz)]),
        ([0,-1, 0],  [(-hx,-hy, hz),(-hx,-hy,-hz),( hx,-hy,-hz),( hx,-hy, hz)]),
        ([1, 0, 0],  [( hx,-hy,-hz),( hx, hy,-hz),( hx, hy, hz),( hx,-hy, hz)]),
        ([-1,0, 0],  [(-hx,-hy, hz),(-hx, hy, hz),(-hx, hy,-hz),(-hx,-hy,-hz)]),
    ]
    pos, norm, idx = [], [], []
    for n, corners in faces:
        base = len(pos) // 3
        for c in corners:
            pos.extend(c)
            norm.extend(n)
        idx.extend([base, base+1, base+2, base, base+2, base+3])
    return pos, norm, idx


def _prim_to_mesh(prim: dict) -> tuple[list, list, list] | None:
    """Convert a parsed RVM primitive to (positions, normals, indices)."""
    kind = prim['type']
    p    = prim.get('params', {})

    try:
        if kind == 2:   # Box
            return _box_mesh(
                max(p.get('xlen', 0.01) * 2, 1e-4),
                max(p.get('ylen', 0.01) * 2, 1e-4),
                max(p.get('zlen', 0.01) * 2, 1e-4),
            )
        elif kind == 8: # Cylinder
            return _cylinder_mesh(
                max(p.get('radius', 0.01), 1e-4),
                max(p.get('radius', 0.01), 1e-4),
                max(p.get('height', 0.01), 1e-4),
            )
        elif kind == 7: # Snout
            return _cylinder_mesh(
                max(p.get('rbottom', 0.01), 1e-4),
                max(p.get('rtop', 0.01), 1e-4),
                max(p.get('height', 0.01), 1e-4),
            )
        elif kind == 9: # Sphere
            return _sphere_mesh(max(p.get('diameter', 0.02) / 2, 1e-4))
        elif kind in (5, 6): # EllDish / SphDish (hemisphere)
            return _sphere_mesh(max(p.get('baseRadius', 0.01), 1e-4))
        elif kind == 1: # Pyramid → cone approximation
            return _cylinder_mesh(
                max(p.get('bx', p.get('by', 0.01)), 1e-4), 0.0,
                max(p.get('height', 0.01), 1e-4),
            )
        elif kind == 11: # FacetGroup
            return _facet_to_mesh(p)
        else:
            # Fallback: bbox-based box
            b = prim['bbox']
            sx = max(abs(b['max'][0] - b['min'][0]) * 0.001, 1e-4)
            sy = max(abs(b['max'][1] - b['min'][1]) * 0.001, 1e-4)
            sz = max(abs(b['max'][2] - b['min'][2]) * 0.001, 1e-4)
            return _box_mesh(sx, sy, sz)
    except Exception:
        return None


def _facet_to_mesh(params: dict) -> tuple[list, list, list] | None:
    pos, norm, idx = [], [], []
    for polygon in params.get('polygons', []):
        if not polygon or not polygon[0]:
            continue
        outer = polygon[0]
        base  = len(pos) // 3
        for vt in outer:
            pos.extend(vt['pos'])
            norm.extend(vt['norm'])
        n = len(outer)
        for i in range(1, n - 1):
            idx.extend([base, base + i, base + i + 1])
    return (pos, norm, idx) if pos else None


def _mat4(matrix: list[float]) -> list[list[float]]:
    """Convert RVM 3×4 matrix to 4×4 (row-major). Translation ×0.001 (mm→m)."""
    ix, iy, iz, jx, jy, jz, kx, ky, kz, tx, ty, tz = matrix
    return [
        [ix, jx, kx, tx * 0.001],
        [iy, jy, ky, ty * 0.001],
        [iz, jz, kz, tz * 0.001],
        [0,  0,  0,  1         ],
    ]


def _transform_pos(m4: list[list[float]], p: list[float]) -> list[float]:
    x, y, z = p
    return [
        m4[0][0]*x + m4[0][1]*y + m4[0][2]*z + m4[0][3],
        m4[1][0]*x + m4[1][1]*y + m4[1][2]*z + m4[1][3],
        m4[2][0]*x + m4[2][1]*y + m4[2][2]*z + m4[2][3],
    ]


def _transform_norm(m4: list[list[float]], n: list[float]) -> list[float]:
    x, y, z = n
    nx = m4[0][0]*x + m4[0][1]*y + m4[0][2]*z
    ny = m4[1][0]*x + m4[1][1]*y + m4[1][2]*z
    nz = m4[2][0]*x + m4[2][1]*y + m4[2][2]*z
    length = math.sqrt(nx*nx + ny*ny + nz*nz)
    if length < 1e-10:
        return [0.0, 0.0, 1.0]
    return [nx/length, ny/length, nz/length]


# ---------------------------------------------------------------------------
# GLB builder
# ---------------------------------------------------------------------------

def _pad4(n: int) -> int:
    return (n + 3) & ~3


class GLBBuilder:

    def build(self, primitives: list[dict]) -> bytes | None:
        all_pos, all_norm, all_idx = [], [], []

        for prim in primitives:
            mesh = _prim_to_mesh(prim)
            if not mesh:
                continue
            lp, ln, li = mesh
            if not lp or any(math.isnan(v) for v in lp):
                continue

            m4   = _mat4(prim['matrix'])
            base = len(all_pos) // 3

            for i in range(0, len(lp), 3):
                tp = _transform_pos(m4, lp[i:i+3])
                tn = _transform_norm(m4, ln[i:i+3])
                all_pos.extend(tp)
                all_norm.extend(tn)

            all_idx.extend(i + base for i in li)

        if not all_pos:
            return None

        pa = struct.pack(f'>{len(all_pos)}f', *all_pos)
        na = struct.pack(f'>{len(all_norm)}f', *all_norm)

        use_u32 = max(all_idx) > 65535 if all_idx else False
        fmt     = '>I' if use_u32 else '>H'
        ia      = struct.pack(f'>{len(all_idx)}{fmt[-1]}', *all_idx)
        i_ct    = 5125 if use_u32 else 5123  # UNSIGNED_INT / UNSIGNED_SHORT

        # Convert big-endian floats to little-endian for GLB (OpenGL standard)
        pa = _swap_endian_f32(pa)
        na = _swap_endian_f32(na)
        ia = _swap_endian_int(ia, use_u32)

        pb  = _pad4(len(pa))
        nb  = _pad4(len(na))
        ib  = _pad4(len(ia))
        bin_len = pb + nb + ib

        buf = bytearray(bin_len)
        buf[:len(pa)] = pa
        buf[pb:pb+len(na)] = na
        buf[pb+nb:pb+nb+len(ia)] = ia

        mn = [min(all_pos[i::3]) for i in range(3)]
        mx = [max(all_pos[i::3]) for i in range(3)]
        vc = len(all_pos) // 3
        ic = len(all_idx)

        gltf = {
            'asset': {'version': '2.0', 'generator': 'RVM-PyWeb'},
            'scene': 0,
            'scenes': [{'nodes': [0]}],
            'nodes': [{'mesh': 0, 'name': 'rvm'}],
            'meshes': [{'primitives': [{
                'attributes': {'POSITION': 0, 'NORMAL': 1},
                'indices': 2, 'material': 0, 'mode': 4,
            }]}],
            'materials': [{'pbrMetallicRoughness': {
                'baseColorFactor': [0.5, 0.65, 0.8, 1.0],
                'metallicFactor': 0.1, 'roughnessFactor': 0.6,
            }, 'doubleSided': True}],
            'accessors': [
                {'bufferView': 0, 'byteOffset': 0, 'componentType': 5126,
                 'count': vc, 'type': 'VEC3', 'min': mn, 'max': mx},
                {'bufferView': 1, 'byteOffset': 0, 'componentType': 5126,
                 'count': vc, 'type': 'VEC3'},
                {'bufferView': 2, 'byteOffset': 0, 'componentType': i_ct,
                 'count': ic, 'type': 'SCALAR'},
            ],
            'bufferViews': [
                {'buffer': 0, 'byteOffset': 0,      'byteLength': pb, 'target': 34962},
                {'buffer': 0, 'byteOffset': pb,     'byteLength': nb, 'target': 34962},
                {'buffer': 0, 'byteOffset': pb + nb,'byteLength': ib, 'target': 34963},
            ],
            'buffers': [{'byteLength': bin_len}],
        }

        js   = json.dumps(gltf)
        jp   = js.ljust(_pad4(len(js)))
        jb   = jp.encode('utf-8')
        blen = len(buf)

        total = 12 + 8 + len(jb) + 8 + blen
        out   = bytearray(total)
        dv    = memoryview(out).cast('B')

        off = 0
        struct.pack_into('<III', out, off, 0x46546C67, 2, total); off += 12
        struct.pack_into('<II',  out, off, len(jb), 0x4E4F534A);  off += 8
        out[off:off+len(jb)] = jb; off += len(jb)
        struct.pack_into('<II',  out, off, blen, 0x004E4942);      off += 8
        out[off:off+blen] = buf

        return bytes(out)


def _swap_endian_f32(data: bytes) -> bytes:
    result = bytearray(len(data))
    for i in range(0, len(data), 4):
        result[i:i+4] = data[i:i+4][::-1]
    return bytes(result)


def _swap_endian_int(data: bytes, use_u32: bool) -> bytes:
    step = 4 if use_u32 else 2
    result = bytearray(len(data))
    for i in range(0, len(data), step):
        result[i:i+step] = data[i:i+step][::-1]
    return bytes(result)


# ---------------------------------------------------------------------------
# b3dm wrapper
# ---------------------------------------------------------------------------

def _wrap_b3dm(glb: bytes) -> bytes:
    ft   = json.dumps({'BATCH_LENGTH': 0})
    pad  = (8 - len(ft) % 8) % 8
    fp   = (ft + ' ' * pad).encode('utf-8')
    total = 28 + len(fp) + len(glb)

    out = bytearray(total)
    out[0:4] = b'b3dm'
    struct.pack_into('<IIIIIII', out, 4,
                     1, total,
                     len(fp), 0,
                     0, 0)
    out[28:28+len(fp)] = fp
    out[28+len(fp):]   = glb
    return bytes(out)


# ---------------------------------------------------------------------------
# TilesExporter
# ---------------------------------------------------------------------------

class TilesExporter:

    def export_all(self, models: list[dict], save_path: str) -> dict:
        """
        Collect primitives from all models, build GLB, wrap as b3dm,
        write tileset.json + model.b3dm into a ZIP at save_path.
        """
        items, bb = [], {
            'min': [1e9, 1e9, 1e9],
            'max': [-1e9, -1e9, -1e9],
        }

        for model in models:
            self._collect(model, items, bb)

        if not items:
            return {'success': False, 'message': '내보낼 지오메트리 없음'}

        glb = GLBBuilder().build(items)
        if not glb:
            return {'success': False, 'message': 'GLB 생성 실패'}

        b3dm    = _wrap_b3dm(glb)
        tileset = self._make_tileset(bb)

        with ZipFile(save_path, 'w', ZIP_DEFLATED) as z:
            z.writestr('tileset.json', json.dumps(tileset, indent=2))
            z.writestr('model.b3dm', b3dm)

        return {'success': True, 'message': f'저장 완료: {save_path}'}

    def _collect(self, model: dict, items: list, bb: dict) -> None:
        def walk(grp: dict) -> None:
            for prim in grp['primitives']:
                items.append(prim)
                for i in range(3):
                    bb['min'][i] = min(bb['min'][i], prim['bbox']['min'][i] * 0.001)
                    bb['max'][i] = max(bb['max'][i], prim['bbox']['max'][i] * 0.001)
            for child in grp['children']:
                walk(child)

        for g in model['groups']:
            walk(g)

    def _make_tileset(self, bb: dict) -> dict:
        cx = (bb['min'][0] + bb['max'][0]) / 2
        cy = (bb['min'][1] + bb['max'][1]) / 2
        cz = (bb['min'][2] + bb['max'][2]) / 2
        hx = max((bb['max'][0] - bb['min'][0]) / 2, 1.0)
        hy = max((bb['max'][1] - bb['min'][1]) / 2, 1.0)
        hz = max((bb['max'][2] - bb['min'][2]) / 2, 1.0)
        geo_err = max(hx, hy, hz) * 2

        return {
            'asset': {'version': '1.0'},
            'geometricError': geo_err,
            'root': {
                'boundingVolume': {
                    'box': [cx, cy, cz, hx, 0, 0, 0, hy, 0, 0, 0, hz]
                },
                'geometricError': 0,
                'refine': 'ADD',
                'content': {'uri': 'model.b3dm'},
            },
        }

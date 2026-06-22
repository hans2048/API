"""
OLE Package 컨테이너 생성.

PowerPoint에 임의 형식 파일(엑셀/PDF/HWP/이미지 등)을 OLE 객체로 임베드할 때,
progId="Package" 로 두면 Windows가 더블클릭 시 파일 확장자의 기본 연결 프로그램으로 실행한다.
이를 위해 oleObject.bin 은 다음 구조의 OLE 복합 파일(Compound File Binary)이어야 한다:

  Root Entry (CLSID = Packager {0003000C-...})
   └─ "\x01Ole10Native" 스트림  (MS-OLEDS 2.3.6 OLENativeStream)

python-pptx 는 prog_id 가 문자열이면 원본 바이트를 그대로 oleObject.bin 에 넣을 뿐
복합 파일로 감싸주지 않으므로(→ "손상됨" 오류), 여기서 직접 감싼다.
"""
import struct

# OLE Packager CLSID  {0003000C-0000-0000-C000-000000000046}
_PACKAGER_CLSID = bytes([
    0x0C, 0x00, 0x03, 0x00,        # Data1  (LE)
    0x00, 0x00,                    # Data2  (LE)
    0x00, 0x00,                    # Data3  (LE)
    0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46,  # Data4 (BE)
])

_FREESECT   = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_FATSECT    = 0xFFFFFFFD
_NOSTREAM   = 0xFFFFFFFF

_SECT = 512          # 섹터 크기
_MINI = 64           # 미니 섹터 크기
_CUTOFF = 4096       # 미니 스트림 컷오프


def _ole10native(filename: str, data: bytes) -> bytes:
    """\x01Ole10Native 스트림 본문 생성 (MS-OLEDS 2.3.6)."""
    label = filename.encode('cp949', 'replace') if _is_kr(filename) else filename.encode('latin-1', 'replace')
    src   = ('C:\\' + filename).encode('cp949', 'replace') if _is_kr(filename) else ('C:\\' + filename).encode('latin-1', 'replace')
    temp  = src
    body = b''
    body += struct.pack('<H', 0x0002)          # unknown_short (type)
    body += label + b'\x00'                     # filename (ANSI, sz)
    body += src + b'\x00'                        # src_path (ANSI, sz)
    body += struct.pack('<I', 0)                # unknown_long_1
    body += struct.pack('<I', 0)                # unknown_long_2
    body += temp + b'\x00'                       # temp_path (ANSI, sz)
    body += struct.pack('<I', len(data))        # actual data size
    body += data                                 # native data
    # 선두 4바이트 = 뒤따르는 전체 크기
    return struct.pack('<I', len(body)) + body


def _is_kr(s: str) -> bool:
    return any('가' <= ch <= '힣' or '㄰' <= ch <= '㆏' for ch in s)


def _pad_sect(b: bytes) -> bytes:
    if len(b) % _SECT:
        b += b'\x00' * (_SECT - len(b) % _SECT)
    return b


def _dir_entry(name: str, obj_type: int, start: int, size: int,
               child=_NOSTREAM, clsid=b'\x00' * 16) -> bytes:
    name_utf16 = name.encode('utf-16-le')
    name_field = name_utf16 + b'\x00\x00'
    name_field = name_field[:64].ljust(64, b'\x00')
    name_len = len(name_utf16) + 2  # null 종결 포함
    e = b''
    e += name_field                        # 0x00
    e += struct.pack('<H', name_len)       # 0x40
    e += struct.pack('<B', obj_type)       # 0x42  (1=storage,2=stream,5=root)
    e += struct.pack('<B', 1)              # 0x43  color = black
    e += struct.pack('<I', _NOSTREAM)      # 0x44  left
    e += struct.pack('<I', _NOSTREAM)      # 0x48  right
    e += struct.pack('<I', child)          # 0x4C  child
    e += clsid                             # 0x50  CLSID (16)
    e += struct.pack('<I', 0)              # 0x60  state
    e += b'\x00' * 8                       # 0x64  creation time
    e += b'\x00' * 8                       # 0x6C  modified time
    e += struct.pack('<I', start)          # 0x74  start sector
    e += struct.pack('<Q', size)           # 0x78  size (uint64)
    assert len(e) == 128
    return e


def _header(num_fat, first_dir, first_minifat, num_minifat, difat) -> bytes:
    h = b''
    h += b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'     # signature
    h += b'\x00' * 16                            # CLSID
    h += struct.pack('<H', 0x003E)               # minor version
    h += struct.pack('<H', 0x0003)               # major version (3)
    h += struct.pack('<H', 0xFFFE)               # byte order
    h += struct.pack('<H', 0x0009)               # sector shift (512)
    h += struct.pack('<H', 0x0006)               # mini sector shift (64)
    h += b'\x00' * 6                             # reserved
    h += struct.pack('<I', 0)                    # num dir sectors (0 for v3)
    h += struct.pack('<I', num_fat)              # num FAT sectors
    h += struct.pack('<I', first_dir)            # first dir sector
    h += struct.pack('<I', 0)                    # transaction sig
    h += struct.pack('<I', _CUTOFF)              # mini stream cutoff
    h += struct.pack('<I', first_minifat)        # first minifat sector
    h += struct.pack('<I', num_minifat)          # num minifat sectors
    h += struct.pack('<I', _ENDOFCHAIN)          # first DIFAT sector
    h += struct.pack('<I', 0)                    # num DIFAT sectors
    difat_arr = list(difat) + [_FREESECT] * (109 - len(difat))
    for d in difat_arr:
        h += struct.pack('<I', d)
    assert len(h) == 512
    return h


def build_ole_package(filename: str, data: bytes) -> bytes:
    """파일을 OLE Package 복합 파일(bytes)로 감싼다."""
    stream = _ole10native(filename, data)
    use_mini = len(stream) < _CUTOFF

    # ── 섹터 배치 ────────────────────────────────────────────────────────────
    # 항상: [FAT][Directory] 이후 데이터 섹터들.
    # mini 사용 시: [MiniFAT][MiniStreamContainer...]
    # 비-mini: [StreamData...]
    fat = []                      # FAT 엔트리 (섹터별 next)
    sectors = []                  # 실제 섹터 바이트들

    SECT_FAT = 0
    SECT_DIR = 1

    if use_mini:
        SECT_MINIFAT = 2
        SECT_MINISTREAM = 3
        # 미니 스트림 컨테이너: stream 을 64바이트 미니섹터로 담음
        n_mini = (len(stream) + _MINI - 1) // _MINI
        mini_container = stream + b'\x00' * (n_mini * _MINI - len(stream))
        # 미니 컨테이너가 차지하는 512 섹터 수
        n_container_sect = (len(mini_container) + _SECT - 1) // _SECT
        if n_container_sect == 0:
            n_container_sect = 1

        # MiniFAT: 미니섹터 체인 (0→1→...→ENDOFCHAIN)
        minifat = []
        for i in range(n_mini):
            minifat.append(i + 1 if i < n_mini - 1 else _ENDOFCHAIN)
        minifat_bytes = b''.join(struct.pack('<I', x) for x in minifat)
        # 미니FAT 섹터 채우기 (남는 자리 FREESECT)
        slots = _SECT // 4
        pad = (slots - (len(minifat) % slots)) % slots
        minifat_bytes += b'\xFF\xFF\xFF\xFF' * pad

        # 총 섹터 구성
        total_sectors = 3 + n_container_sect  # FAT,DIR,MINIFAT, container...
        # FAT 작성
        fat = [_FREESECT] * total_sectors
        fat[SECT_FAT] = _FATSECT
        fat[SECT_DIR] = _ENDOFCHAIN
        fat[SECT_MINIFAT] = _ENDOFCHAIN
        # 컨테이너 섹터 체인
        for i in range(n_container_sect):
            idx = SECT_MINISTREAM + i
            fat[idx] = (idx + 1) if i < n_container_sect - 1 else _ENDOFCHAIN

        # 디렉터리: Root + Stream
        root = _dir_entry("Root Entry", 5, SECT_MINISTREAM, len(mini_container),
                          child=1, clsid=_PACKAGER_CLSID)
        strm = _dir_entry("\x01Ole10Native", 2, 0, len(stream))
        dir_sect = _pad_sect(root + strm)

        fat_bytes = b''.join(struct.pack('<I', x) for x in fat)
        fat_bytes = _pad_sect(fat_bytes)

        out = _header(1, SECT_DIR, SECT_MINIFAT, 1, [SECT_FAT])
        out += fat_bytes
        out += dir_sect
        out += _pad_sect(minifat_bytes)
        out += _pad_sect(mini_container)
        return out

    else:
        # 큰 스트림: 일반 섹터에 직접 저장
        SECT_DATA = 2
        data_padded = _pad_sect(stream)
        n_data_sect = len(data_padded) // _SECT

        total_sectors = 2 + n_data_sect
        fat = [_FREESECT] * total_sectors
        fat[SECT_FAT] = _FATSECT
        fat[SECT_DIR] = _ENDOFCHAIN
        for i in range(n_data_sect):
            idx = SECT_DATA + i
            fat[idx] = (idx + 1) if i < n_data_sect - 1 else _ENDOFCHAIN

        root = _dir_entry("Root Entry", 5, _ENDOFCHAIN, 0,
                          child=1, clsid=_PACKAGER_CLSID)
        strm = _dir_entry("\x01Ole10Native", 2, SECT_DATA, len(stream))
        dir_sect = _pad_sect(root + strm)

        fat_bytes = _pad_sect(b''.join(struct.pack('<I', x) for x in fat))

        out = _header(1, SECT_DIR, _ENDOFCHAIN, 0, [SECT_FAT])
        out += fat_bytes
        out += dir_sect
        out += data_padded
        return out

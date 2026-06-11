"""
ATT Parser — ported from rvm_parser.html (JS ATTParser class)

Supported format:
  /PATH/TO/ELEMENT
  ATTR_KEY 'string value'
  ATTR_KEY numeric_value
  ATTR_KEY WORD_VALUE

Or inline:  /PATH ATTR1 'v1' ATTR2 v2
"""

import re


class ATTParser:

    def parse(self, file_path: str) -> dict:
        with open(file_path, 'r', encoding='latin-1') as f:
            text = f.read()

        result: dict[str, dict] = {}
        current_path  = None
        current_attrs: dict = {}

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(('!', '#', '*')):
                continue

            if line.startswith('/'):
                if current_path is not None:
                    result[current_path] = current_attrs
                space_idx = re.search(r'\s+[A-Z_]', line)
                if space_idx:
                    current_path  = line[:space_idx.start()].strip()
                    current_attrs = {}
                    self._parse_kv(line[space_idx.start():], current_attrs)
                else:
                    current_path  = line.strip()
                    current_attrs = {}
            elif current_path is not None:
                self._parse_kv(line, current_attrs)

        if current_path is not None:
            result[current_path] = current_attrs

        return result

    def _parse_kv(self, line: str, obj: dict) -> None:
        pattern = re.compile(
            r"([A-Z_][A-Z0-9_]*)\s+(?:'([^']*)'|\"([^\"]*)\"|(-?[\d.eE+]+)|([A-Z_][A-Z0-9_]*))"
        )
        for m in pattern.finditer(line):
            key = m.group(1)
            if m.group(2) is not None:
                val = m.group(2)
            elif m.group(3) is not None:
                val = m.group(3)
            elif m.group(4) is not None:
                val = float(m.group(4))
            else:
                val = m.group(5)
            obj[key] = val

    def apply_to_model(self, model: dict, att_map: dict) -> int:
        """Inject ATT attributes into matching group nodes."""
        if not att_map:
            return 0
        count = 0

        def walk(grp: dict, ancestors: list[str]) -> None:
            nonlocal count
            names = ancestors + [grp['name']]
            for path, attrs in att_map.items():
                parts = [p for p in path.split('/') if p]
                if self._path_matches(names, parts):
                    grp['attributes'] = attrs
                    count += 1
                    break
            for child in grp['children']:
                walk(child, names)

        for g in model['groups']:
            walk(g, [])
        return count

    def _path_matches(self, names: list[str], path_parts: list[str]) -> bool:
        if not path_parts:
            return False
        last = path_parts[-1].upper()
        for n in names:
            nu = n.upper()
            if nu == last or last in nu or nu in last:
                return True
        return False

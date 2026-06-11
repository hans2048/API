"""
pywebview JS API — exposed to the HTML frontend via window.pywebview.api
"""

import os
import webview

from api.rvm_parser    import RVMParser
from api.att_parser    import ATTParser
from api.geometry_export import TilesExporter


class Api:

    def __init__(self) -> None:
        self._rvm_parser  = RVMParser()
        self._att_parser  = ATTParser()
        self._exporter    = TilesExporter()

    # ------------------------------------------------------------------
    # File dialogs
    # ------------------------------------------------------------------

    def open_file_dialog(self) -> list[str]:
        """Open a file-selection dialog and return selected file paths."""
        try:
            result = webview.windows[0].filedialog.open(allow_multiple=True)
        except AttributeError:
            # fallback for pywebview < 5
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True
            )
        return list(result) if result else []

    def save_file_dialog(self, default_name: str = 'export_3dtiles.zip') -> str:
        """Open a save dialog and return the chosen path (empty string if cancelled)."""
        try:
            result = webview.windows[0].filedialog.save(save_filename=default_name)
        except AttributeError:
            # fallback for pywebview < 5
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG, save_filename=default_name
            )
        return result[0] if isinstance(result, (list, tuple)) else (result or '')

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_rvm(self, file_path: str) -> dict:
        """
        Parse an RVM file and return the model dict.
        Raises on file-not-found or parse error (JS receives as rejected Promise).
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f'파일을 찾을 수 없습니다: {file_path}')
        return self._rvm_parser.parse(file_path)

    def parse_att(self, file_path: str) -> dict:
        """Parse an ATT file and return {path: {key: value}} dict."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f'파일을 찾을 수 없습니다: {file_path}')
        return self._att_parser.parse(file_path)

    def apply_att(self, model: dict, att_map: dict) -> dict:
        """
        Inject ATT attributes into model groups and return
        {'model': <updated model>, 'matched': <count>}.
        """
        matched = self._att_parser.apply_to_model(model, att_map)
        return {'model': model, 'matched': matched}

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_tiles(self, models: list, save_path: str = '') -> dict:
        """
        Build 3D Tiles (tileset.json + model.b3dm) ZIP.
        If save_path is empty, opens a save dialog.
        Returns {'success': bool, 'message': str, 'path': str}.
        """
        if not save_path:
            save_path = self.save_file_dialog()
        if not save_path:
            return {'success': False, 'message': '저장 취소됨', 'path': ''}

        result = self._exporter.export_all(models, save_path)
        result['path'] = save_path if result['success'] else ''
        return result

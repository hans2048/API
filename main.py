import os
import sys
import webview
from api.app_api import Api

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_PATH  = os.path.join(BASE_DIR, 'ui', 'index.html')


def main() -> None:
    api    = Api()
    window = webview.create_window(
        title     = 'RVM Parser & 3D Tiles Converter',
        url       = UI_PATH,
        js_api    = api,
        width     = 1400,
        height    = 900,
        min_size  = (800, 600),
        resizable = True,
    )
    webview.start(debug='--debug' in sys.argv)


if __name__ == '__main__':
    main()

"""
루트 report.html → weekly_report/templates/report.html 생성기.

단일 SPA(report.html)를 Jinja2 템플릿으로 변환한다:
1. </head> 와 <body> 사이에 API_URL 주입 <script> 삽입
2. <body> 직후 {% raw %} ~ </body> 직전 {% endraw %} 로 감싸 JS 템플릿 리터럴 보호
3. savedApi 초기값에 window.__API_URL__ 폴백 추가

report.html 수정 후 이 스크립트를 실행하면 템플릿이 동기화된다:
    python -m weekly_report.build_template
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent / "report.html"
OUT = Path(__file__).parent / "templates" / "report.html"

INJECT = '<script>window.__API_URL__ = "{{ api_url }}";</script>'
SAVED_OLD = "const savedApi = getCookie('api_url');"
SAVED_NEW = ("const savedApi = getCookie('api_url') || "
             "(typeof window.__API_URL__ !== 'undefined' ? window.__API_URL__ : '');")


def build() -> str:
    html = ROOT.read_text(encoding="utf-8")

    # 1) API_URL 주입 + {% raw %} 시작
    html = html.replace(
        "</head>\n<body>\n",
        f"</head>\n{INJECT}\n<body>\n{{% raw %}}\n",
        1,
    )
    # 2) {% endraw %} 종료
    html = html.replace("</body>\n</html>", "</body>\n{% endraw %}\n</html>", 1)
    # 3) savedApi 폴백
    html = html.replace(SAVED_OLD, SAVED_NEW, 1)
    return html


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"생성됨: {OUT}")


if __name__ == "__main__":
    main()

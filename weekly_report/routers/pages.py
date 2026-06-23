import os
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

@router.get("/app_wr", response_class=HTMLResponse)
def index(request: Request):
    api_url = os.environ.get("API_URL", str(request.base_url).rstrip("/"))
    return templates.TemplateResponse(request=request, name="report.html", context={"api_url": api_url})

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── 기존 앱 ───────────────────────────────────────────────────────────────────
app = FastAPI(title="My API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 기존 엔드포인트 (예시) ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/employees")
async def get_employees(name: str):
    return {"response": f"{name}님 반갑습니다."}

# ── 주간 보고 모듈 등록 ─────────────────────────────────────────────────────────
# 아래 두 줄만 추가하면 /wr/* 엔드포인트가 모두 활성화됩니다.
from weekly_report import register as register_weekly_report
register_weekly_report(app)

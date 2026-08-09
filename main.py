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

# ── 주간 보고 모듈 등록 (app_wr) ───────────────────────────────────────────────
# API Gateway 규약(ADDING_NEW_SERVICE.md)에 따라 단일 router 를 마운트한다.
from app_wr import router as app_wr_router
app.include_router(app_wr_router)

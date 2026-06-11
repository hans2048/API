from fastapi import FastAPI
from weekly_report.core import init_db
from weekly_report.routers import auth, org, users, tasks, activities

def register(app: FastAPI, prefix: str = ""):
    """
    기존 FastAPI 앱에 주간 보고 라우터를 등록합니다.

    사용 예:
        from weekly_report import register
        register(app)
    """
    init_db()
    for router in (auth.router, org.router, users.router, tasks.router, activities.router):
        app.include_router(router)

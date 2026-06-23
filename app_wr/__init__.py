"""
app_wr — 주간보고(Weekly Report) 서비스의 게이트웨이 어댑터.

API Gateway 규약(ADDING_NEW_SERVICE.md)에 맞춰 단일 `router` 하나만 외부에 노출한다.
실제 비즈니스 로직/DB/템플릿은 기존 `weekly_report` 패키지 안에 그대로 격리돼 있고,
이 어댑터는 그 내부 라우터들을 묶어 게이트웨이에 단일 진입점으로 제공할 뿐이다.

게이트웨이(main.py) 등록:
    from app_wr import router as app_wr_router
    app.include_router(app_wr_router)

모든 URL 은 게이트웨이 규약대로 `/app_wr/...`(API), `/app_wr`(페이지) 네임스페이스를
사용한다. 프론트엔드(report.html)의 fetch 경로도 동일하게 `/app_wr/...` 를 호출한다.
"""
from fastapi import APIRouter

from weekly_report.core import init_db
from weekly_report.routers import (
    auth, org, users, tasks, activities, admin, pages,
)

# 앱 로드 시 전용 테이블 생성/마이그레이션
init_db()

# 내부 라우터를 하나로 묶어 단일 진입점으로 노출
router = APIRouter()
router.include_router(pages.router)
for _r in (auth.router, org.router, users.router, tasks.router,
           activities.router, admin.router):
    router.include_router(_r)

__all__ = ["router"]

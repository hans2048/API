"""
app_wr — 주간보고(Weekly Report) 서비스.

API Gateway 규약(ADDING_NEW_SERVICE.md)에 따른 단일 서비스 패키지.
모든 코드/DB/템플릿이 이 `app_wr/` 패키지 안에 격리돼 있으며,
외부에는 내부 라우터를 모두 묶은 **단일 `router`** 하나만 노출한다.

게이트웨이(main.py) 등록:
    from app_wr import router as app_wr_router
    app.include_router(app_wr_router)

모든 URL 은 규약대로 `/app_wr/...`(API), `/app_wr`(페이지) 네임스페이스를 사용한다.
"""
from fastapi import APIRouter

from app_wr.core import init_db
from app_wr.routers import (
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

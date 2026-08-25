import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.routers import (
    account_applications, announcements, audit_logs, auth, backup_jobs,
    dark_genes, dashboard, dna_data, gencc_diseases, login_logs, nav, news, news_admin, oauth_accounts, patients, permissions, pharmacies, project_info, roles,
    system_settings, tcmsp, user_preferences, users,
)
from app.seed import seed_default_data

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TCM 中藥腫瘤篩選平台 - 後台系統 API（目標零）",
    description="帳號 / 角色 / 權限矩陣 / 帳號審核 / 第三方登入 / 稽核紀錄 / 備份紀錄 / 登入紀錄 / 每日重點新聞（含多語系簡短摘要）",
    version="1.35.3",
)

ALLOWED_ORIGINS = [
    "https://fwc-tcmsp.pages.dev",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.fwc-tcmsp\.pages\.dev",  # Cloudflare Pages 的預覽部署網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length"],  # 跨網域請求預設不會公開回應標頭給 JS 讀取，進度條需要這個才能算出下載百分比
)

# ---------------------------------------------------------------------------
# 唯讀模式（系統設定頁面的「連線本機端資料庫」開關）：
# 啟用後全站禁止任何新增/編輯/刪除操作，只能瀏覽查詢。
# 用全站 middleware 攔截，而不是去每一個 CRUD 端點各自加檢查——
# 這個系統的 CRUD 端點很多（帳號/角色/公告/病患/中藥行/暗黑基因/DNA資料...），
# 逐一加檢查很容易漏掉，用 middleware 攔截可以確保「不管以後新增多少個端點都一定會被擋到」。
#
# 一定要排除的例外：
#   - /auth/login、/auth/logout：管理者要能夠登入/登出，不然唯讀模式一開，
#     連能夠把它關掉的管理者都無法登入，會造成整個系統被鎖死
#   - PUT /system-settings/read-only-mode：關閉唯讀模式本身這個操作一定要放行，
#     不然啟用之後就永遠無法再關閉
#   - POST /system-settings/backup-database：建立備份這個操作也一定要放行——
#     不然會造成一個自相矛盾的死結：啟用唯讀模式要求「必須先有成功的備份」，
#     但如果備份端點本身被唯讀模式擋住，一旦唯讀模式被啟用，就永遠無法再建立新的備份
#     （這是真實發生過的 bug，v1.31.2）
# ---------------------------------------------------------------------------
_READ_ONLY_EXEMPT_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/system-settings/read-only-mode",
    "/system-settings/backup-database",
}


@app.middleware("http")
async def enforce_read_only_mode(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path not in _READ_ONLY_EXEMPT_PATHS:
        db = SessionLocal()
        try:
            from app.routers.system_settings import _get_setting_value
            value = _get_setting_value(db, "read_only_mode")
            if value == "true":
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=423,
                    content={"detail": "系統目前為唯讀模式（已啟用「連線本機端資料庫」設定），無法執行任何新增/編輯/刪除操作，僅能瀏覽查詢。請管理者到「系統設定」頁面關閉這個設定後再試一次。"},
                )
        finally:
            db.close()
    return await call_next(request)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(permissions.router)
app.include_router(account_applications.router)
app.include_router(oauth_accounts.router)
app.include_router(audit_logs.router)
app.include_router(backup_jobs.router)
app.include_router(login_logs.router)
app.include_router(dashboard.router)
app.include_router(pharmacies.router)
app.include_router(tcmsp.router)
app.include_router(project_info.router)
app.include_router(nav.router)
app.include_router(system_settings.router)
app.include_router(announcements.router)
app.include_router(user_preferences.router)
app.include_router(patients.router)
app.include_router(dark_genes.router)
app.include_router(gencc_diseases.router)
app.include_router(dna_data.router)
app.include_router(news.router)
app.include_router(news_admin.router)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed_default_data(db)
    finally:
        db.close()


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    return {"message": "TCM 後台 API 運作中，前端頁面請至 /app/index.html，API 文件請至 /docs"}

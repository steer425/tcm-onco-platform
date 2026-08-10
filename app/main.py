import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.routers import (
    account_applications, announcements, audit_logs, auth, backup_jobs,
    dark_genes, dashboard, dna_data, login_logs, nav, oauth_accounts, patients, permissions, pharmacies, project_info, roles,
    system_settings, tcmsp, user_preferences, users,
)
from app.seed import seed_default_data

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TCM 中藥腫瘤篩選平台 - 後台系統 API（目標零）",
    description="帳號 / 角色 / 權限矩陣 / 帳號審核 / 第三方登入 / 稽核紀錄 / 備份紀錄 / 登入紀錄",
    version="1.27.1",
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
app.include_router(dna_data.router)


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

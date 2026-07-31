import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.routers import (
    account_applications, audit_logs, auth, backup_jobs,
    dashboard, login_logs, oauth_accounts, permissions, pharmacies, roles, users,
)
from app.seed import seed_default_data

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TCM 中藥腫瘤篩選平台 - 後台系統 API（目標零）",
    description="帳號 / 角色 / 權限矩陣 / 帳號審核 / 第三方登入 / 稽核紀錄 / 備份紀錄 / 登入紀錄",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

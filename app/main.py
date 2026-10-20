import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, engine
from app.routers import (
    account_applications, announcements, audit_logs, auth, backup_jobs,
    dark_genes, depmap, literature, me, dashboard, dna_data, gencc_diseases, login_logs, nav, news, news_admin, oauth_accounts, patients, permissions, pharmacies, project_info, roles,
    ingredient_mapping, pathways, system_settings, target_mapping, tcmsp,
    user_preferences, users,
)
from app.seed import seed_default_data

Base.metadata.create_all(bind=engine)
# v1.49.0：users 的帳號安全欄位每個請求都會讀，少了整站 500、連登入都進不去；
# 而手動跑 migrate_schema 要在本機輸入正式資料庫密碼（電腦未清乾淨時不該這麼做），所以啟動時自己補
from app.account_security import ensure_auth_columns  # noqa: E402
ensure_auth_columns(engine)

app = FastAPI(
    title="TCM 中藥腫瘤篩選平台 - 後台系統 API（目標零）",
    description="帳號 / 角色 / 權限矩陣 / 帳號審核 / 第三方登入 / 稽核紀錄 / 備份紀錄 / 登入紀錄 / 每日重點新聞（含多語系簡短摘要）",
    version="1.50.0",
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
    # 跨網域請求預設不會公開回應標頭給 JS 讀取：Content-Length 給進度條算百分比；
    # Content-Disposition 讓備份下載保留伺服器給的檔名（backup_日期_時間.enc），否則一律變成 backup.enc（v1.48.3）
    expose_headers=["Content-Length", "Content-Disposition"],
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
    # 密碼外洩時要能立刻換，不能因為系統剛好在唯讀就卡住（v1.44.0）
    "/me/password",
    # 同理：發現帳號被盜用時要能立刻讓所有登入失效、解除鎖定（v1.49.0）
    "/me/logout-all",
    # 通路富集「自選靶點」是 POST（靶點清單可能上千個，放不進網址），但只計算、不寫入（v1.49.4）。
    # tests/test_read_only_cache.py 會檢查所有查詢端點都沒有發出 INSERT／UPDATE／DELETE，
    # 日後若有人在這支加了寫入，那支測試會紅——到時候要把它從這裡拿掉。
    "/pathways/enrich",
}
# 管理者的「強制登出／解鎖」帶使用者 id，用前綴＋結尾比對（v1.49.0）
_READ_ONLY_EXEMPT_SUFFIXES = ("/revoke-sessions", "/unlock")


@app.middleware("http")
async def enforce_read_only_mode(request, call_next):
    path = request.url.path
    exempt = path in _READ_ONLY_EXEMPT_PATHS or (path.startswith("/users/") and path.endswith(_READ_ONLY_EXEMPT_SUFFIXES))
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not exempt:
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
app.include_router(target_mapping.router)
app.include_router(pathways.router)
app.include_router(ingredient_mapping.router)
app.include_router(depmap.router)
app.include_router(literature.router)
app.include_router(me.router)
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
        # 上一個行程沒做完的備份不會再完成，改成 failed 並寫明原因（v1.48.3）
        from app.backup_service import mark_interrupted_backups
        try:
            mark_interrupted_backups(db)
        except Exception:  # noqa: BLE001 — 這一步失敗不能擋住開機
            db.rollback()
    finally:
        db.close()


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    return {"message": "TCM 後台 API 運作中，前端頁面請至 /app/index.html，API 文件請至 /docs"}

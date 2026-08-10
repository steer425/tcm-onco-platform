from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/system-settings", tags=["系統設定（主題配色等全站設定）"])

AVAILABLE_THEMES = [
    {"id": "forest", "name": "森林綠（預設）"},
    {"id": "ocean", "name": "海洋藍"},
    {"id": "sunset", "name": "暖橘"},
    {"id": "slate", "name": "石墨灰"},
]
DEFAULT_THEME = "forest"


@router.get("/theme", summary="查詢目前系統配色主題（登入前後皆可查詢，不需權限）")
def get_theme(db: Session = Depends(get_db)):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "theme").first()
    return {"theme": setting.value if setting and setting.value else DEFAULT_THEME, "available": AVAILABLE_THEMES}


@router.put("/theme", summary="（後台）切換系統配色主題，全站套用")
def set_theme(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    theme_id = payload.get("theme")
    if theme_id not in [t["id"] for t in AVAILABLE_THEMES]:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="不是有效的主題名稱")
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "theme").first()
    if setting:
        setting.value = theme_id
    else:
        db.add(models.SystemSetting(key="theme", value=theme_id))
    db.commit()
    write_audit_log(db, admin, "update_theme", "system_setting", "theme", f"切換系統配色主題為 {theme_id}")
    return {"message": "已更新", "theme": theme_id}


# ---------------------------------------------------------------------------
# 查詢站預設項目：TCMSP 藥材/疾病查詢站首次載入時，只顯示這個預設項目，
# 減少一次載入全部資料造成的效能負擔（詳見 v1.16/v1.17 的漸進式載入設計）。
# ---------------------------------------------------------------------------

def _get_setting_value(db: Session, key: str):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return setting.value if setting else None


def _set_setting_value(db: Session, key: str, value):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if setting:
        setting.value = str(value) if value is not None else None
    else:
        db.add(models.SystemSetting(key=key, value=str(value) if value is not None else None))
    db.commit()


@router.get("/default-herb", summary="查詢查詢站預設顯示的藥材（登入即可查詢）")
def get_default_herb(db: Session = Depends(get_db)):
    value = _get_setting_value(db, "default_herb_id")
    return {"herb_id": int(value) if value else None}


@router.put("/default-herb", summary="（後台）設定查詢站預設顯示的藥材")
def set_default_herb(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    herb_id = payload.get("herb_id")
    _set_setting_value(db, "default_herb_id", herb_id)
    write_audit_log(db, admin, "update_default_herb", "system_setting", "default_herb_id", f"設定預設藥材 herb_id={herb_id}")
    return {"message": "已更新", "herb_id": herb_id}


@router.get("/default-disease", summary="查詢查詢站預設顯示的疾病（登入即可查詢）")
def get_default_disease(db: Session = Depends(get_db)):
    value = _get_setting_value(db, "default_disease_id")
    return {"dis_id": value}


@router.put("/default-disease", summary="（後台）設定查詢站預設顯示的疾病")
def set_default_disease(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    dis_id = payload.get("dis_id")
    _set_setting_value(db, "default_disease_id", dis_id)
    write_audit_log(db, admin, "update_default_disease", "system_setting", "default_disease_id", f"設定預設疾病 dis_id={dis_id}")
    return {"message": "已更新", "dis_id": dis_id}


# ---------------------------------------------------------------------------
# 查詢站關聯網絡圖：每層節點顯示數量上限的「預設值」，三個查詢站（藥材/疾病/暗黑基因）共用同一組設定。
# 使用者在畫面上還是可以自行調整下拉選單，這裡只是決定「網頁一開始載入時」預設選中哪個數字，
# 不用像先前那樣寫死在前端程式碼裡（例如之前寫死「15」，改動還要重新部署前端）。
# ---------------------------------------------------------------------------

GRAPH_LIMIT_KEYS = {
    "graph_limit_level1": {"label": "網絡圖第一層節點數量上限（例如：每個藥材最多顯示幾個靶點）", "default": 8},
    "graph_limit_level2": {"label": "網絡圖第二層節點數量上限（例如：每個靶點最多顯示幾個成分/疾病）", "default": 5},
    "graph_limit_level3": {"label": "網絡圖第三層節點數量上限（例如：每個成分最多顯示幾種藥材）", "default": 15},
}


@router.get("/graph-limits", summary="查詢查詢站網絡圖節點數量上限的預設值（登入即可查詢）")
def get_graph_limits(db: Session = Depends(get_db)):
    result = {}
    for key, meta in GRAPH_LIMIT_KEYS.items():
        value = _get_setting_value(db, key)
        result[key] = int(value) if value else meta["default"]
    return result


@router.put("/graph-limits", summary="（後台）設定查詢站網絡圖節點數量上限的預設值")
def set_graph_limits(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    updated = {}
    for key in GRAPH_LIMIT_KEYS:
        if key in payload:
            value = int(payload[key])
            if value < 1 or value > 9999:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail=f"{key} 必須介於 1~9999 之間")
            _set_setting_value(db, key, value)
            updated[key] = value
    write_audit_log(db, admin, "update_graph_limits", "system_setting", "graph_limits", f"設定網絡圖節點數量上限預設值：{updated}")
    return {"message": "已更新", **updated}


@router.post("/recompute-stats", summary="（後台）手動觸發重算統計欄位（藥材/疾病靶點數、暗黑基因比對結果），供只是手動編輯少量資料、不想重跑整個匯入流程時使用")
def trigger_recompute_stats(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    from app.recompute_stats import recompute_all_stats
    recompute_all_stats(db)
    write_audit_log(db, admin, "recompute_stats", "system", "stats", "手動觸發重算統計欄位")
    return {"message": "統計欄位已重算完成"}


# ---------------------------------------------------------------------------
# 資料庫備份到本機端（下載）
# ---------------------------------------------------------------------------

@router.post("/backup-database", response_model=None, summary="（後台）建立一份加密的資料庫備份，路徑由系統自動決定，在背景執行避免大量資料時逾時")
def create_backup(background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    # 備份是在同一次 HTTP 請求裡「同步」處理完才回應的話，正式環境資料量大時
    # （逐一掃過幾十張資料表、幾萬筆關聯資料再加密）容易超過 Render/瀏覽器的逾時限制，
    # 導致前端看到「Failed to fetch」——這是真實發生過的 bug（v1.31.1）。
    # 改成：這裡只負責建立一筆 running 狀態的紀錄就立刻回應，實際的匯出/加密工作丟到背景執行，
    # 前端改成輪詢 GET /backup-jobs 直到狀態變成 success/failed 為止。
    job = models.BackupJob(status=models.BackupStatus.running, notes="手動觸發，透過系統設定頁面下載到本機（背景處理中）")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    def _run_backup_in_background(job_id: str, admin_id: str):
        from app.database import SessionLocal
        from app.backup_service import create_encrypted_backup
        import datetime as _dt

        bg_db = SessionLocal()
        try:
            bg_job = bg_db.query(models.BackupJob).filter(models.BackupJob.id == job_id).first()
            if not bg_job:
                return
            try:
                file_path, size_bytes = create_encrypted_backup(bg_db)
                bg_job.status = models.BackupStatus.success
                bg_job.file_path = file_path
                bg_job.size_bytes = size_bytes
                bg_job.notes = "手動觸發，透過系統設定頁面下載到本機"
                bg_job.finished_at = _dt.datetime.utcnow()
                bg_db.commit()
                admin_user = bg_db.query(models.User).filter(models.User.id == admin_id).first()
                if admin_user:
                    write_audit_log(bg_db, admin_user, "create_backup", "backup_job", job_id, f"建立資料庫備份，檔案大小 {size_bytes} bytes")
            except Exception as e:
                bg_job.status = models.BackupStatus.failed
                bg_job.notes = f"備份失敗：{e}"
                bg_job.finished_at = _dt.datetime.utcnow()
                bg_db.commit()
        finally:
            bg_db.close()

    background_tasks.add_task(_run_backup_in_background, job_id, admin.id)

    from app import schemas
    return schemas.BackupJobOut.model_validate(job)


@router.get("/backup-database/{job_id}/download", summary="（後台）下載指定的加密備份檔案到本機")
def download_backup(job_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    job = db.query(models.BackupJob).filter(models.BackupJob.id == job_id).first()
    if not job or not job.file_path:
        raise HTTPException(status_code=404, detail="找不到備份紀錄，或這筆紀錄還沒有實際備份檔案")

    from app.backup_service import read_backup_file
    try:
        content = read_backup_file(job.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="備份檔案在伺服器上已經不存在（可能已被清除）")

    write_audit_log(db, admin, "download_backup", "backup_job", job.id, "下載加密備份檔案到本機")

    filename = job.file_path.split("/")[-1]
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 唯讀模式（「連線本機端資料庫」設定）：勾選後全站禁止任何 CRUD 異動操作
# ---------------------------------------------------------------------------

@router.get("/read-only-mode", summary="查詢目前是否為唯讀模式（登入即可查詢，前端需要據此提示使用者）")
def get_read_only_mode(db: Session = Depends(get_db)):
    value = _get_setting_value(db, "read_only_mode")
    return {"enabled": value == "true"}


@router.put("/read-only-mode", summary="（後台）設定唯讀模式：啟用後全站無法執行任何新增/編輯/刪除操作，僅能瀏覽查詢；啟用前必須先有至少一次成功的資料庫備份")
def set_read_only_mode(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    enabled = bool(payload.get("enabled"))

    if enabled:
        # 「連線本機端資料庫」的前提是本機端要先有資料庫可以連——也就是至少要有一次成功完成的備份，
        # 不然啟用唯讀模式時，本機端根本沒有任何資料庫內容，這個設定形同虛設。
        has_successful_backup = db.query(models.BackupJob).filter(
            models.BackupJob.status == models.BackupStatus.success
        ).first() is not None
        if not has_successful_backup:
            raise HTTPException(
                status_code=400,
                detail="尚未完成過任何資料庫備份，無法啟用唯讀模式（連線本機端資料庫）。請先到上方「資料庫備份到本機」建立至少一次成功的備份。",
            )

    _set_setting_value(db, "read_only_mode", "true" if enabled else "false")
    write_audit_log(db, admin, "set_read_only_mode", "system_setting", "read_only_mode",
                     f"{'啟用' if enabled else '關閉'}唯讀模式")
    return {"enabled": enabled}

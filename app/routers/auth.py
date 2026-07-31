from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, write_audit_log
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["登入與帳號申請"])


@router.post("/apply", response_model=schemas.ApplicationOut, summary="申請新帳號")
def apply_account(payload: schemas.ApplyAccountRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.account == payload.account).first()
    if existing:
        raise HTTPException(status_code=400, detail="此帳號已存在或已提出申請")

    user = models.User(
        account=payload.account,
        password_hash=hash_password(payload.password),
        status=models.UserStatus.pending,
        notes=payload.notes,
    )
    db.add(user)
    db.flush()

    application = models.AccountApplication(account=payload.account, user_id=user.id, notes=payload.notes)
    db.add(application)
    db.commit()
    db.refresh(application)
    write_audit_log(db, None, "apply_account", "user", user.id, f"帳號 {payload.account} 提出申請")
    return application


@router.post("/login", response_model=schemas.TokenResponse, summary="登入")
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.account == payload.account).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if user.status == models.UserStatus.pending:
        raise HTTPException(status_code=403, detail="帳號審核中，請等待管理者審核通過")
    if user.status == models.UserStatus.suspended:
        raise HTTPException(status_code=403, detail=f"帳號已停用：{user.suspend_reason or '未填寫原因'}")

    client_ip = request.client.host if request.client else None
    login_log = models.LoginLog(
        user_id=user.id,
        account=user.account,
        ip_address=client_ip,
        device_id=payload.device_id,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(login_log)
    db.commit()
    db.refresh(login_log)

    token = create_access_token({"sub": user.id, "acc": user.account})
    write_audit_log(db, user, "login", "user", user.id, f"{user.account} 登入系統")
    return schemas.TokenResponse(access_token=token, login_log_id=login_log.id)


@router.post("/logout", summary="登出")
def logout(login_log_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = db.query(models.LoginLog).filter(
        models.LoginLog.id == login_log_id, models.LoginLog.user_id == current_user.id
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="找不到對應的登入紀錄")
    log.logout_at = datetime.utcnow()
    log.duration_seconds = int((log.logout_at - log.login_at).total_seconds())
    db.commit()
    write_audit_log(db, current_user, "logout", "user", current_user.id, f"{current_user.account} 登出系統")
    return {"message": "已登出", "duration_seconds": log.duration_seconds}


@router.get("/me", response_model=schemas.UserOut, summary="取得目前登入者資訊")
def me(current_user: models.User = Depends(get_current_user)):
    result = schemas.UserOut.model_validate(current_user)
    result.role_names = [ur.role.name for ur in current_user.roles]
    return result

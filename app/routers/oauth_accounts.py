from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/oauth-accounts", tags=["第三方登入綁定"])

# 說明：Google / 小紅書 / WeChat 實際 OAuth 授權流程（取得 authorization code、
# 交換 access token、取得使用者資料）需要各平台的 client id/secret 與正式回呼網址，
# 屬於「待確認事項」（開發者串接資格尚未確認）。
# 這裡先提供帳號綁定關係的 CRUD 骨架，之後接上真實 OAuth flow 時，
# 只需在對應 provider 的授權完成後呼叫 create_link 寫入即可。


@router.get("/me", response_model=List[schemas.OAuthAccountOut], summary="查詢我目前綁定的第三方帳號")
def my_links(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return current_user.oauth_accounts


@router.post("/me", response_model=schemas.OAuthAccountOut, summary="綁定第三方帳號（暫以手動輸入 provider_user_id 代替正式 OAuth flow）")
def create_link(payload: schemas.OAuthLinkCreate, current_user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    existing = db.query(models.OAuthAccount).filter(
        models.OAuthAccount.provider == payload.provider,
        models.OAuthAccount.provider_user_id == payload.provider_user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="此第三方帳號已被綁定")
    link = models.OAuthAccount(
        user_id=current_user.id, provider=payload.provider,
        provider_user_id=payload.provider_user_id, notes=payload.notes,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    write_audit_log(db, current_user, "link_oauth", "oauth_account", link.id,
                     f"{current_user.account} 綁定 {payload.provider}")
    return link


@router.delete("/me/{link_id}", summary="解除第三方帳號綁定")
def delete_link(link_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.query(models.OAuthAccount).filter(
        models.OAuthAccount.id == link_id, models.OAuthAccount.user_id == current_user.id
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="找不到綁定紀錄")
    db.delete(link)
    db.commit()
    write_audit_log(db, current_user, "unlink_oauth", "oauth_account", link_id,
                     f"{current_user.account} 解除 {link.provider} 綁定")
    return {"message": "已解除綁定"}


@router.get("", response_model=List[schemas.OAuthAccountOut], summary="（管理者）查詢全站第三方登入綁定")
def list_all_links(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return db.query(models.OAuthAccount).all()

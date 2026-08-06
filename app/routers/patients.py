from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/patients", tags=["客戶資料管理（病患基本資料／就診紀錄）"])


def _mask_id_number(id_number: Optional[str]) -> str:
    """證件號碼遮罩：只保留前 1~3 碼與後 3 碼，中間用 * 取代，長度太短就整串遮住"""
    if not id_number:
        return ""
    s = id_number.strip()
    if len(s) <= 6:
        return "*" * len(s)
    head = s[:3]
    tail = s[-3:]
    return head + "*" * (len(s) - 6) + tail


def _to_patient_out(p: models.Patient, encounter_count: int = 0) -> schemas.PatientOut:
    out = schemas.PatientOut.model_validate(p, from_attributes=True)
    out.id_number_masked = _mask_id_number(p.id_number)
    out.encounter_count = encounter_count
    return out


# ---------------------------------------------------------------------------
# 病患基本資料 CRUD（僅限管理者，內含敏感個資）
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.PatientOut], summary="查詢病患列表（可搜尋姓名/病患識別碼/病歷號）")
def list_patients(keyword: Optional[str] = None, status_filter: Optional[str] = None,
                   db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.Patient)
    if keyword:
        q = q.filter(
            (models.Patient.name.ilike(f"%{keyword}%")) |
            (models.Patient.patient_id.ilike(f"%{keyword}%")) |
            (models.Patient.medical_record_no.ilike(f"%{keyword}%"))
        )
    if status_filter:
        q = q.filter(models.Patient.status == status_filter)
    patients = q.order_by(models.Patient.created_at.desc()).all()
    return [_to_patient_out(p, len(p.encounters)) for p in patients]


@router.post("", response_model=schemas.PatientOut, summary="新增病患")
def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    if db.query(models.Patient).filter(models.Patient.patient_id == payload.patient_id).first():
        raise HTTPException(status_code=400, detail="病患識別碼已存在")
    p = models.Patient(**payload.model_dump(), created_by=admin.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "create_patient", "patient", p.id, f"新增病患 {p.name}（{p.patient_id}）")
    return _to_patient_out(p, 0)


@router.put("/{patient_id}", response_model=schemas.PatientOut, summary="編輯病患基本資料")
def update_patient(patient_id: str, payload: schemas.PatientUpdate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到病患資料")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "update_patient", "patient", p.id, f"編輯病患資料 {p.name}（{p.patient_id}）")
    return _to_patient_out(p, len(p.encounters))


@router.delete("/{patient_id}", summary="刪除病患（軟刪除）")
def delete_patient(patient_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到病患資料")
    p.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_patient_soft", "patient", p.id, f"刪除（軟刪除）病患 {p.name}（{p.patient_id}）")
    return {"message": "已刪除（軟刪除）"}


@router.get("/{patient_id}/id-number", summary="顯示完整證件號碼明碼（會記錄稽核紀錄，敏感操作）")
def reveal_id_number(patient_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到病患資料")
    write_audit_log(db, admin, "reveal_patient_id_number", "patient", p.id,
                     f"查看病患 {p.name}（{p.patient_id}）的完整證件號碼明碼")
    return {"id_number": p.id_number or ""}


# ---------------------------------------------------------------------------
# 就診紀錄 CRUD（依病患查詢）
# ---------------------------------------------------------------------------

@router.get("/{patient_id}/encounters", response_model=List[schemas.EncounterOut], summary="查詢某病患的就診紀錄")
def list_encounters(patient_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到病患資料")
    return db.query(models.Encounter).filter(models.Encounter.patient_id == patient_id).order_by(models.Encounter.created_at.desc()).all()


@router.post("/{patient_id}/encounters", response_model=schemas.EncounterOut, summary="新增就診紀錄")
def create_encounter(patient_id: str, payload: schemas.EncounterCreate, db: Session = Depends(get_db),
                      admin: models.User = Depends(require_admin)):
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到病患資料")
    if db.query(models.Encounter).filter(models.Encounter.encounter_id == payload.encounter_id).first():
        raise HTTPException(status_code=400, detail="就診識別碼已存在")
    data = payload.model_dump()
    data["patient_id"] = patient_id  # 以路徑參數為準，避免 body 塞錯 patient
    e = models.Encounter(**data)
    db.add(e)
    db.commit()
    db.refresh(e)
    write_audit_log(db, admin, "create_encounter", "encounter", e.id, f"新增就診紀錄 {e.encounter_id}（病患：{p.name}）")
    return e


@router.put("/encounters/{encounter_id}", response_model=schemas.EncounterOut, summary="編輯就診紀錄")
def update_encounter(encounter_id: str, payload: schemas.EncounterUpdate, db: Session = Depends(get_db),
                      admin: models.User = Depends(require_admin)):
    e = db.query(models.Encounter).filter(models.Encounter.id == encounter_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="找不到就診紀錄")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(e, field, value)
    db.commit()
    db.refresh(e)
    write_audit_log(db, admin, "update_encounter", "encounter", e.id, f"編輯就診紀錄 {e.encounter_id}")
    return e


@router.delete("/encounters/{encounter_id}", summary="刪除就診紀錄（軟刪除）")
def delete_encounter(encounter_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    e = db.query(models.Encounter).filter(models.Encounter.id == encounter_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="找不到就診紀錄")
    e.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_encounter_soft", "encounter", e.id, f"刪除（軟刪除）就診紀錄 {e.encounter_id}")
    return {"message": "已刪除（軟刪除）"}

"""F1-10 兩岸中藥典比較 API（v1.51.0）。

讀取（get_query_db，唯讀模式可讀快取）：
  GET  /pharmacopeia/thp                        品項清單＋每項的 TCMSP 比對結果＋統計
  GET  /pharmacopeia/thp/{seq}                  單一品項的 15 欄全文、修正公告、飲片、比對到的 TCMSP 藥材
  GET  /pharmacopeia/tcmsp-only                 TCMSP 有、臺灣中藥典沒有（或尚無已採用比對）的藥材
  GET  /pharmacopeia/tcmsp-herbs/{herb_id}/ingredients   展開某個 TCMSP 藥材的全部成分（MOL）
審核（get_db，需 F1-10 can_execute；寫稽核紀錄）：
  POST /pharmacopeia/map/{map_id}/review        確認／否決
  POST /pharmacopeia/map                        人工指定對應
  POST /pharmacopeia/rematch                    重新比對（只動 auto／pending）

「中國側」以 TCMSP 藥材編號代表——TCMSP 依中國藥典 2010 年版收載品項建立，**不是**中國藥典的官方編號，
也沒有中國藥典的專論內容。畫面與 API 都要照這樣標示。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models, pathways
from app import thp as T
from app.database import get_db, get_query_db
from app.deps import get_current_user, has_permission, require_permission, write_audit_log

router = APIRouter(prefix="/pharmacopeia", tags=["F1-10 兩岸中藥典比較"])
FEATURE = "F1-10"

CN_SIDE_LABEL = "中國藥典 2010 收載品項（依 TCMSP 藥材編號）"
DISCLAIMER = ("臺灣中藥典內容摘錄自衛生福利部公告之臺灣中藥典第四版（110-09-24 公告、111-06-01 施行）"
              "與 114-07-30 修正公告，由 PDF 解析，排版複雜處（公式、梯度表）可能與原書略有差異，"
              "以衛福部官方頁面為準。功能、用法與用量、注意事項為藥典原文照錄，僅供查閱。"
              "「中國側」以 TCMSP 藥材編號代表中國藥典 2010 年版收載品項，並非中國藥典官方編號。"
              "本平台為科研輔助工具，不作為醫療診斷或治療建議。")


def _herb_brief(h) -> dict:
    return {"herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
            "herb_en_name": h.herb_en_name}


def _map_out(r, herb) -> dict:
    return {"map_id": r.id, "status": r.status, "method": r.method,
            "flags": json.loads(r.flags) if r.flags else [], "note": r.note,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            **(_herb_brief(herb) if herb else {"herb_id": r.herb_id})}


def _maps_by_seq(db):
    herbs = {h.id: h for h in db.query(models.TcmspHerb).all()}
    out = {}
    for r in db.query(models.ThpTcmspMap).all():
        out.setdefault(r.thp_seq, []).append(_map_out(r, herbs.get(r.herb_id)))
    order = {"confirmed": 0, "auto": 1, "pending": 2, "rejected": 3}
    for v in out.values():
        v.sort(key=lambda x: (order.get(x["status"], 9), x.get("herb_id") or 0))
    return out


@router.get("/thp", summary="臺灣中藥典品項清單與 TCMSP 比對結果")
def list_thp(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db),
             main_db: Session = Depends(get_db)):
    maps = _maps_by_seq(db)
    items = []
    for m in db.query(models.ThpMonograph).order_by(models.ThpMonograph.seq).all():
        items.append({
            "seq": m.seq, "site_no": m.site_no, "kind": m.kind, "parent_seq": m.parent_seq,
            "name_zh": m.name_zh, "latin_name": m.latin_name, "en_name": m.en_name,
            "category": m.category, "amended": bool(m.amendment),
            "species": json.loads(m.species or "[]"),
            "matches": maps.get(m.seq, []),
        })
    src = T.load_json()["source"]
    return {"items": items, "stats": T.stats(db), "source": src,
            "cn_side_label": CN_SIDE_LABEL, "disclaimer": DISCLAIMER,
            # 權限表不在唯讀快取裡，一律查主資料庫
            "can_review": has_permission(main_db, current_user, FEATURE, need_execute=True)}


@router.get("/thp/{seq}", summary="單一品項：15 欄全文、修正公告、飲片與比對到的 TCMSP 藥材")
def get_thp(seq: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    m = db.query(models.ThpMonograph).filter(models.ThpMonograph.seq == seq).first()
    if not m:
        raise HTTPException(status_code=404, detail="找不到這個臺灣中藥典品項")
    parent = (db.query(models.ThpMonograph).filter(models.ThpMonograph.seq == m.parent_seq).first()
              if m.parent_seq else None)
    children = (db.query(models.ThpMonograph).filter(models.ThpMonograph.parent_seq == m.seq)
                .order_by(models.ThpMonograph.seq).all())
    fields = {f: getattr(m, f) for f in T.FIELDS}
    if m.kind == "processed" and parent and not fields["origin"]:
        fields["origin"] = parent.origin          # 飲片的基原同所屬藥材，畫面上標示「同原藥材」
    maps = _maps_by_seq(db).get(m.seq, [])
    return {
        "seq": m.seq, "site_no": m.site_no, "kind": m.kind, "name_zh": m.name_zh,
        "latin_name": m.latin_name or (parent.latin_name if parent else None),
        "en_name": m.en_name or (parent.en_name if parent else None),
        "species": json.loads(m.species or "[]"), "book_page": m.book_page,
        "fields": fields, "origin_inherited": bool(m.kind == "processed" and parent and not m.origin),
        "extra": json.loads(m.extra) if m.extra else None,
        "amendment": json.loads(m.amendment) if m.amendment else None,
        "official_url": T.site_url(m.site_no),
        "parent": {"seq": parent.seq, "site_no": parent.site_no, "name_zh": parent.name_zh} if parent else None,
        "children": [{"seq": c.seq, "site_no": c.site_no, "name_zh": c.name_zh} for c in children],
        "matches": maps, "cn_side_label": CN_SIDE_LABEL, "disclaimer": DISCLAIMER,
    }


@router.get("/tcmsp-only", summary="TCMSP 有、但沒有對到任何臺灣中藥典品項的藥材")
def tcmsp_only(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    linked = {r.herb_id for r in db.query(models.ThpTcmspMap).filter(models.ThpTcmspMap.status != "rejected").all()}
    herbs = (db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active")
             .order_by(models.TcmspHerb.id).all())
    return {"items": [_herb_brief(h) for h in herbs if h.id not in linked], "cn_side_label": CN_SIDE_LABEL}


@router.get("/tcmsp-herbs/{herb_id}/ingredients", summary="展開 TCMSP 藥材的成分（MOL）清單")
def herb_ingredients(herb_id: int, current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_query_db)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id).first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到這個 TCMSP 藥材")
    ob_min, dl_min = pathways.adme_thresholds(db)
    meta = pathways.active_ingredients(db, herb_id, ob_min, dl_min)   # 活性判定只在這一支（rules.md）
    active = set(meta["passed"])
    rows = (db.query(models.TcmspIngredient)
            .join(models.TcmspHerbIngredient, models.TcmspHerbIngredient.mol_id == models.TcmspIngredient.mol_id)
            .filter(models.TcmspHerbIngredient.herb_id == herb_id)
            .order_by(models.TcmspIngredient.mol_id).all())
    return {
        "herb": _herb_brief(herb), "thresholds": {"ob_min": ob_min, "dl_min": dl_min},
        "total": len(rows), "active": len(active),
        "items": [{"mol_id": i.mol_id, "molecule_name": i.molecule_name, "ob": i.ob, "dl": i.dl,
                   "active": i.mol_id in active} for i in rows],
    }


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(confirm|reject)$")
    note: str | None = Field(default=None, max_length=500)


@router.post("/map/{map_id}/review", summary="確認或否決一筆比對（需 F1-10 可執行）")
def review_map(map_id: str, payload: ReviewIn, db: Session = Depends(get_db),
               user: models.User = Depends(require_permission(FEATURE, need_execute=True))):
    row = db.query(models.ThpTcmspMap).filter(models.ThpTcmspMap.id == map_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到這筆比對")
    before = row.status
    T.review(db, row, payload.action, user, payload.note)
    write_audit_log(db, user, f"thp_map_{payload.action}", "thp_tcmsp_map", row.id,
                    json.dumps({"thp_seq": row.thp_seq, "herb_id": row.herb_id, "before": before,
                                "after": row.status, "note": payload.note}, ensure_ascii=False))
    db.commit()
    return {"map_id": row.id, "status": row.status}


class ManualIn(BaseModel):
    thp_seq: int
    herb_id: int
    note: str | None = Field(default=None, max_length=500)


@router.post("/map", summary="人工指定臺灣中藥典品項 ↔ TCMSP 藥材（需 F1-10 可執行）")
def manual_map(payload: ManualIn, db: Session = Depends(get_db),
               user: models.User = Depends(require_permission(FEATURE, need_execute=True))):
    if not db.query(models.ThpMonograph).filter(models.ThpMonograph.seq == payload.thp_seq).first():
        raise HTTPException(status_code=404, detail="找不到這個臺灣中藥典品項")
    if not db.query(models.TcmspHerb).filter(models.TcmspHerb.id == payload.herb_id).first():
        raise HTTPException(status_code=404, detail="找不到這個 TCMSP 藥材")
    row = (db.query(models.ThpTcmspMap)
           .filter(models.ThpTcmspMap.thp_seq == payload.thp_seq, models.ThpTcmspMap.herb_id == payload.herb_id).first())
    if row is None:
        row = models.ThpTcmspMap(thp_seq=payload.thp_seq, herb_id=payload.herb_id, method="manual")
        db.add(row)
    row.method = "manual"
    T.review(db, row, "confirm", user, payload.note)
    db.flush()
    write_audit_log(db, user, "thp_map_manual", "thp_tcmsp_map", row.id,
                    json.dumps({"thp_seq": payload.thp_seq, "herb_id": payload.herb_id, "note": payload.note},
                               ensure_ascii=False))
    db.commit()
    return {"map_id": row.id, "status": row.status}


@router.post("/rematch", summary="重新比對（只更新自動結果，人工判過的不動；需 F1-10 可執行）")
def rematch(db: Session = Depends(get_db),
            user: models.User = Depends(require_permission(FEATURE, need_execute=True))):
    res = T.rematch(db)
    write_audit_log(db, user, "thp_rematch", "thp_tcmsp_map", None, json.dumps(res, ensure_ascii=False))
    db.commit()
    return res

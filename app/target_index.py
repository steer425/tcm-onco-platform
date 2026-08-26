"""靶點比對索引（單一事實來源）。

平台裡有八個地方要回答同一個問題：「這個基因符號（HGNC symbol）對應到哪些 TCMSP 靶點？」
——暗黑基因統計、逐基因統計、藥材反查、基因詳情、關聯圖、GenCC 疾病比對、
以及離線重算（app/recompute_stats.py）。

在 v1.38.0 之前，這八個地方各自就地寫一段「把 target_name 拆成英數字詞」的索引。
邏輯一樣、來源一樣，所以答案也一樣，沒出過事；但 UniProt 標準化上線之後就不是這樣了：
只要有任何一個地方沒改到，就會出現「查詢站說這個基因比對到靶點，統計欄位卻說沒有」
這種自相矛盾的畫面，而且很難查。所以比對邏輯集中在這裡，八個地方一律呼叫這裡的函式。

比對規則（兩層，順序有意義）：
    1. 已標準化的靶點（tcmsp_target_uniprot 裡 status 為 auto/confirmed）
       → 用 UniProt 的 gene_symbol 與 gene_synonyms 精確比對。
    2. 尚未標準化的靶點
       → 退回原本的「蛋白名稱英數字詞」比對。

第 2 層是刻意保留的退路：UniProt 解析要連外網、要跑幾十分鐘，
在它跑完之前統計不能整個歸零。但**已標準化的靶點不再走第 2 層**——
它已經有精確的基因符號了，再拿名稱裡的字詞去猜只會多出誤中
（例如靶點名稱含 "1"、"2"、"A" 這種字詞，會亂中一堆單字母基因）。

pending / rejected / unresolved 的映射一律不採用：待人工確認的東西還不是結論，
拿它算統計等於把猜測當成事實。
"""
import json
import re

from sqlalchemy.orm import Session

from app import models

WORD_RE = re.compile(r"[A-Za-z0-9]+")

# 這幾個 status 才算「已經確定的映射」，詳見上面的模組說明
ACCEPTED_STATUS = ("auto", "confirmed")


def name_words(name) -> set:
    """把靶點蛋白名稱拆成大寫英數字詞（第 2 層退路用）。"""
    return set(WORD_RE.findall((name or "").upper()))


def _uniprot_rows(db: Session):
    return (db.query(models.TcmspTargetUniprot)
            .filter(models.TcmspTargetUniprot.status.in_(ACCEPTED_STATUS))
            .all())


def _row_symbols(row) -> list:
    """一筆映射能代表的所有符號：主要基因符號 + 同義詞。"""
    names = [row.gene_symbol or ""]
    try:
        names += json.loads(row.gene_synonyms or "[]")
    except (TypeError, ValueError):
        # gene_synonyms 是 Text 欄位存 JSON 字串（本專案不用 JSONB），
        # 舊資料或人工編輯過的內容可能不是合法 JSON，這裡不讓它炸掉整個統計
        pass
    return [(n or "").strip().upper() for n in names if (n or "").strip()]


def target_to_symbols(db: Session):
    """回傳 {tar_id: {符號, ...}}，涵蓋全部靶點。

    已標準化的靶點回傳它的 UniProt 基因符號與同義詞；未標準化的回傳名稱字詞。
    用於「從靶點反查基因／疾病」的方向（關聯圖、GenCC 反查）。
    """
    tar_to_sym: dict = {}
    for row in _uniprot_rows(db):
        syms = _row_symbols(row)
        if syms:
            tar_to_sym.setdefault(row.tar_id, set()).update(syms)

    for tar_id, name in db.query(models.TcmspTarget.tar_id, models.TcmspTarget.target_name).all():
        if tar_id in tar_to_sym:
            continue
        tar_to_sym[tar_id] = name_words(name)
    return tar_to_sym


def symbol_to_targets(db: Session):
    """回傳 ({符號: {tar_id, ...}}, 已標準化的靶點數)。

    用於「從基因符號查靶點」的方向（統計、查詢站、藥材反查）。
    第二個回傳值只是給畫面／log 顯示進度用的，不影響比對結果。
    """
    sym_to_tar: dict = {}
    mapped = set()
    for row in _uniprot_rows(db):
        syms = _row_symbols(row)
        if not syms:
            continue
        mapped.add(row.tar_id)
        for s in syms:
            sym_to_tar.setdefault(s, set()).add(row.tar_id)

    for tar_id, name in db.query(models.TcmspTarget.tar_id, models.TcmspTarget.target_name).all():
        if tar_id in mapped:
            continue
        for w in name_words(name):
            sym_to_tar.setdefault(w, set()).add(tar_id)
    return sym_to_tar, len(mapped)


def symbol_set(db: Session):
    """只要判斷「這個符號有沒有比對到任何靶點」時用，省掉建立集合的成本。"""
    sym_to_tar, _ = symbol_to_targets(db)
    return set(sym_to_tar.keys())


def mapping_coverage(db: Session):
    """回傳 (已標準化靶點數, 靶點總數)，給後台頁面顯示覆蓋率。"""
    total = db.query(models.TcmspTarget).count()
    mapped = (db.query(models.TcmspTargetUniprot.tar_id)
              .filter(models.TcmspTargetUniprot.status.in_(ACCEPTED_STATUS))
              .distinct().count())
    return mapped, total

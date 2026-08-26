"""TCMSP 靶點 → UniProt 標準化解析（目標一 Step 3）。

背景見 `models.TcmspTargetUniprot` 的說明：TCMSP 的靶點是蛋白全名，
而全站的比對都是拿基因符號去比字串，導致 1245 個癌症基因只比中 32 個（2.6%）。

解析策略分三級，由精確到寬鬆。**信心不足的一律不自動採用，進待確認佇列**——
這是科研平台，一個錯誤的基因映射會污染下游每一次分析，而且錯誤會被當成結論。
寧可留白等人確認，也不要給一個看起來合理的錯答案。

⚠️ 這支需要對外連到 `rest.uniprot.org`。Cowork 的沙箱與本機 VM 都連不到
（代理回 403），實際執行必須在 Render 上，或在使用者自己的機器帶 `DATABASE_URL` 跑。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
FIELDS = ("accession,id,gene_primary,gene_synonym,protein_name,"
          "organism_id,xref_kegg,xref_reactome")
HUMAN = 9606

# 方法與信心分數。auto 門檻設在 0.8：
# 0.8 以上代表「查詢條件夠精確且只回一筆」，其餘一律要人看過。
METHOD_CONFIDENCE = {"exact": 1.0, "stripped": 0.8, "fulltext": 0.5, "manual": 1.0}
AUTO_THRESHOLD = 0.8


def normalize(name: str) -> str:
    """比較用的正規化：小寫、壓掉多餘空白、拿掉結尾標點。"""
    return re.sub(r"\s+", " ", (name or "").strip().lower()).rstrip(" .;,")


def query_terms(name: str) -> str:
    """把名稱拆成可以做 AND 查詢的詞。

    **刻意不移除結尾的數字**：「Prostaglandin G/H synthase 1」與
    「⋯ synthase 2」是 PTGS1 與 PTGS2 兩個不同的基因，
    把數字剝掉會讓兩者無法區分——而那正是這整件事最不能出的錯。
    同理不剝 alpha／beta／I／II 這類同工異構物的標示。
    """
    parts = re.split(r"[^A-Za-z0-9]+", name or "")
    return " ".join(p for p in parts if len(p) >= 2 or p.isdigit())


def _xrefs(entry: dict) -> tuple[str | None, list[str]]:
    kegg, reactome = None, []
    for x in entry.get("uniProtKBCrossReferences") or []:
        db = (x.get("database") or "").lower()
        if db == "kegg" and not kegg:
            kegg = x.get("id")
        elif db == "reactome" and x.get("id"):
            reactome.append(x["id"])
    return kegg, reactome[:20]


def parse_entry(entry: dict) -> dict:
    """把 UniProt 的一筆結果轉成我們要存的形狀。

    防禦性解析：UniProt 的回應結構會因為 `fields` 參數與條目種類而略有差異，
    少一層就整支掛掉是不能接受的——這支會在正式環境跑批次。
    """
    genes = entry.get("genes") or []
    primary = ""
    synonyms: list[str] = []
    if genes:
        primary = ((genes[0].get("geneName") or {}).get("value") or "")
        for g in genes:
            for syn in g.get("synonyms") or []:
                if syn.get("value"):
                    synonyms.append(syn["value"])

    desc = entry.get("proteinDescription") or {}
    rec = (desc.get("recommendedName") or {}).get("fullName") or {}
    protein_name = rec.get("value") or ""
    if not protein_name:
        subs = desc.get("submissionNames") or []
        if subs:
            protein_name = ((subs[0].get("fullName") or {}).get("value") or "")

    kegg, reactome = _xrefs(entry)
    return {
        "accession": entry.get("primaryAccession") or entry.get("accession"),
        "gene_symbol": primary or None,
        "gene_synonyms": sorted(set(synonyms)),
        "protein_name": protein_name or None,
        "organism_id": ((entry.get("organism") or {}).get("taxonId")),
        "kegg_id": kegg,
        "reactome_ids": reactome,
    }


def _search(client: httpx.Client, query: str, size: int = 5) -> list[dict]:
    resp = client.get(SEARCH_URL, params={"query": query, "fields": FIELDS,
                                          "format": "json", "size": size})
    resp.raise_for_status()
    return resp.json().get("results") or []


def resolve_name(client: httpx.Client, name: str) -> dict:
    """解析單一靶點名稱。回傳一定包含 method／confidence／status。

    status：
      auto        自動採用（單一結果且查詢條件夠精確）
      pending     有候選但需要人確認（多筆命中，或只靠全文查詢找到）
      unresolved  三級都查不到
      error       連線或 API 失敗，之後可重跑
    """
    base = f"AND organism_id:{HUMAN} AND reviewed:true"
    norm = normalize(name)

    try:
        # 第 1 級：精確名稱
        results = _search(client, f'protein_name:"{name}" {base}')
        if results:
            exact = [r for r in results
                     if normalize((parse_entry(r).get("protein_name") or "")) == norm]
            pick = exact[0] if len(exact) == 1 else (results[0] if len(results) == 1 else None)
            if pick is not None:
                return {**parse_entry(pick), "method": "exact",
                        "confidence": METHOD_CONFIDENCE["exact"], "status": "auto",
                        "candidates": []}
            return {"method": "exact", "confidence": METHOD_CONFIDENCE["exact"],
                    "status": "pending",
                    "candidates": [parse_entry(r) for r in results[:5]],
                    "note": "精確名稱查詢命中多筆，需人工判斷是哪一個"}

        # 第 2 級：拆詞後 AND 查詢（容忍語序與標點差異，但不放寬語意）
        terms = query_terms(name)
        if terms:
            results = _search(client, f"protein_name:({terms}) {base}")
            if len(results) == 1:
                return {**parse_entry(results[0]), "method": "stripped",
                        "confidence": METHOD_CONFIDENCE["stripped"], "status": "auto",
                        "candidates": []}
            if results:
                return {"method": "stripped", "confidence": METHOD_CONFIDENCE["stripped"],
                        "status": "pending",
                        "candidates": [parse_entry(r) for r in results[:5]],
                        "note": "拆詞查詢命中多筆，需人工判斷"}

        # 第 3 級：全文查詢。一律進待確認，不管只回一筆——
        # 全文查詢會命中「內文提到這個名稱」的條目，那不等於就是同一個蛋白。
        results = _search(client, f'"{name}" {base}')
        if results:
            return {"method": "fulltext", "confidence": METHOD_CONFIDENCE["fulltext"],
                    "status": "pending",
                    "candidates": [parse_entry(r) for r in results[:5]],
                    "note": "僅全文查詢找得到，可信度低，務必人工確認"}

        return {"method": "fulltext", "confidence": 0.0, "status": "unresolved",
                "candidates": [], "note": "三級查詢都查無結果"}

    except Exception as exc:  # noqa: BLE001
        logger.error("UniProt 解析失敗（%s）：%s", name, exc)
        return {"method": "exact", "confidence": 0.0, "status": "error",
                "candidates": [], "note": f"查詢失敗：{str(exc)[:200]}"}


def resolve_many(names: list[str], *, timeout: float = 25.0,
                 pause: float = 0.15) -> dict[str, dict]:
    """批次解析。回傳 {原始名稱: 解析結果}。

    每次查詢之間留 0.15 秒間隔：UniProt 沒有硬性速率限制，但這是別人免費提供的
    公共服務，1748 個名稱慢個幾分鐘無所謂，把對方打掛才是問題。
    """
    out: dict[str, dict] = {}
    if not names:
        return out
    headers = {"Accept": "application/json",
               "User-Agent": "TCM-Onco-Platform/1.0 (research; target standardisation)"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for i, name in enumerate(names):
            out[name] = resolve_name(client, name)
            if i + 1 < len(names):
                time.sleep(pause)
    return out


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)

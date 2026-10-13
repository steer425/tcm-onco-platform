"""成分標準化待確認佇列的重新分類（v1.42.9）。

## 這支要解決的問題

v1.42.9 改了 `tcmsp_pubchem.resolve_name()` 的三條規則：

1. `_qt` 苷元不再被 `cleaned_name()` 靜默剝除，改走明確的 `aglycone_parent` 路徑
2. `_qt` 苷元查回的母體苷若重出糖基組合 → 直接**否決**，不再進待確認
3. 名稱命中多筆時用 TCMSP 分子量挑候選，只有一筆相符就採用

但那只影響**之後新解析**的成分。佇列裡已經躺著的 pending 列（9/10 盤點時 272 筆，
其中 81 筆是糖基差、帶著錯分子的 CID／SMILES／InChIKey）不會自己變。
這支用**資料庫裡已經存的欄位**套同一套規則重判一次，**不連 PubChem**。

判定一律呼叫 `tcmsp_pubchem` 的共用函式（`glycoside_mismatch`、`rank_by_mw`、
`same_compound_form`），**不在這裡重寫一份**——同一個判定寫兩份就會分岔
（v1.40.1 的教訓，見 `rules.md`）。

## 四個桶

| 桶 | 條件 | `--apply` 後 |
|---|---|---|
| 苷元誤配 | 名稱帶 `_qt`、PubChem 較重、差值是 1~4 個糖基組合 | `rejected` |
| 多筆挑中 | 原名命中多筆、只有一筆分子量相符 | `auto`（採用那一筆） |
| 同一化合物 | 原名命中、差一個氫（酸式 vs 陰離子式） | 只有加 `--accept-same` 才改 `auto` |
| 人工審核 | 其他 | 不動 |

「同一化合物」預設不動，要不要整批收請看過報表再決定。
v1.42.10 起**差一個水分子不再算同一化合物**（見 `tcmsp_pubchem.same_compound_form()`）：
正式資料庫跑出來的 Isotanshinone II 是 PubChem 少一個水的脫水產物，不是水合物。

## 不會碰的東西

- 已經 `confirmed`／`rejected` 的列——那是人工審核結果，任何情況都不改
- `auto` 的列
- 人工寫進 `note` 的意見：只有本支改動的列才會更新 `note`，而且會把舊 note 接在後面

使用方式：

    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.reclassify_ingredient_queue                      # 只看報表（預設，不寫入）
    python -m app.reclassify_ingredient_queue --out reports\\requeue.md
    python -m app.reclassify_ingredient_queue --apply              # 寫入：否決＋多筆挑中
    python -m app.reclassify_ingredient_queue --apply --accept-same  # 連同一化合物一起收

可重複執行：第二次跑只會看到第一次沒處理的 pending 列。
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone

from app import models, tcmsp_pubchem as pc
from app.database import SessionLocal

BUCKETS = ("苷元誤配", "多筆挑中", "同一化合物", "人工審核")
NOTE_MAX = 1000
ACTION = "tcmsp_reclassify_ingredient_queue"


def _fix_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("⚠️  DATABASE_URL 沒有設定，會退回本機空的 SQLite。")
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        sys.exit(2)
    print(f"資料庫：{url.split('@')[-1].split('/')[0] if '@' in url else '(local)'}")


def _merge_note(new: str, old: str | None) -> str:
    """新判讀放前面，舊 note 接在後面——不洗掉任何人寫過的東西。"""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = f"[{stamp} 重新分類] {new}"
    if old and old.strip():
        text += f"｜原記錄：{old.strip()}"
    return text[:NOTE_MAX]


def classify_row(row, name: str | None) -> dict:
    """判定一筆 pending 列該進哪個桶。**純函式，不寫資料庫。**

    回傳 {bucket, reason, pick（多筆挑中時採用的候選）, relabel（是否改 method）}。
    """
    cands = _loads(row.candidates)
    aglycone = pc.is_aglycone(name)
    # 以前 `_qt` 是在 cleaned 層被剝掉的；現在那條路叫 aglycone_parent，標籤要跟著對
    relabel = aglycone and row.method == "cleaned"

    single = bool(row.cid) and row.molecular_weight
    if single:
        if aglycone:
            wrong = pc.glycoside_mismatch(name, row.tcmsp_mw, row.molecular_weight)
            if wrong:
                return {"bucket": "苷元誤配", "reason": wrong, "pick": None, "relabel": relabel}
        elif row.method == "exact":
            same = pc.same_compound_form(row.tcmsp_mw, row.molecular_weight)
            if same and pc.mw_check(row.tcmsp_mw, row.molecular_weight)["agree"] is not True:
                return {"bucket": "同一化合物", "reason": same, "pick": None, "relabel": False}
        return {"bucket": "人工審核", "reason": "", "pick": None, "relabel": relabel}

    if len(cands) > 1:
        ranked, agree = pc.rank_by_mw(cands, row.tcmsp_mw, name)
        if aglycone and not agree:
            reasons = [pc.glycoside_mismatch(name, row.tcmsp_mw, c.get("molecular_weight"))
                       for c in ranked]
            if all(reasons):
                return {"bucket": "苷元誤配",
                        "reason": f"{len(ranked)} 筆候選全部是帶糖基的母體苷。{reasons[0]}",
                        "pick": None, "relabel": relabel}
        if len(agree) == 1 and row.method == "exact" and not aglycone:
            hit = agree[0]
            return {"bucket": "多筆挑中",
                    "reason": (f"名稱命中 {len(cands)} 筆化合物，其中只有 CID {hit.get('cid')} "
                               f"的分子量與 TCMSP 相符（差 {hit.get('mw_delta')} Da），自動採用"),
                    "pick": hit, "relabel": False, "ranked": ranked}

    return {"bucket": "人工審核", "reason": "", "pick": None, "relabel": relabel}


def _loads(text):
    try:
        value = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def run(apply: bool = False, accept_same: bool = False, out_path: str | None = None,
        db=None) -> dict:
    """執行重新分類。回傳各桶筆數與實際寫入筆數，供測試斷言。"""
    own = db is None
    db = db or SessionLocal()
    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    try:
        P, I = models.TcmspIngredientPubchem, models.TcmspIngredient
        rows = (db.query(P, I.molecule_name)
                .join(I, I.mol_id == P.mol_id)
                .filter(P.status == "pending")
                .order_by(P.mol_id).all())

        result = {b: [] for b in BUCKETS}
        relabel_n = 0
        for row, name in rows:
            c = classify_row(row, name)
            result[c["bucket"]].append((row, name, c))
            if c["relabel"]:
                relabel_n += 1

        counts = {b: len(v) for b, v in result.items()}
        mode = "寫入" if apply else "只看報表（未寫入）"
        out("# 成分標準化待確認佇列：重新分類")
        out()
        out(f"模式：**{mode}**　｜　待確認列：**{len(rows)}**　｜　"
            f"`_qt` 改標 aglycone_parent：{relabel_n}")
        out()
        out("| 桶 | 筆數 | 處理 |")
        out("|---|---|---|")
        out(f"| 苷元誤配 | {counts['苷元誤配']} | → rejected |")
        out(f"| 多筆挑中 | {counts['多筆挑中']} | → auto |")
        out(f"| 同一化合物 | {counts['同一化合物']} | "
            f"{'→ auto' if accept_same else '不動（加 --accept-same 才收）'} |")
        out(f"| 人工審核 | {counts['人工審核']} | 不動 |")
        out()

        for b in BUCKETS[:3]:
            if not result[b]:
                continue
            out(f"## {b}")
            out()
            out("| mol_id | 成分名稱 | TCMSP MW | PubChem MW | 說明 |")
            out("|---|---|---|---|---|")
            for row, name, c in result[b]:
                pmw = (c["pick"] or {}).get("molecular_weight") if c["pick"] else row.molecular_weight
                why = c["reason"].replace("|", "／")
                out(f"| {row.mol_id} | {name} | {row.tcmsp_mw or '—'} | {pmw or '—'} | {why} |")
            out()

        written = {"rejected": 0, "auto_pick": 0, "auto_same": 0, "relabel": 0}
        if apply:
            for row, name, c in (x for group in result.values() for x in group):
                if c["relabel"]:
                    row.method = "aglycone_parent"
                    written["relabel"] += 1
                if c["bucket"] == "苷元誤配":
                    row.status = "rejected"
                    row.confidence = "0.0"
                    row.note = _merge_note(c["reason"], row.note)
                    written["rejected"] += 1
                elif c["bucket"] == "多筆挑中":
                    hit = c["pick"]
                    for field in ("canonical_smiles", "isomeric_smiles", "inchikey",
                                  "molecular_formula", "molecular_weight", "iupac_name"):
                        setattr(row, field, hit.get(field))
                    row.cid = str(hit.get("cid"))
                    row.mw_delta = (str(hit["mw_delta"])
                                    if hit.get("mw_delta") is not None else None)
                    row.candidates = pc.dumps(c.get("ranked", [])[:5])
                    row.confidence = str(pc.MW_PICK_CONFIDENCE)
                    row.status = "auto"
                    row.note = _merge_note(c["reason"] + "（CAS 未取得，需重新解析才會補上）",
                                           row.note)
                    written["auto_pick"] += 1
                elif c["bucket"] == "同一化合物" and accept_same:
                    row.status = "auto"
                    row.note = _merge_note(c["reason"] + "，整批採用", row.note)
                    written["auto_same"] += 1

            from app.deps import write_audit_log   # 內含 commit
            write_audit_log(db, None, ACTION, target_type="tcmsp_ingredient_pubchem",
                            detail=pc.dumps({"pending_before": len(rows),
                                             "buckets": counts, "written": written,
                                             "accept_same": accept_same}))
            out(f"已寫入：否決 {written['rejected']}、多筆挑中 {written['auto_pick']}、"
                f"同一化合物 {written['auto_same']}、改標 method {written['relabel']}")
        else:
            out("（未寫入。確認報表無誤後加 `--apply` 執行。）")

        if out_path:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(buf.getvalue())
            print(f"\n報表已存：{out_path}")

        return {"pending": len(rows), "counts": counts, "written": written,
                "relabel": relabel_n}
    finally:
        if own:
            db.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="成分標準化待確認佇列的重新分類（不連 PubChem）")
    ap.add_argument("--apply", action="store_true", help="實際寫入（預設只看報表）")
    ap.add_argument("--accept-same", action="store_true",
                    help="連「差一個氫」（酸式 vs 陰離子式）的同一化合物一起改成 auto")
    ap.add_argument("--out", default=None, help="另存成 markdown 檔")
    args = ap.parse_args(argv)
    _fix_console()
    _check_db_target()
    run(apply=args.apply, accept_same=args.accept_same, out_path=args.out)


if __name__ == "__main__":
    main()

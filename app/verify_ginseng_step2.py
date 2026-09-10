"""
目標一 Step 2 驗收：檢查指定藥材的**活性成分**是否已完成 PubChem 標準化。

## 這支腳本要回答的問題

F1-6 頁面上的覆蓋率（1,303 / 2,632 = 49.5%）是**全庫層級**的數字。
它回答不了目標一真正的驗收條件：

    「人參那 22 個活性成分，是不是每一個都拿到了 SMILES／CAS／InChIKey？」

全庫 49.5% 不等於這 22 筆都到手。有可能 22 筆全中，也有可能一筆都沒中——
兩種情況在 F1-6 的卡片上長得一模一樣。所以要逐筆列出來看。

## 為什麼不新增 API 端點

`/tcmsp/ingredient-mapping/review` 只列未採用的狀態（pending／unresolved／
error／rejected），上限 200 筆且沒有 offset，而 pending 有 362 筆、
unresolved 有 967 筆——**用 API 湊不出完整答案**。`/lookup` 則要先有
InChIKey 才查得到，正好是我們想確認有沒有的東西。

這是一次性的驗收查核，不是平台功能，所以做成腳本而不是端點。

## 活性成分的判定沿用既有實作

OB／DL 門檻與篩選一律呼叫 `app.pathways.active_ingredients()`，
**不在這裡重寫一次**。理由見 `rules.md`：v1.40.1 那次事故就是
`/stats` 與 `/resolve` 各寫了一份母體判定，兩邊回答了不同的問題。

使用方式：

    # 一定要先指向正式資料庫，否則會跑在本機空的 SQLite 上
    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.verify_ginseng_step2

    # 換一味藥材（目標二會用到）
    python -m app.verify_ginseng_step2 --herb 黃芪
    python -m app.verify_ginseng_step2 --herb 43

    # 存成 markdown 方便貼回對話
    python -m app.verify_ginseng_step2 --out ginseng_step2.md

這支腳本**唯讀**，不會寫入任何資料，可重複執行。
"""
import argparse
import io
import os
import sys

from sqlalchemy import or_

from app import models, pathways
from app.database import SessionLocal

# 與 app/routers/ingredient_mapping.py 的 ACCEPTED 一致：
# 只有這兩種狀態算「已標準化」，pending 是還沒審過的候選、不能算數。
ACCEPTED = ("auto", "confirmed")

STATUS_CN = {
    "auto": "自動採用", "confirmed": "已確認", "pending": "待確認",
    "rejected": "已否決", "unresolved": "查無結果", "error": "連線失敗",
}


def _fix_console():
    """Windows 主控台預設 cp950，印中文與 ✓✗ 會直接 UnicodeEncodeError。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    """DATABASE_URL 沒設時會靜默退回本機 SQLite——這是本專案最容易誤判
    「已經跑過了」的坑（見 claude/上版流程與跨對話慣例.md 第 3 節）。
    畫面會顯示成功，只是查的是一個空的本機檔案。所以這裡直接擋下來。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("=" * 72)
        print("⚠️  DATABASE_URL 沒有設定，會退回本機 SQLite（tcm_platform.db）。")
        print("    本機檔案通常是空的，跑下去會得到「0 個成分」而不是錯誤訊息。")
        print()
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        print("=" * 72)
        sys.exit(2)
    # 連線字串含密碼，只印主機名讓使用者確認打對了資料庫
    tail = url.split("@")[-1].split("/")[0] if "@" in url else "(unknown host)"
    print(f"資料庫：{tail}")


def _search_herbs(db, keyword: str):
    """整詞比對五個名稱欄位。"""
    like = f"%{keyword}%"
    return (db.query(models.TcmspHerb)
            .filter(models.TcmspHerb.status == "active")
            .filter(or_(models.TcmspHerb.herb_cn_name.ilike(like),
                        models.TcmspHerb.herb_en_name.ilike(like),
                        models.TcmspHerb.herb_pinyin.ilike(like),
                        models.TcmspHerb.child_cn_name.ilike(like),
                        models.TcmspHerb.child_en_name.ilike(like)))
            .order_by(models.TcmspHerb.id).all())


def _relaxed_herbs(db, keyword: str, limit: int = 25):
    """整詞查不到時的放寬搜尋，用來給提示而不是直接採用。

    實際踩到的狀況：TCMSP 匯入的藥材名是**簡體**，用繁體「人參」查
    一筆都不會中，而畫面只說「找不到」，看起來像資料沒匯進來。
    逐字 OR 比對可以跨過繁簡差異——「人參」的「人」還是會命中「人参」。
    """
    kw = (keyword or "").strip()
    conds = []
    for ch in dict.fromkeys(kw):
        if ch.isspace() or ch.isascii():
            continue
        like = f"%{ch}%"
        conds.append(models.TcmspHerb.herb_cn_name.ilike(like))
        conds.append(models.TcmspHerb.child_cn_name.ilike(like))
    if kw.isascii() and len(kw) >= 4:
        like = f"%{kw[:4]}%"
        conds.append(models.TcmspHerb.herb_en_name.ilike(like))
        conds.append(models.TcmspHerb.child_en_name.ilike(like))
        conds.append(models.TcmspHerb.herb_pinyin.ilike(like))
    if not conds:
        return []
    return (db.query(models.TcmspHerb)
            .filter(models.TcmspHerb.status == "active")
            .filter(or_(*conds))
            .order_by(models.TcmspHerb.id).limit(limit).all())


def _print_herbs(rows):
    for h in rows:
        cn = h.herb_cn_name or "-"
        pad = " " * max(0, 10 - sum(2 if ord(c) > 0x2E80 else 1 for c in cn))
        print(f"  {h.id:>5}  {cn}{pad}  {h.herb_pinyin or '-':<14} {h.herb_en_name or '-'}")


def _find_herb(db, keyword: str):
    """回傳單一藥材；找到多筆就列出來讓使用者指定，不自己挑一個。

    「參」會命中 人參／紅參／西洋參 之類的多筆，隨便挑一筆等於默默
    驗錯了對象——那正是這份驗收要避免的事。
    """
    if keyword.isdigit():
        herb = (db.query(models.TcmspHerb)
                .filter(models.TcmspHerb.status == "active",
                        models.TcmspHerb.id == int(keyword)).first())
        if not herb:
            print(f"找不到 herb_id={keyword} 的藥材（或已下架）。")
            sys.exit(1)
        return herb

    rows = _search_herbs(db, keyword)

    if not rows:
        print(f"整詞查不到符合「{keyword}」的藥材。")
        near = _relaxed_herbs(db, keyword)
        if near:
            print()
            print("放寬比對後找到這些，請用 --herb <herb_id> 指定："
                  "（TCMSP 匯入的名稱是簡體，繁體字整詞查不到）")
            print()
            _print_herbs(near)
        else:
            print("放寬比對也沒有結果。用 --list 看完整清單：")
            print("    python -m app.verify_ginseng_step2 --list")
        sys.exit(1)

    exact = [h for h in rows if (h.herb_cn_name or "") == keyword]
    if len(exact) == 1:
        return exact[0]
    if len(rows) == 1:
        return rows[0]

    print(f"「{keyword}」命中 {len(rows)} 筆，請用 --herb <herb_id> 指定其中一個：")
    print()
    _print_herbs(rows)
    sys.exit(1)


def _mapping_by_mol(db, mol_ids):
    """mol_id → 映射列。同一個成分合法可有多筆（唯一鍵是 mol_id+cid），
    已採用的優先，其次才是 pending 之類的候選。"""
    if not mol_ids:
        return {}
    rows = (db.query(models.TcmspIngredientPubchem)
            .filter(models.TcmspIngredientPubchem.mol_id.in_(mol_ids)).all())
    best = {}
    for r in rows:
        cur = best.get(r.mol_id)
        if cur is None:
            best[r.mol_id] = r
        elif r.status in ACCEPTED and cur.status not in ACCEPTED:
            best[r.mol_id] = r
    return best


def _has(v) -> bool:
    return bool((v or "").strip())


def _clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser(description="目標一 Step 2 驗收：藥材活性成分的 PubChem 標準化狀況")
    # 預設用 herb_id 而不是名稱：TCMSP 匯入的藥材名是簡體，
    # 預設寫「人參」會查不到；而「人参」與「人参叶」在名稱上難以自動區分。
    ap.add_argument("--herb", default="336",
                    help="herb_id／藥材中文名（簡體）／英文名（預設：336 人参 Panax Ginseng）")
    ap.add_argument("--list", nargs="?", const="", default=None, metavar="關鍵字",
                    help="列出藥材清單（可加關鍵字過濾）後結束，用來找 herb_id")
    ap.add_argument("--out", default=None, help="另存成 markdown 檔")
    args = ap.parse_args()

    _fix_console()
    _check_db_target()

    if args.list is not None:
        db = SessionLocal()
        try:
            kw = args.list.strip()
            rows = (_search_herbs(db, kw) if kw else
                    db.query(models.TcmspHerb)
                    .filter(models.TcmspHerb.status == "active")
                    .order_by(models.TcmspHerb.id).all())
            if not rows and kw:
                rows = _relaxed_herbs(db, kw, limit=50)
                if rows:
                    print(f"「{kw}」整詞查不到，以下為放寬比對的結果：")
            print(f"共 {len(rows)} 筆")
            print()
            _print_herbs(rows)
        finally:
            db.close()
        return

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    db = SessionLocal()
    try:
        herb = _find_herb(db, args.herb)
        ob_min, dl_min = pathways.adme_thresholds(db)
        # 目標一 Step 1 的定義就在這一支，不要在這裡重寫 OB／DL 條件
        meta = pathways.active_ingredients(db, herb.id, ob_min, dl_min)
        mol_ids = meta["passed"]

        out(f"# Step 2 驗收：{herb.herb_cn_name or herb.herb_en_name}"
            f"（herb_id={herb.id}，{herb.herb_en_name}）")
        out()
        out(f"- 篩選門檻：OB ≥ {ob_min}%、DL ≥ {dl_min}")
        out(f"- 全部成分 {meta['total']} 個 → **活性成分 {meta['passed_count']} 個**"
            f"（ADME 缺值而排除 {meta['missing_adme']} 個）")
        out()

        if not mol_ids:
            out("⚠️ 這味藥材沒有任何成分通過活性篩選，Step 2 無從驗起。")
            return

        names = dict(db.query(models.TcmspIngredient.mol_id,
                              models.TcmspIngredient.molecule_name)
                     .filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all())
        maps = _mapping_by_mol(db, mol_ids)

        out("| # | mol_id | 成分名稱 | 狀態 | CID | SMILES | CAS | InChIKey | 分子量差 |")
        out("|---|---|---|---|---|---|---|---|---|")

        tally = {}
        n_smiles = n_cas = n_inchi = n_accepted = 0
        no_name = []
        problems = []

        for i, mol_id in enumerate(sorted(mol_ids), 1):
            name = names.get(mol_id) or ""
            if not name.strip():
                no_name.append(mol_id)
            m = maps.get(mol_id)

            if m is None:
                tally["未處理"] = tally.get("未處理", 0) + 1
                problems.append((mol_id, name, "未處理"))
                out(f"| {i} | {mol_id} | {_clip(name, 38)} | **未處理** | - | - | - | - | - |")
                continue

            st = STATUS_CN.get(m.status, m.status)
            tally[st] = tally.get(st, 0) + 1
            accepted = m.status in ACCEPTED
            if accepted:
                n_accepted += 1
            else:
                problems.append((mol_id, name, st))

            smi = _has(m.canonical_smiles) or _has(m.isomeric_smiles)
            cas = _has(m.cas_number)
            inchi = _has(m.inchikey)
            # 只有被採用的映射才算數：pending 那筆的 SMILES 可能屬於別的分子
            if accepted:
                n_smiles += 1 if smi else 0
                n_cas += 1 if cas else 0
                n_inchi += 1 if inchi else 0

            mark = lambda b: "✓" if b else "✗"
            delta = (m.mw_delta or "").strip() or "-"
            label = f"**{st}**" if not accepted else st
            out(f"| {i} | {mol_id} | {_clip(name, 38)} | {label} | {m.cid or '-'} | "
                f"{mark(smi)} | {mark(cas)} | {mark(inchi)} | {delta} |")

        total = len(mol_ids)
        pct = lambda n: f"{n}/{total}（{n / total * 100:.1f}%）"

        out()
        out("## 結果")
        out()
        out(f"| 指標 | 數字 |")
        out(f"|---|---|")
        out(f"| 活性成分 | {total} |")
        out(f"| 已標準化（自動採用＋已確認） | {pct(n_accepted)} |")
        out(f"| 其中有 SMILES | {pct(n_smiles)} |")
        out(f"| 其中有 CAS | {pct(n_cas)} |")
        out(f"| 其中有 InChIKey | {pct(n_inchi)} |")
        out()
        out("狀態分佈：" + "、".join(f"{k} {v}" for k, v in sorted(tally.items())))

        if no_name:
            out()
            out(f"⚠️ 有 {len(no_name)} 個成分的名稱是空的，在任何模式下都進不了解析佇列：")
            out("　　" + "、".join(no_name))

        out()
        if n_accepted == total and n_inchi == total:
            out("✅ **Step 2 對這味藥材完成**：全部活性成分都有已採用的映射與 InChIKey。")
        else:
            out(f"❌ **Step 2 對這味藥材尚未完成**：{total - n_accepted} 個成分還沒有已採用的映射"
                f"，{total - n_inchi} 個成分沒有 InChIKey。")
            out()
            out("需要處理的成分：")
            out()
            out("| mol_id | 成分名稱 | 目前狀態 |")
            out("|---|---|---|")
            for mol_id, name, st in problems:
                out(f"| {mol_id} | {_clip(name, 44)} | {st} |")

        out()
        out("> InChIKey 是跨資料庫比對的鍵。沒有它，Step 6 的 DepMap／GDSC 藥物"
            "與文獻裡提到的化合物就對不回 TCMSP 成分——用名稱是永遠對不起來的。")
    finally:
        db.close()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"\n已寫入 {args.out}")


if __name__ == "__main__":
    main()

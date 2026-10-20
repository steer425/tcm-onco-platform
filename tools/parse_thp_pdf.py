"""臺灣中藥典第四版 PDF → 結構化 JSON（v1.51.0，開發工具，伺服器上不會執行）。

    pip install pymupdf opencc-python-reimplemented
    python tools/parse_thp_pdf.py <第四版中文電子書.pdf> <114年修正公告附件.pdf> app/data/thp_v4.json

## 為什麼要自己解析、不爬中藥典資訊網

www.cmthp.mohw.gov.tw 的 robots.txt 禁止自動抓取（2026-10-20 確認）。所以改用衛福部公告的第四版中文 PDF，
在開發機解析一次，結果 JSON 進版控，伺服器啟動時載入——伺服器與使用者電腦都不需要連到資訊網，
也不需要在本機輸入正式資料庫連線字串。

## 版面

正文是 A4 雙欄：x < 300 為左欄、其餘為右欄；每欄由上到下讀完再換下一欄、下一頁。
- 品名區塊：12pt。中文名（細明體，可能兩行，例：「加味逍遙散濃縮製劑」＋「（顆粒、散）」），
  接著粗體大寫的拉丁生藥名（可能兩行），再接粗體英文名。
- 內文 10pt；下標（H₂SO₄ 的 2、4）是 6.5pt，併回同一行。
- 欄位標題頂格（例：「性狀：」），段落首行縮排約 30pt，條列「1.」縮排約 9pt。
- 學名用斜體（TimesNewRomanPS-Italic）——基原的物種學名就從斜體字抓，不靠正規表示式猜。

## 114-07-30 修正公告

公告列出 8 味的修正內容，但沒有逐項說明「整節取代」還是「只換其中幾條」。
**這裡不自動併回原文**，而是把公告原文與備註另存在 amendment 欄，頁面上標示「以修正公告為準」。
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict

import pymupdf

FIELDS = ["性狀", "鑑別", "雜質檢查及其它規定", "含量測定", "貯藏法", "用途分類",
          "性味與歸經", "功能", "用法與用量", "注意事項"]
# 濃縮製劑另有的標題（全書實際出現的只有這四個，2026-10-20 盤點）；存在 extra，不丟
PREP_HEADINGS = ["出典", "處方", "效能", "適應症"]
HEADINGS = FIELDS + PREP_HEADINGS
# 只認上面列出的標題。不能用「頂格＋任意中文＋冒號」：展開溶劑比例換行後，
# 「乙酸乙酯：甲醇…」也會剛好頂格，會被誤當成新欄位（第一版解析就踩到 12 次）
HEAD_RE = re.compile(r"^(" + "|".join(sorted(HEADINGS, key=len, reverse=True)) + r")[：︰:]")   # 當歸的「貯藏法︰」用的是 U+FE30
SUB_RE = re.compile(r"^【飲片】\s*(.+)$")
NUM_RE = re.compile(r"^(\d+\.(?=\s)|\(\d+\)|[①-⑳]|[（(][一二三四五六七八九十]+[)）])")   # 「0.3%」開頭不算編號
END_RE = re.compile(r"[。：；」）)】]$")
VAR_RE = re.compile(r"^[A-Za-z]{1,3}\d?\s*[：:]")
CJK = re.compile(r"[　-〿一-鿿＀-￯]")


# PDF 用 Symbol 字型畫的符號會落在私用區（例：μg 的 μ 是 U+F06D），轉回標準字元
SYMBOL_MAP = str.maketrans({"\uf06d": "μ", "\uf0b4": "×", "\uf02d": "−", "\uf02b": "+", "\uf03d": "=",
                            "\uf025": "%", "\uf0b0": "°", "\uf061": "α", "\uf0d7": "·", "\uf062": "β",
                            "\uf067": "γ", "\uf0a3": "≤", "\uf0b3": "≥", "\uf0b1": "±", "\uf0ae": "→"})


def clean_text(t):
    """NFC 正規化＋符號字型還原。

    這本 PDF 有 3,774 個字是「相容表意文字」（U+F900～FAFF，例：狀 U+F9FA、參 U+F96B），
    外觀跟一般的「狀」「參」一樣，但碼位不同：搜尋找不到、部分字型顯示成空白，
    最嚴重的是**欄位標題「性狀：」比對不到**（第一版只抓到 354 個性狀、其他欄位都有 385 個）、
    中文名「人參」也可能對不上 TCMSP 的「人参」。NFC 會把它們換回統一碼的標準字。
    """
    return unicodedata.normalize("NFC", t).translate(SYMBOL_MAP)


def is_italic(span):
    return bool(span["flags"] & 2) or "Ital" in span["font"]


def page_lines(page):
    """回傳 [(column, y, x0, size, bold, text, italic_runs)]，已依欄、y 排好。"""
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = clean_text(s["text"])
                if not t.strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                if y0 < 40 or y0 > 785:          # 頁首「臺灣中藥典 第四版」、頁碼
                    continue
                spans.append(dict(x0=x0, x1=x1, y=(y0 + y1) / 2, size=s["size"], font=s["font"],
                                  text=t, italic=is_italic(s), bold="Bold" in s["font"]))
    out = []
    for col in (0, 1):
        cs = [s for s in spans if (s["x0"] < 300) == (col == 0)]
        main = sorted([s for s in cs if s["size"] > 9], key=lambda s: (round(s["y"]), s["x0"]))
        rows = []
        for s in main:
            if rows and abs(rows[-1]["y"] - s["y"]) <= 4 and abs(rows[-1]["size"] - s["size"]) < 0.5:
                rows[-1]["spans"].append(s)
            else:
                rows.append(dict(y=s["y"], size=s["size"], spans=[s]))
        for s in [s for s in cs if s["size"] <= 9]:   # 上下標併回所屬的那一行
            if rows:
                # 優先找「有字剛好結束在這個下標左邊」的行（B₁ 的 1 緊接在 B 後面）；
                # 只看 y 最近的話，行距小的段落會掛到下一行，變成「（通則1｜6307）」
                near = [r for r in rows if abs(r["y"] - s["y"]) < 12
                        and any(-1.5 <= s["x0"] - q["x1"] <= 3 for q in r["spans"])]
                r = min(near or rows, key=lambda r: abs(r["y"] - s["y"]))
                r["spans"].append(s)
        for r in rows:
            ss = sorted(r["spans"], key=lambda s: s["x0"])
            text, italics, prev = "", [], None
            for s in ss:
                t = s["text"]
                if prev is not None:
                    gap = s["x0"] - prev["x1"]
                    a, b = text[-1:], t[:1]
                    cjk_a, cjk_b = bool(CJK.match(a or " ")), bool(CJK.match(b or " "))
                    # 中文接英文（「植物蕎麥 Fagopyrum」）間距小也補空白；英數之間照原本間距判斷
                    need = (gap > 0.3) if (cjk_a != cjk_b and re.match(r"[A-Za-z]", (b if cjk_a else a) or "")) else (gap > 1.5)
                    if need and not (cjk_a and cjk_b) and s["size"] > 9:
                        if not text.endswith(" ") and not t.startswith(" "):
                            text += " "
                if s["italic"] and s["size"] > 9:
                    italics.append(t.strip())
                text += t
                prev = s
            out.append(dict(col=col, y=r["y"], x0=ss[0]["x0"], x1=max(q["x1"] for q in ss), size=r["size"],
                            bold=all(s["bold"] for s in ss if s["size"] > 9),
                            text=re.sub(r"\s+", " ", text).strip(), italics=italics))
    return out


def join_lines(lines):
    """同一段的多行接起來：中文與中文直接接，英數之間補空白。

    中文接拉丁字母（例：行尾「植物丁香」＋下一行「Syzygium aromaticum」）也補一個空白——原書排版在這裡有空白，
    v1.51.0 驗證時發現 294 處學名黏在中文後面（「丁香Syzygium」）。數字與標點不補（「2 室」原本就有、「Mey.之」原本沒有）。"""
    s = ""
    for t in lines:
        if not s:
            s = t
        elif (CJK.match(s[-1]) and re.match(r"[A-Za-z]", t[0])) or (re.match(r"[A-Za-z]", s[-1]) and CJK.match(t[0])):
            s += " " + t
        elif CJK.match(s[-1]) or CJK.match(t[0]):
            s += t
        else:
            s += " " + t
    return s


def parse_main(path, first_page, last_page):
    doc = pymupdf.open(path)
    stream = []
    for i in range(first_page, last_page + 1):
        for ln in page_lines(doc[i]):
            ln["page"] = i
            stream.append(ln)

    mons, cur = [], None
    i = 0
    while i < len(stream):
        ln = stream[i]
        # 品名：12pt 中文（非粗體）後面跟著 12pt 粗體
        if abs(ln["size"] - 12) < 0.4 and not ln["bold"] and CJK.search(ln["text"]):
            names, j = [ln["text"]], i + 1
            while j < len(stream) and abs(stream[j]["size"] - 12) < 0.4 and not stream[j]["bold"]:
                names.append(stream[j]["text"]); j += 1
            bolds = []
            while j < len(stream) and abs(stream[j]["size"] - 12) < 0.4 and stream[j]["bold"]:
                bolds.append(stream[j]["text"]); j += 1
            if bolds:
                latin = [b for b in bolds if b.upper() == b]
                english = [b for b in bolds if b.upper() != b]
                cur = dict(name_zh="".join(names), latin_name=" ".join(" ".join(latin).split()),
                           en_name=" ".join(" ".join(english).split()), page=ln["page"],
                           col=ln["col"], body=[])
                mons.append(cur)
                i = j
                continue
        if cur is not None and ln["size"] > 9:
            cur["body"].append(ln)
        i += 1
    return mons


COL_RIGHT = {0: 278.0, 1: 535.0}   # 兩欄滿行的右緣（實測第 1～100 頁：左欄 275～278、右欄 532～535）


def split_segments(m):
    """把一個品項的內文切成：主藥材一段＋每個【飲片】一段。"""
    segs = [dict(name=None, lines=[])]
    for ln in m["body"]:
        sm = SUB_RE.match(ln["text"])
        if sm and ln["size"] > 9:
            segs.append(dict(name=sm.group(1).strip(), lines=[]))
            continue
        segs[-1]["lines"].append(ln)
    return segs


def structure_lines(lines):
    """一段內文 → ({欄位: 文字}, 標題前的段落, 標題前的斜體字)。段落判斷：

    - 頂格且是已知標題 → 新欄位
    - 開頭是編號（1.、(1)、①、（一））→ 新段落
    - **上一行沒寫到欄位右緣 → 上一段結束，這行是新段落**。
      不能只看縮排：段落首行縮 30pt、標題續行縮 27pt，只差 3pt。
    - 換欄、換頁的第一行一律視為接續（欄末常剛好寫滿，判斷不準）
    """
    sections = defaultdict(list)
    cur, prev = "_pre", None
    italics = []
    for ln in lines:
        base = 62.0 if ln["col"] == 0 else 320.0
        t = ln["text"]
        h = HEAD_RE.match(t)
        if h and abs(ln["x0"] - base) < 8:      # 黃蘗的「性狀：」離欄邊 6.7pt；只認已知標題，放寬不會誤判
            cur = h.group(1)
            sections[cur].append(t[h.end():].strip())
            prev = ln
            continue
        if cur == "_pre":
            italics.extend(ln["italics"])
        jumped = prev is not None and (prev["col"] != ln["col"] or prev["page"] != ln["page"])
        if not sections[cur] or NUM_RE.match(t):
            new_para = True
        elif t.startswith("本品") and (ln["x0"] - base) >= 25 and prev is not None and END_RE.search(prev["text"]):
            new_para = True                      # 「本品…」首行縮排、上一句已結束（韭菜子：基原那行剛好寫到右緣）
        elif jumped or prev is None:
            # 換欄／換頁：上一行寫滿與否判斷不準（欄末常剛好寫滿），縮排也不準（巢狀條列縮得更深）——
            # 改看上一行是不是句子結尾
            new_para = bool(END_RE.search(prev["text"])) if prev is not None else False
        elif VAR_RE.match(t):
            new_para = True                      # 公式變數說明（rU：、CS：）各自一行
        else:
            gap = COL_RIGHT[prev["col"]] - prev["x1"]
            ended = bool(END_RE.search(prev["text"]))
            # 上一行沒寫滿：結尾是句末標點 → 段落結束；離右緣很遠（表格列，例：梯度表「0~30 19 81」）→ 自成一行；
            # 其餘是「下一個英數字塞不下而換行」（例：「（通則」｜「6307）」），視為接續
            new_para = sections[cur][-1] != "" and ((gap > 12 and ended) or gap > 60)
        if new_para:
            sections[cur].append(t)
        else:
            sections[cur][-1] = join_lines([sections[cur][-1], t]) if sections[cur][-1] else t
        prev = ln
    fields = {k: "\n".join(x for x in v if x) or None for k, v in sections.items() if k != "_pre"}
    pre = [x for x in sections.get("_pre", []) if x]
    return fields, pre, italics


def to_record(fields, pre, kind):
    """主藥材：第一段是基原，其餘是含量。飲片：「本品飲片為…」是炮製與性狀，其餘是含量。"""
    rec = dict(
        description=fields.get("性狀"), identification=fields.get("鑑別"),
        impurity=fields.get("雜質檢查及其它規定"), assay=fields.get("含量測定"),
        storage=fields.get("貯藏法"), category=fields.get("用途分類"),
        nature_meridian=fields.get("性味與歸經"), functions=fields.get("功能"),
        usage_dosage=fields.get("用法與用量"), precautions=fields.get("注意事項"),
    )
    if kind == "processed":
        desc = [p for p in pre if p.startswith("本品飲片")]
        rest = [p for p in pre if not p.startswith("本品飲片")]
        rec["origin"] = None
        rec["content"] = "\n".join(rest) or None
        if desc:
            rec["description"] = "\n".join(desc + ([rec["description"]] if rec["description"] else []))
    else:
        # 基原＝從第一段接到第一個以「。」結尾的段落（蕎麥、冬蟲夏草的基原在版面上被拆成好幾段）
        origin, i = "", 0
        while i < len(pre):
            origin = join_lines([origin, pre[i]]) if origin else pre[i]
            i += 1
            if origin.endswith("。") and (i >= len(pre) or pre[i].startswith("本品")):
                break
        rec["origin"] = origin or None
        rec["content"] = "\n".join(pre[i:]) or None
    extra = {k: fields.get(k) for k in PREP_HEADINGS if fields.get(k)}
    rec["extra"] = extra or None
    return rec


def structure(m):
    """一個品項 → [主藥材紀錄, 飲片紀錄…]。"""
    segs = split_segments(m)
    fields, pre, italics = structure_lines(segs[0]["lines"])
    is_prep = "濃縮製劑" in m["name_zh"]
    main = dict(name_zh=m["name_zh"], latin_name=m["latin_name"] or None, en_name=m["en_name"] or None,
                kind="preparation" if is_prep else "herb", parent=None,
                book_page=m["page"] - 159, species=[] if is_prep else species_from_italics(italics))
    main.update(to_record(fields, pre, main["kind"]))
    out = [main]
    for sg in segs[1:]:
        f2, pre2, _ = structure_lines(sg["lines"])
        rec = dict(name_zh=sg["name"], latin_name=None, en_name=None, kind="processed",
                   parent=m["name_zh"],
                   book_page=(sg["lines"][0]["page"] - 159) if sg["lines"] else main["book_page"],
                   species=main["species"])
        rec.update(to_record(f2, pre2, "processed"))
        out.append(rec)
    return out


def species_from_italics(chunks):
    """斜體片段 → 物種學名（屬＋種小名，小寫）。屬名單獨一段時接下一段。"""
    words = " ".join(chunks).replace("×", " ").split()
    out, i = [], 0
    while i < len(words) - 1:
        g, s = words[i], words[i + 1]
        if re.fullmatch(r"[A-Z][a-z]+", g) and re.fullmatch(r"[a-z][a-z\-]+", s):
            sp = f"{g} {s}"
            if sp not in out:
                out.append(sp)
            i += 2
        else:
            i += 1
    return out


def parse_synonym_table(path, pages):
    """中藥材基原植物學名修正對照表（通則第 129～131 頁）：第四版新學名 ← 第三版學名。

    TCMSP 是 2014 年的資料，用的多半是舊學名（例：黃耆 Astragalus membranaceus），
    比對 TCMSP 時兩個都要認。版面是「編號／中文名」可能同一行也可能分兩行，所以逐行走狀態機。
    """
    doc = pymupdf.open(path)
    lines = []
    for i in pages:
        lines += [clean_text(l).strip() for l in doc[i].get_text().split("\n") if l.strip()]
    rows, cur, mode, depth = [], None, None, 0
    for l in lines:
        m = re.fullmatch(r"(\d{1,3})\s*([\u4e00-\u9fff]+)?", l)
        if m and (cur is None or mode == "old_done" or mode == "old"):
            if cur:
                rows.append(cur)
            cur = dict(no=int(m.group(1)), name=m.group(2) or "", new="", old="")
            mode = "name" if not m.group(2) else "new"
            continue
        if cur is None:
            continue
        if mode == "name" and re.fullmatch(r"[\u4e00-\u9fff]+", l):
            cur["name"] = l; mode = "new"; continue
        if mode == "new" and l.startswith("("):
            mode = "old"; depth = 0
        if mode == "new":
            cur["new"] = (cur["new"] + " " + l).strip()
        elif mode == "old":
            cur["old"] = (cur["old"] + " " + l).strip()
            depth += l.count("(") - l.count(")")
            if depth <= 0:
                mode = "old_done"
    if cur:
        rows.append(cur)
    for r in rows:
        r["old"] = r["old"][1:-1].strip() if r["old"].startswith("(") and r["old"].endswith(")") else r["old"]
        r["new_species"] = " ".join(r["new"].split()[:2])
        r["old_species"] = " ".join(r["old"].split()[:2])
    return rows


def parse_amendment(path):
    """修正公告：三欄表（品項 x 15～63｜內容說明 63～460｜備註 460～581）。

    列的邊界用「品項欄」那一段的橫線（x 15～63）；整頁寬的橫線不存在、內容欄裡也有內部橫線，不能拿來切列。
    品項名稱垂直置中在列裡；跨頁的列在下一頁沒有品項名稱 → 接到上一個品項。
    """
    doc = pymupdf.open(path)
    out = []
    for page in doc:
        seps = sorted({round(d["rect"].y0) for d in page.get_drawings()
                       if d["rect"].height < 2 and 14 <= d["rect"].x0 <= 16 and 45 <= d["rect"].x1 <= 64})
        words = [(w[0], w[1], w[2], w[3], clean_text(w[4])) for w in page.get_text("words")]
        for top, bot in zip(seps, seps[1:]):
            cells = {"item": [], "content": [], "note": []}
            for w in words:
                x0, y0, x1, y1, t = w[:5]
                ym = (y0 + y1) / 2
                if not (top < ym < bot):
                    continue
                key = "item" if x1 <= 64 else ("note" if x0 >= 459 else "content")
                cells[key].append((ym, x0, t))
            item = "".join(t for _, _, t in sorted(cells["item"]))
            if item == "品項":
                continue                       # 表頭
            content = rows_to_lines(cells["content"])
            note = "".join(rows_to_lines(cells["note"]))
            if item:
                out.append(dict(item=item, content=content, note=note))
            elif out:
                out[-1]["content"] += content
                out[-1]["note"] += note
    for o in out:
        o["content"] = reflow(o["content"])
        o["note"] = o["note"].replace(" ", "")
    return out


SUBHEAD_RE = re.compile(r"^[\u4e00-\u9fff]{2,10}――")


def reflow(lines):
    """公告的內容欄是逐行的；不是新條目（編號、標題、「移動相溶劑――」這類小標、公式變數）的行就接回上一行。"""
    out = []
    for t in lines:
        if not out or NUM_RE.match(t) or HEAD_RE.match(t) or SUBHEAD_RE.match(t) or VAR_RE.match(t) \
                or t.startswith("本品") or re.match(r"^[\u4e00-\u9fff、]+（%）＝", t):
            out.append(t)
        else:
            out[-1] = join_lines([out[-1], t])
    return "\n".join(out)


def rows_to_lines(cells):
    rows = []
    for ym, x0, t in sorted(cells):
        if rows and abs(rows[-1][0] - ym) <= 3:
            rows[-1][1].append((x0, t))
        else:
            rows.append([ym, [(x0, t)]])
    return [join_words(sorted(r[1])) for r in rows]


def join_words(row):
    s = ""
    for x, t in row:
        if s and not (CJK.match(s[-1]) and CJK.match(t[0])):
            s += " "
        s += t
    return s


def build(main_pdf, amend_pdf):
    mons = parse_main(main_pdf, 160, 621)          # 正文第 1～462 頁＝PDF 第 161～622 頁
    recs = []
    for m in mons:
        recs += structure(m)
    # 「薑」只是生薑、乾薑的總標題，沒有內文；資訊網的品項清單也沒有它（365－9 製劑－1＋30 飲片＝385）
    recs = [r for r in recs if not (r["kind"] == "herb" and r["name_zh"] == "薑" and not r["origin"])]
    # 簡體名稱在這裡（開發機）先轉好：TCMSP 的藥材中文名是簡體，比對時伺服器只要做字串比較，
    # 不必為此在正式環境多裝一個繁簡轉換套件（pip install opencc-python-reimplemented，只有這支工具用）
    from opencc import OpenCC
    t2s = OpenCC("t2s")
    for r in recs:
        r["name_s"] = t2s.convert(r["name_zh"])
    amend = {a["item"]: a for a in parse_amendment(amend_pdf)}
    # 資訊網項次（v1.51.1 依使用者提供的資訊網「品項查詢」畫面修正）：
    #   001～385 中藥材項次、386～394 中藥濃縮製劑項次。
    #   001 丁香、002 人參、003 八角茴香、004 三七、005 三稜、006 千年健、007 土茯苓
    #   ——原藥材依書中順序連號，【飲片】**不插在所屬藥材後面**（v1.51.0 插在後面，害 003 以後全部錯位）。
    # 書中原藥材 355 味，356～385 這 30 項是飲片，依書中順序排在原藥材之後（已用資訊網 351-385 頁逐筆核對，2026-10-21）；
    # 濃縮製劑 386～394。seq 仍是書中順序（飲片緊跟所屬藥材），只給內部排序用。
    for i, r in enumerate(recs, 1):
        r["seq"] = i
    order = ([r for r in recs if r["kind"] == "herb"] + [r for r in recs if r["kind"] == "processed"]
             + [r for r in recs if r["kind"] == "preparation"])
    for n, r in enumerate(order, 1):
        r["site_no"] = f"{n:03d}"
    if len(order) != 394 or sum(r["kind"] == "herb" for r in recs) != 355:
        raise SystemExit(f"品項數與資訊網不符：{len(order)}（應為 394＝中藥材 385＋濃縮製劑 9）")
    for r in recs:
        a = amend.get(r["name_zh"]) if r["kind"] == "herb" else None
        r["amendment"] = dict(date="2025-07-30", content=a["content"], note=a["note"]) if a else None
    apply_fixups(recs)
    missing = [k for k in amend if not any(r["name_zh"] == k and r["kind"] == "herb" for r in recs)]
    if missing:
        raise SystemExit(f"修正公告的品項在正文找不到：{missing}")
    return dict(
        source=dict(
            title="臺灣中藥典第四版", publisher="衛生福利部",
            announced="2021-09-24", effective="2022-06-01",
            amendment="2025-07-30 公告修正大黃、川芎、五加皮、辛夷、兒茶、砂仁、柴胡、茯神等 8 品項",
            official_page="https://dep.mohw.gov.tw/DOCMAP/lp-759-108.html",
            detail_url="https://www.cmthp.mohw.gov.tw/Search/SearchDetail?v=4&p={site_no}",
            note="由第四版中文 PDF 解析；版面複雜處（公式、梯度表）可能與原書排版略有差異，以官方頁面為準",
        ),
        synonyms=parse_synonym_table(main_pdf, [150, 151, 152]),
        items=recs,
    )


# 版面解析不了、逐一對照原書人工改正的地方（v1.51.0 交付前驗證時發現）。
# 每一條：(藥材中文名, 欄位, 解析出來的錯誤文字, 原書的正確內容)。用品名不用項次——項次在 v1.51.1 改過一次編法。找不到原文就直接報錯——
# 代表 PDF 換版或解析邏輯變了，要重新對照，不能默默略過。
FIXUPS = [
    # 下標 B1 在 PDF 裡是另一行的小字，被歸到上一條的行尾
    ("紅耆", "impurity", "（通則6307）\nB1\n(2) 本品之黃麴毒素 限量", "（通則6307）\n(2) 本品之黃麴毒素 B1 限量"),
    # 鞣質含量是上下兩行的分數式（分母 W 在下一行），攤平後順序亂掉
    ("五倍子", "assay", "(T1 − T2 + T0)×10 = ×100鞣質含量(%)\nW", "鞣質含量(%) = (T1 − T2 + T0) × 10 ÷ W × 100"),
    ("石榴皮", "assay", "(T1 − T2 + T0)×10 = ×100鞣質含量(%)\nW", "鞣質含量(%) = (T1 − T2 + T0) × 10 ÷ W × 100"),
    ("地榆", "assay", "(T1 − T2 + T0)×10 = ×100鞣質含量(%)\nW", "鞣質含量(%) = (T1 − T2 + T0) × 10 ÷ W × 100"),
]


def apply_fixups(recs):
    by_name = {r["name_zh"]: r for r in recs if r["kind"] == "herb"}
    for name, field, wrong, right in FIXUPS:
        r = by_name[name]
        if wrong not in (r.get(field) or ""):
            raise SystemExit(f"FIXUPS 對不上：{name} {field}（PDF 或解析邏輯變了，請重新對照原書）")
        r[field] = r[field].replace(wrong, right)


if __name__ == "__main__":
    main_pdf, amend_pdf, out_path = sys.argv[1:4]
    data = build(main_pdf, amend_pdf)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    n = len(data["items"])
    print(f"品項 {n}（資訊網品項 {sum(1 for r in data['items'] if r['site_no'])}、"
          f"濃縮製劑 {sum(1 for r in data['items'] if r['kind'] == 'preparation')}）、"
          f"學名修正對照 {len(data['synonyms'])}、修正公告 {sum(1 for r in data['items'] if r['amendment'])} → {out_path}")

"""資料庫備份的還原：把 `backup_service` 產生的加密備份寫進一個**空的**資料庫。

## 為什麼只還原到空資料庫、不覆蓋現有資料

「就地覆蓋正式庫」一旦按錯，連同按錯之前的資料一起沒了，而且沒有第二次機會。
這裡刻意只做非破壞性的還原——目標資料庫只要有任何一張表有資料就拒絕執行。
災難復原的正確流程是：

1. 開一個新的空資料庫（Neon 開新 branch／新 database，或本機 SQLite 檔）
2. `python -m app.restore_backup 備份檔.enc --target <新資料庫網址>`
3. 確認報表上每張表的筆數都對得上
4. 到 Render 把 `DATABASE_URL` 換成新資料庫、重新部署

舊資料庫原封不動留著，換錯了改回原本的網址就好。

另一個用途是**演練**：沒有還原過的備份不算備份。下載備份後在自己電腦上還原到一個
SQLite 檔，對得上筆數，才知道這份備份真的能用。

## 金鑰

備份用 `TCM_JWT_SECRET` 衍生的金鑰加密（`backup_service._get_fernet_key`）。
**換掉 `TCM_JWT_SECRET` 之後，舊備份就解不開了**——換之前要嘛先把舊值記下來，
要嘛換完立刻做一份新備份。還原舊備份時用 `--secret-env` 指定存放舊值的環境變數。

## 與唯讀快取共用

`local_cache.rebuild_local_cache()` 也呼叫這裡的 `restore_dump()`，只是限定 CACHED_TABLES。
還原邏輯只有一份：日期字串轉回 datetime、備份裡多出來的欄位丟掉、PostgreSQL 序號重設。
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, Integer, inspect, text

from app import models
from app.security import SECRET_KEY

CHUNK = 1000


class RestoreError(Exception):
    """還原前檢查不通過（金鑰不符、目標不是空的…），訊息直接給使用者看。"""


def fernet_for(secret: str | None = None) -> Fernet:
    """與 backup_service._get_fernet_key 同一套衍生方式；secret 為 None 時用目前的 TCM_JWT_SECRET。"""
    digest = hashlib.sha256((secret if secret is not None else SECRET_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


KEY_HINT = ("解不開這份備份：金鑰不符。備份是用建立當時的 TCM_JWT_SECRET 加密的，"
            "如果之後換過這個值，請把舊值放進環境變數，再用 --secret-env 指定那個變數名稱。")


def _open(source):
    """bytes／路徑／檔案物件 → (binary 檔案物件, 要不要關)。"""
    import io
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(source), True
    if isinstance(source, (str, os.PathLike)):
        return open(source, "rb"), True
    return source, False


def iter_backup(source, secret: str | None = None):
    """逐段讀出備份內容，記憶體只放一段。產生：
         ("rows", 表名, [列...])   可能同一張表多段
         ("meta", {"format", "exported_at", "counts"})   最後一個

    格式 2（v1.48.3 起，開頭 TCMBAK2）逐行解密；格式 1（舊的一整包）整份解密後依表輸出。
    格式 2 結尾沒有 meta 視為檔案不完整。
    """
    import gzip

    from app.backup_service import MAGIC

    fernet = fernet_for(secret)
    f, close = _open(source)
    try:
        head = f.read(len(MAGIC))
        if head == MAGIC:
            meta, first = None, True
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(gzip.decompress(fernet.decrypt(line)))
                except InvalidToken:
                    if first:
                        raise RestoreError(KEY_HINT) from None
                    raise RestoreError("備份檔中段損毀（某一段解不開），請重新下載一份。") from None
                first = False
                if "meta" in obj:
                    meta = obj["meta"]
                    continue
                if meta is not None:
                    raise RestoreError("備份檔格式異常：摘要之後還有資料。")
                yield ("rows", obj["t"], obj["r"])
            if meta is None:
                raise RestoreError("備份檔不完整：結尾沒有筆數摘要，可能是下載或寫入到一半中斷。請重新下載一份。")
            yield ("meta", meta)
            return
        # 格式 1：整個檔案是一個 Fernet token
        try:
            plain = fernet.decrypt(head + f.read())
        except InvalidToken:
            raise RestoreError(KEY_HINT) from None
        dump = json.loads(plain)
        if not isinstance(dump, dict) or "tables" not in dump:
            raise RestoreError("檔案解得開，但內容不是本系統的備份格式（缺少 tables）。")
        for name, rows in dump["tables"].items():
            yield ("rows", name, rows)
        yield ("meta", {"format": 1, "exported_at": dump.get("exported_at"), "counts": None})
    finally:
        if close:
            f.close()


def _iter_dict(dump: dict):
    for name, rows in (dump.get("tables") or {}).items():
        yield ("rows", name, rows)
    yield ("meta", {"format": dump.get("format", 1), "exported_at": dump.get("exported_at"),
                    "counts": dump.get("counts")})


def decrypt_backup(source, secret: str | None = None) -> dict:
    """整份讀進記憶體成 {"format", "exported_at", "counts", "tables": {表: [列]}}。

    只給測試與小檔案用；伺服器上請用 iter_backup()／restore_dump(source=路徑)，不要整份載入。
    """
    tables: dict = {}
    meta = {}
    for ev in iter_backup(source, secret):
        if ev[0] == "rows":
            tables.setdefault(ev[1], []).extend(ev[2])
        else:
            meta = ev[1]
    return {"format": meta.get("format"), "exported_at": meta.get("exported_at"),
            "counts": meta.get("counts"), "tables": tables}


def _nonempty_tables(engine, names: list[str]) -> list[str]:
    existing = set(inspect(engine).get_table_names())
    out = []
    with engine.connect() as conn:
        for n in names:
            if n in existing and conn.execute(text(f'SELECT 1 FROM "{n}" LIMIT 1')).first():
                out.append(n)
    return out


def _reset_sequences(conn, tables) -> None:
    """PostgreSQL：明確指定整數主鍵寫入後，序號不會跟著前進，下一筆新增會撞主鍵。"""
    if conn.dialect.name != "postgresql":
        return
    for t in tables:
        for c in t.primary_key.columns:
            if isinstance(c.type, Integer) and c.autoincrement in (True, "auto"):
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', '{c.name}'), "
                    f"COALESCE((SELECT MAX(\"{c.name}\") FROM \"{t.name}\"), 0) + 1, false)"))


def restore_dump(engine, source, tables: list[str] | None = None,
                 require_empty: bool = True, secret: str | None = None) -> dict:
    """把備份內容寫進 engine 指向的資料庫，回傳逐表報表。

    source         備份檔路徑／bytes／檔案物件（逐段讀），或 decrypt_backup() 的 dict
    tables         只還原這些表（None＝全部）
    require_empty  True 時目標有任何一張要還原的表已有資料就拒絕（RestoreError）

    全部寫入在同一個交易裡：檔案中途解不開、或筆數與檔尾摘要對不上，整批 rollback，目標不留半套資料。
    """
    events = _iter_dict(source) if isinstance(source, dict) else iter_backup(source, secret)
    all_tables = models.Base.metadata.sorted_tables      # 依外鍵相依順序
    known = {t.name: t for t in all_tables}
    targets = [t for t in all_tables if tables is None or t.name in tables]
    target_map = {t.name: t for t in targets}

    if require_empty:
        busy = _nonempty_tables(engine, list(target_map))
        if busy:
            raise RestoreError(
                f"目標資料庫不是空的（{len(busy)} 張表已有資料，例如 {', '.join(busy[:5])}）。"
                "為了不覆蓋任何現有資料，只能還原到空的資料庫。請另開一個新資料庫再還原。")

    models.Base.metadata.create_all(bind=engine, tables=targets)

    report = {t.name: {"backup": 0, "restored": 0, "dropped_columns": set()} for t in targets}
    seen, unknown, meta = set(), set(), {}
    cols_of = {t.name: {c.name for c in t.columns} for t in targets}
    dt_of = {t.name: [c.name for c in t.columns if isinstance(c.type, DateTime)] for t in targets}

    with engine.begin() as conn:
        for ev in events:
            if ev[0] == "meta":
                meta = ev[1]
                continue
            _, name, rows = ev
            seen.add(name)
            if name not in known:
                unknown.add(name)
                continue
            if name not in target_map:
                continue
            cols, dt_cols, rep = cols_of[name], dt_of[name], report[name]
            clean = []
            for r in rows:
                rep["dropped_columns"].update(k for k in r if k not in cols)
                row = {k: v for k, v in r.items() if k in cols}
                # 備份把 datetime 存成 isoformat 字串（backup_service._serialize_row），
                # SQLite 的 DateTime 欄位不收字串（v1.31.3）
                for c in dt_cols:
                    v = row.get(c)
                    if isinstance(v, str) and v:
                        row[c] = datetime.datetime.fromisoformat(v)
                clean.append(row)
            for i in range(0, len(clean), CHUNK):
                conn.execute(target_map[name].insert(), clean[i:i + CHUNK])
            rep["backup"] += len(rows)
            rep["restored"] += len(clean)

        # 格式 2 檔尾有各表筆數：讀到的跟寫入當時的對不上，就是檔案缺段
        counts = meta.get("counts") or {}
        short = [n for n, c in counts.items() if n in report and report[n]["backup"] != c]
        if short:
            raise RestoreError(f"備份檔內容與檔尾摘要的筆數不符（例如 {', '.join(short[:5])}），檔案可能損毀。"
                               "已全部復原，目標資料庫沒有寫入任何資料。")
        _reset_sequences(conn, targets)

    # 寫完再數一次，不要相信「寫入沒報錯」
    with engine.connect() as conn:
        for name, rep in report.items():
            rep["in_target"] = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            rep["dropped_columns"] = sorted(rep["dropped_columns"])

    return {
        "format": meta.get("format"),
        "exported_at": meta.get("exported_at"),
        "tables": report,
        "missing_in_backup": sorted(n for n in target_map if n not in seen),
        "unknown_in_backup": sorted(unknown),
        "ok": all(v["backup"] == v["in_target"] for v in report.values()),
    }


def format_report(rep: dict) -> str:
    lines = [f"備份時間（UTC）：{rep.get('exported_at')}　格式：{rep.get('format')}", "",
             "| 資料表 | 備份筆數 | 還原後筆數 | 備註 |", "|---|---:|---:|---|"]
    for name, v in rep["tables"].items():
        note = []
        if v["backup"] != v["in_target"]:
            note.append("❌ 筆數不符")
        if v["dropped_columns"]:
            note.append("備份有、現在沒有的欄位已略過：" + "、".join(v["dropped_columns"]))
        if v["backup"] or note:
            lines.append(f"| {name} | {v['backup']} | {v['in_target']} | {'；'.join(note)} |")
    empty = [n for n, v in rep["tables"].items() if not v["backup"]]
    if empty:
        lines += ["", f"備份裡沒有資料的表（{len(empty)} 張）：" + "、".join(empty)]
    if rep["missing_in_backup"]:
        lines += ["", "**備份建立時還不存在的表**（較新版本才加的，已建立為空表）："
                  + "、".join(rep["missing_in_backup"])]
    if rep["unknown_in_backup"]:
        lines += ["", "**備份裡有、目前程式已不存在的表**（未還原）：" + "、".join(rep["unknown_in_backup"])]
    lines += ["", "✅ 每張表筆數都對得上" if rep["ok"] else "❌ 有表的筆數對不上，請勿切換到這個資料庫"]
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse

    from sqlalchemy import create_engine

    p = argparse.ArgumentParser(
        prog="python -m app.restore_backup",
        description="把加密備份還原到一個空的資料庫（不會覆蓋任何現有資料）。")
    p.add_argument("backup_file", help="從系統設定頁下載的 backup_*.enc")
    p.add_argument("--target", required=True,
                   help="目標資料庫網址，例如 sqlite:///restored.db（必須是空的）")
    p.add_argument("--secret-env", default=None,
                   help="備份建立時的 TCM_JWT_SECRET 若已更換，把舊值放進某個環境變數，在這裡填變數名稱")
    p.add_argument("--report", default=None, help="把報表另存成 Markdown 檔")
    a = p.parse_args(argv)

    secret = None
    if not a.secret_env and "TCM_JWT_SECRET" not in os.environ:
        print("⚠️ 這個視窗沒有設定 TCM_JWT_SECRET，會用開發用的預設值解密，正式環境的備份一定解不開。\n"
              "   請先設定與 Render 相同的值：$env:TCM_JWT_SECRET=\"...\"（PowerShell）\n")
    if a.secret_env:
        secret = os.environ.get(a.secret_env)
        if not secret:
            print(f"⛔ 環境變數 {a.secret_env} 沒有值。")
            return 2
    try:
        if not os.path.exists(a.backup_file):
            raise FileNotFoundError(a.backup_file)
        engine = create_engine(a.target)
        rep = restore_dump(engine, a.backup_file, secret=secret)
    except RestoreError as exc:
        print(f"⛔ {exc}")
        return 2
    except FileNotFoundError:
        print(f"⛔ 找不到檔案：{a.backup_file}")
        return 2
    txt = format_report(rep)
    print(txt)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
    return 0 if rep["ok"] else 1

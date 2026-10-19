"""資料庫備份還原（v1.48.2）— 驗證。

執行：`python -m tests.test_backup_restore`（從專案根目錄）。不連外網、不起 app。

最重要的斷言：
  1. 備份 → 還原到空資料庫，**每張表逐列內容一模一樣**（不只是筆數）
  2. 目標不是空的就拒絕——任何情況都不會覆蓋現有資料
  3. 金鑰不符給看得懂的訊息（換過 TCM_JWT_SECRET 是最可能的情境）
  4. 舊備份遇到新 schema（多欄、少表）照樣能還原，報表寫清楚差異
  5. 唯讀快取重建走同一支 restore_dump
  6. （v1.48.3）格式 2 分段串流：記憶體與資料量無關；檔案被截斷或中段損毀 → 拒絕且整批 rollback；
     舊格式 1 的備份照樣能還原；伺服器重啟留下的「進行中」紀錄開機時改成失敗
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = "test_backup_src.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{SRC}")
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。")
if os.path.exists(SRC):
    os.remove(SRC)

import copy  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import backup_restore as br, local_cache, models  # noqa: E402
from app.backup_service import create_encrypted_backup  # noqa: E402
from app.database import Base, SessionLocal, engine as src_engine  # noqa: E402
from tests.test_depmap_page import seed  # noqa: E402

MEM_SCRIPT = r"""
import os, sys, resource
os.environ["DATABASE_URL"] = "sqlite:///" + sys.argv[1]
from app.database import Base, engine, SessionLocal
from app import models, backup_service
if sys.argv[2] == "make":
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        for k in range(0, 150000, 10000):
            c.execute(models.DepMapGeneDependency.__table__.insert(),
                      [{"id": f"x{i:08d}", "depmap_id": "ACH-1", "gene_symbol": f"G{i}", "gene_effect": "-0.7",
                        "release": "24Q2"} for i in range(k, k + 10000)])
    sys.exit(0)
import tracemalloc
db = SessionLocal()
tracemalloc.start()
p, size = backup_service.create_encrypted_backup(db)
peak = tracemalloc.get_traced_memory()[1] / 1024 / 1024
tracemalloc.stop()
os.remove(p)
print(f"rows=150000 file={size/1024/1024:.1f}MB grow={peak:.1f} (Python 配置峰值 MB)")
"""
FAIL = []
TMP = Path(tempfile.mkdtemp(prefix="restore_test_"))


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra != '' else ''}")
    if not cond:
        FAIL.append(label)


def rows_of(engine, table):
    with engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(select(table))]
    pk = [col.name for col in table.primary_key.columns]
    return sorted(rows, key=lambda r: tuple(str(r[k]) for k in pk))


def target(name):
    return create_engine(f"sqlite:///{TMP / name}")


def main():
    print("\n" + "=" * 60)
    print("資料庫備份還原 驗證")
    print("=" * 60)

    Base.metadata.create_all(bind=src_engine)
    db = SessionLocal()
    seed(db)   # TCMSP、DepMap、使用者
    u = db.query(models.User).first()
    db.add(models.AuditLog(actor_user_id=u.id, actor_account=u.account, action="test_action",
                           detail="含中文與 emoji ✅", created_at=datetime.datetime(2026, 10, 1, 8, 30, 15)))
    db.add(models.LiteratureSearch(herb_id=336, gene_symbol="BCL2", query_term='"x"[tiab]',
                                   total_count=3, n_fetched=1, status="ok"))
    db.commit()
    path, size = create_encrypted_backup(db)
    db.close()
    raw = open(path, "rb").read()
    dump = br.decrypt_backup(raw)
    n_rows = sum(len(v) for v in dump["tables"].values())
    check("建立加密備份並解得開", size > 0 and n_rows > 30, (size, n_rows))
    from app.backup_service import MAGIC
    check("**新備份是格式 2（分段）**，檔頭 TCMBAK2、檔尾帶各表筆數",
          raw.startswith(MAGIC) and dump["format"] == 2
          and dump["counts"]["tcmsp_herbs"] == 2 and sum(dump["counts"].values()) == n_rows, dump.get("counts", {}).get("tcmsp_herbs"))
    check("沒有留下 .partial 暫存檔", not list(Path(path).parent.glob("*.partial")))

    print("\n【還原到空的 SQLite】")
    eng = target("restored.db")
    rep = br.restore_dump(eng, dump)
    check("報表 ok：每張表筆數對得上", rep["ok"], [k for k, v in rep["tables"].items() if v["backup"] != v["in_target"]])
    check("所有資料表都建立了", set(rep["tables"]) == {t.name for t in models.Base.metadata.sorted_tables})
    diff = [t.name for t in models.Base.metadata.sorted_tables
            if rows_of(src_engine, t) != rows_of(eng, t)]
    check("**每張表逐列內容與來源完全相同**（含日期時間、布林、列舉、中文）", not diff, diff)
    log = rows_of(eng, models.AuditLog.__table__)
    check("日期時間還原成 datetime、到秒都對",
          any(r["created_at"] == datetime.datetime(2026, 10, 1, 8, 30, 15) for r in log))
    s = eng.connect()
    check("整數主鍵（tcmsp_herbs.id）照原值還原",
          sorted(r[0] for r in s.execute(select(models.TcmspHerb.id))) == [336, 999])
    s.close()

    print("\n【不覆蓋任何現有資料】")
    try:
        br.restore_dump(eng, dump)
        check("**目標已有資料 → 拒絕**", False, "沒有拒絕")
    except br.RestoreError as exc:
        check("**目標已有資料 → 拒絕**，並說明要另開新資料庫",
              "不是空的" in str(exc) and "另開" in str(exc), str(exc)[:80])
    check("被拒絕後目標資料沒有變動",
          not [t.name for t in models.Base.metadata.sorted_tables if rows_of(src_engine, t) != rows_of(eng, t)])
    half = target("half.db")
    models.Base.metadata.create_all(bind=half)
    with half.begin() as c:
        c.execute(models.SystemSetting.__table__.insert(), [{"key": "x", "value": "1"}])
    try:
        br.restore_dump(half, dump)
        check("只有一張表有資料也拒絕", False)
    except br.RestoreError:
        check("只有一張表有資料也拒絕", True)
    empty_schema = target("empty_schema.db")
    models.Base.metadata.create_all(bind=empty_schema)
    check("已建好表但全空 → 允許還原", br.restore_dump(empty_schema, dump)["ok"])

    print("\n【金鑰】")
    try:
        br.decrypt_backup(raw, secret="some-other-secret")
        check("金鑰不符 → 拒絕", False)
    except br.RestoreError as exc:
        check("**金鑰不符 → 說明是 TCM_JWT_SECRET 換過、要用 --secret-env**",
              "TCM_JWT_SECRET" in str(exc) and "--secret-env" in str(exc), str(exc)[:80])
    try:
        br.decrypt_backup(br.fernet_for().encrypt(b'{"hello": 1}'))
        check("不是備份格式 → 拒絕", False)
    except br.RestoreError as exc:
        check("解得開但不是備份格式 → 拒絕", "tables" in str(exc))

    print("\n【舊備份 × 新 schema】")
    old = copy.deepcopy(dump)
    for r in old["tables"]["tcmsp_herbs"]:
        r["legacy_column"] = "舊版欄位"
    del old["tables"]["literature_evidence"]
    old["tables"]["removed_table"] = [{"id": "1"}]
    rep = br.restore_dump(target("drift.db"), old)
    check("備份多出的欄位略過並列在報表", rep["tables"]["tcmsp_herbs"]["dropped_columns"] == ["legacy_column"])
    check("備份建立時還沒有的表 → 建空表、列在報表", rep["missing_in_backup"] == ["literature_evidence"])
    check("備份裡有、程式已沒有的表 → 不還原、列在報表", rep["unknown_in_backup"] == ["removed_table"])
    check("其餘照常、ok", rep["ok"])
    txt = br.format_report(rep)
    check("報表文字含三種差異說明",
          "legacy_column" in txt and "literature_evidence" in txt and "removed_table" in txt and "✅" in txt)

    print("\n【唯讀快取重建走同一支 restore_dump】")
    local_cache.LOCAL_CACHE_DB_PATH = TMP / "cache" / "local_query_cache.db"
    local_cache._local_engine = None

    class Job:
        file_path = path
    n = local_cache.rebuild_local_cache(Job())
    want = sum(len(dump["tables"].get(t, [])) for t in local_cache.CACHED_TABLES)
    check("寫入筆數 = 備份中 CACHED_TABLES 的筆數", n == want, (n, want))
    ceng = create_engine(f"sqlite:///{local_cache.LOCAL_CACHE_DB_PATH}")
    from sqlalchemy import inspect
    names = set(inspect(ceng).get_table_names())
    check("快取只建 CACHED_TABLES（不含使用者、稽核等帳號資料）",
          names == set(local_cache.CACHED_TABLES) and "users" not in names and "audit_logs" not in names,
          sorted(names - set(local_cache.CACHED_TABLES)))
    check("重建第二次（檔案已存在）也成功", local_cache.rebuild_local_cache(Job()) == want)
    ceng.dispose()

    print("\n【格式 2：截斷與損毀】")
    lines = raw.split(b"\n")
    cut = b"\n".join(lines[:-2]) + b"\n"          # 少了最後一段（meta）
    t_eng = target("truncated.db")
    try:
        br.restore_dump(t_eng, cut)
        check("**檔案被截斷（缺檔尾摘要）→ 拒絕**", False, "沒有拒絕")
    except br.RestoreError as exc:
        check("**檔案被截斷（缺檔尾摘要）→ 拒絕**", "不完整" in str(exc), str(exc)[:60])
    with t_eng.connect() as c:
        left = sum(c.execute(text(f'SELECT COUNT(*) FROM "{t.name}"')).scalar()
                   for t in models.Base.metadata.sorted_tables)
    check("**截斷時整批 rollback，目標沒有留下半套資料**", left == 0, left)
    bad = lines[:]
    bad[3] = bad[3][:-10] + b"AAAAAAAAAA"             # 中段某一行壞掉
    try:
        br.restore_dump(target("corrupt.db"), b"\n".join(bad))
        check("中段損毀 → 拒絕", False)
    except br.RestoreError as exc:
        check("中段損毀 → 拒絕並說明", "損毀" in str(exc), str(exc)[:60])
    import gzip as _gz
    f = br.fernet_for()
    idx = next(i for i, ln in enumerate(lines[1:-1], start=1)
               if ln and json.loads(_gz.decompress(f.decrypt(ln))).get("r"))
    dropped = lines[:]
    del dropped[idx]                                 # 少一段有資料的段落，但檔尾摘要還在
    try:
        br.restore_dump(target("missing_chunk.db"), b"\n".join(dropped))
        check("少一段資料 → 筆數與檔尾摘要不符 → 拒絕", False)
    except br.RestoreError as exc:
        check("少一段資料 → 筆數與檔尾摘要不符 → 拒絕", "筆數不符" in str(exc), str(exc)[:60])

    print("\n【舊格式 1 相容】")
    v1 = br.fernet_for().encrypt(json.dumps({"exported_at": "2026-08-11T00:00:00", "tables": dump["tables"]},
                                            ensure_ascii=False, default=str).encode())
    rep1 = br.restore_dump(target("v1.db"), v1)
    check("8/11 那種舊格式備份照樣能還原", rep1["ok"] and rep1["format"] == 1, rep1["format"])

    print("\n【記憶體不隨資料量成長】")
    menv = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    subprocess.run([sys.executable, "-c", MEM_SCRIPT, str(TMP / "mem.db"), "make"], env=menv, check=True)
    mem = subprocess.run([sys.executable, "-c", MEM_SCRIPT, str(TMP / "mem.db"), "backup"],
                         capture_output=True, text=True, encoding="utf-8",
                         env={k: v for k, v in os.environ.items() if k != "DATABASE_URL"})
    print("   ", mem.stdout.strip()[-160:], mem.stderr.strip()[-300:])
    try:
        grow = float(mem.stdout.strip().split("grow=")[1].split()[0])
    except Exception:  # noqa: BLE001
        grow = 9999
    check("**15 萬列備份時，記憶體增加 < 40 MB**（舊寫法 40 萬列峰值 546 MB）", grow < 40, grow)

    print("\n【網頁端：下載串流、伺服器重啟留下的紀錄】")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        tok = client.post("/auth/login", json={"account": "admin", "password": "0000"}).json()["access_token"]
        A = {"Authorization": f"Bearer {tok}"}
        r = client.post("/system-settings/backup-database", headers=A)
        jid = r.json()["id"]
        jobs = client.get("/backup-jobs", headers=A).json()
        job = next(j for j in jobs if j["id"] == jid)
        check("建立備份（背景工作）→ success", job["status"] == "success", job["status"])
        d = client.get(f"/system-settings/backup-database/{jid}/download", headers=A)
        check("下載 200、內容是格式 2、帶附件檔名",
              d.status_code == 200 and d.content.startswith(MAGIC)
              and 'filename="backup_' in d.headers.get("content-disposition", ""), d.headers.get("content-disposition"))
        jdb = SessionLocal()
        fp = jdb.query(models.BackupJob).filter_by(id=jid).first().file_path
        jdb.close()
        os.remove(fp)
        d = client.get(f"/system-settings/backup-database/{jid}/download", headers=A)
        check("伺服器上檔案已不在 → 404 並說明要重新建立、立刻下載",
              d.status_code == 404 and "重新建立" in d.json()["detail"], d.text[:80])
        jdb = SessionLocal()
        jdb.add(models.BackupJob(status=models.BackupStatus.running, notes="背景處理中"))
        jdb.commit()
        jdb.close()
    with TestClient(app) as client:      # 模擬伺服器重啟
        jdb = SessionLocal()
        stuck = jdb.query(models.BackupJob).filter(models.BackupJob.status == models.BackupStatus.running).count()
        last = jdb.query(models.BackupJob).order_by(models.BackupJob.started_at.desc()).first()
        jdb.close()
        check("**重啟後不再有「進行中」的紀錄**，改成失敗並寫明原因",
              stuck == 0 and last.status == models.BackupStatus.failed and "重新啟動" in (last.notes or ""),
              (stuck, last.status, last.notes))

    print("\n【命令列工具】")
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TCM_JWT_SECRET")}
    out = subprocess.run([sys.executable, "-m", "app.restore_backup", path,
                          "--target", f"sqlite:///{TMP / 'cli.db'}", "--report", str(TMP / "r.md")],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    check("還原成功 → exit 0、印出 ✅", out.returncode == 0 and "每張表筆數都對得上" in out.stdout, out.stdout[-200:] + out.stderr[-300:])
    check("沒設 TCM_JWT_SECRET 會先警告", "沒有設定 TCM_JWT_SECRET" in out.stdout)
    check("報表另存檔案", (TMP / "r.md").exists())
    out = subprocess.run([sys.executable, "-m", "app.restore_backup", path,
                          "--target", f"sqlite:///{TMP / 'cli.db'}"],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    check("**同一個目標再跑一次 → exit 2、拒絕覆蓋**", out.returncode == 2 and "不是空的" in out.stdout, out.stdout[-200:])
    env2 = {**env, "OLD_SECRET": "wrong"}
    out = subprocess.run([sys.executable, "-m", "app.restore_backup", path, "--secret-env", "OLD_SECRET",
                          "--target", f"sqlite:///{TMP / 'cli2.db'}"],
                         capture_output=True, text=True, encoding="utf-8", env=env2)
    check("--secret-env 指到錯的值 → 金鑰不符、exit 2", out.returncode == 2 and "金鑰不符" in out.stdout, out.stdout[-200:])
    out = subprocess.run([sys.executable, "-m", "app.restore_backup", "nope.enc",
                          "--target", f"sqlite:///{TMP / 'cli3.db'}"],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    check("找不到備份檔 → exit 2", out.returncode == 2 and "找不到檔案" in out.stdout)

    os.remove(path)
    src_engine.dispose()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 備份還原驗證全部通過")


if __name__ == "__main__":
    main()

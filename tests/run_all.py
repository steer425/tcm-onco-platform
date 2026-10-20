"""一鍵跑完 tests/ 底下所有驗收腳本（v1.49.3）。

    python -m tests.run_all              全部跑
    python -m tests.run_all -k news      只跑名稱含 news 的
    python -m tests.run_all --list       只列出會跑哪些
    python -m tests.run_all -v           失敗時印出完整輸出（預設只印最後 40 行）

也可以用 `python -m pytest tests/ -q`，跑的是同一份清單（見 tests/test_all_scripts.py）。

## 為什麼需要這支

這個 repo 的測試都是「手寫的驗收腳本」：用 `python -m tests.xxx` 執行、自己印 ✅／❌、
有失敗就以非零結束碼結束，不是 pytest 慣例的 `def test_*`。結果是：

  - `python -m pytest tests/` 回報 collected 0 items——**看起來有跑，其實一項都沒驗**；
  - rules.md 第九章的上版清單手列 6 支，但 tests/ 底下已經有 15 支，另外 9 支沒人記得跑。

這支程式自己掃 tests/，新增的腳本不用再改任何清單就會被跑到。

## 安全：一律不帶 DATABASE_URL

每支腳本都會寫入、刪除資料。v1.43.0 發生過：同一個 PowerShell 視窗先前為了跑維運腳本設了
`$env:DATABASE_URL`（Neon），測試就直接連上正式庫。各腳本開頭已有「非 SQLite 就拒絕執行」的檢查，
這裡再多一層：**傳給子程序的環境變數一律拿掉 DATABASE_URL**，讓每支腳本都退回自己的 SQLite 測試檔。

## 判定

結束碼非零＝失敗。另外，結束碼是 0 但輸出裡有 ❌ 也算失敗——
防的是日後有人寫了新腳本卻忘了在最後 `raise SystemExit(1)`，畫面上紅了、結束碼卻是成功。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
TIMEOUT_SECONDS = 900        # 最久的 test_backup_restore 約 20 秒；15 分鐘只是防卡死
TAIL_LINES = 40
FAIL_MARK = "❌"

# 不是驗收腳本、不要被掃進來的檔案
EXCLUDE = {"run_all.py", "test_all_scripts.py", "conftest.py"}


@dataclass
class Script:
    name: str        # 顯示用，例如 test_pathways.py
    kind: str        # py / js
    path: Path

    def command(self) -> list[str] | None:
        if self.kind == "py":
            return [sys.executable, "-m", f"tests.{self.path.stem}"]
        node = shutil.which("node")
        return [node, str(self.path)] if node else None


@dataclass
class Result:
    script: Script
    status: str      # pass / fail / skip
    seconds: float
    returncode: int | None
    output: str
    reason: str = ""


def discover(keyword: str | None = None) -> list[Script]:
    found = []
    for p in sorted(TESTS.glob("test_*.py")):
        if p.name not in EXCLUDE:
            found.append(Script(p.name, "py", p))
    for p in sorted(TESTS.glob("test_*.js")):
        found.append(Script(p.name, "js", p))
    if keyword:
        found = [s for s in found if keyword.lower() in s.name.lower()]
    return found


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    # Windows 的管線預設用系統編碼（繁中是 cp950），腳本印 ✅ 會直接 UnicodeEncodeError
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_one(s: Script) -> Result:
    cmd = s.command()
    if cmd is None:
        return Result(s, "skip", 0.0, None, "", "找不到 node，略過（裝 Node.js 後即會執行）")
    t0 = time.monotonic()
    try:
        cp = subprocess.run(cmd, cwd=ROOT, env=child_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", errors="replace")
        return Result(s, "fail", time.monotonic() - t0, None, out,
                      f"超過 {TIMEOUT_SECONDS} 秒未結束（可能卡在網路或鎖）")
    out = cp.stdout.decode("utf-8", errors="replace")
    secs = time.monotonic() - t0
    if cp.returncode != 0:
        return Result(s, "fail", secs, cp.returncode, out, f"結束碼 {cp.returncode}")
    if FAIL_MARK in out:
        return Result(s, "fail", secs, 0, out, f"結束碼是 0，但輸出裡有 {FAIL_MARK}（腳本可能忘了以非零結束碼結束）")
    return Result(s, "pass", secs, 0, out)


def tail(text: str, n: int = TAIL_LINES) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="跑完 tests/ 底下所有驗收腳本")
    ap.add_argument("-k", dest="keyword", help="只跑檔名含這個字串的腳本")
    ap.add_argument("--list", action="store_true", help="只列出會跑哪些")
    ap.add_argument("-v", "--verbose", action="store_true", help="失敗時印完整輸出")
    args = ap.parse_args(argv)

    scripts = discover(args.keyword)
    if not scripts:
        print("沒有符合的測試腳本。")
        return 1
    if args.list:
        for s in scripts:
            print(f"  {s.name}")
        print(f"共 {len(scripts)} 支")
        return 0

    if os.environ.get("DATABASE_URL"):
        print("ℹ️ 偵測到 DATABASE_URL，已忽略——測試一律跑在各自的 SQLite 測試檔上，不會碰到它指向的資料庫。\n")

    results = []
    for i, s in enumerate(scripts, 1):
        print(f"[{i:>2}/{len(scripts)}] {s.name} … ", end="", flush=True)
        r = run_one(s)
        results.append(r)
        label = {"pass": "通過", "fail": "失敗", "skip": "略過"}[r.status]
        print(f"{label}（{r.seconds:.1f} 秒）" + (f"　{r.reason}" if r.reason else ""), flush=True)
        if r.status == "fail":
            print("-" * 60)
            print(r.output.rstrip() if args.verbose else tail(r.output))
            print("-" * 60)

    passed = sum(r.status == "pass" for r in results)
    failed = [r for r in results if r.status == "fail"]
    skipped = [r for r in results if r.status == "skip"]
    total = sum(r.seconds for r in results)
    print("\n" + "=" * 60)
    print(f"通過 {passed}　失敗 {len(failed)}　略過 {len(skipped)}　共 {len(results)} 支，{total:.0f} 秒")
    for r in failed:
        print(f"  ❌ {r.script.name}：{r.reason}")
    for r in skipped:
        print(f"  ⏭ {r.script.name}：{r.reason}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

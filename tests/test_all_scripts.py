"""讓 `python -m pytest tests/` 真的跑到東西（v1.49.3）。

每支驗收腳本是一個測試項目，放在獨立子程序裡執行；探索、環境變數處理、成敗判定
全部沿用 tests/run_all.py，**不在這裡另寫一份**。
"""
import sys
from pathlib import Path

import pytest

# `pytest`（不是 `python -m pytest`）不會把專案根目錄放進 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import run_all  # noqa: E402

SCRIPTS = run_all.discover()


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.name for s in SCRIPTS])
def test_script(script):
    r = run_all.run_one(script)
    if r.status == "skip":
        pytest.skip(r.reason)
    assert r.status == "pass", f"{r.reason}\n{run_all.tail(r.output)}"

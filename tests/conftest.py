"""pytest 設定（v1.49.3）。

tests/ 底下的 test_*.py 都是**手寫驗收腳本**，很多在 import 的當下就會設定 DATABASE_URL、
建立資料庫、甚至直接開始跑（例如 test_news_dedupe.py）。讓 pytest 自己去收集它們，
等於在同一個程序裡依序 import 十幾支各自改環境變數的腳本——互相污染，結果不可信。

所以這裡叫 pytest 不要收集它們，只收集 test_all_scripts.py；那支會把每支腳本放進
**獨立的子程序**執行（與 `python -m tests.run_all` 同一套），一支腳本一個測試項目。
"""
collect_ignore_glob = ["test_*.py"]
collect_ignore = []


def pytest_ignore_collect(collection_path, config):
    # 上面的 glob 會連 test_all_scripts.py 也擋掉；它是唯一要收集的
    if collection_path.name == "test_all_scripts.py":
        return False
    return None

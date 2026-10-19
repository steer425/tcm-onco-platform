"""命令列入口：python -m app.restore_backup 備份檔.enc --target sqlite:///restored.db

說明見 app/backup_restore.py。只會還原到空的資料庫，不會覆蓋任何現有資料。
"""
import sys

from app.backup_restore import main

if __name__ == "__main__":
    sys.exit(main())

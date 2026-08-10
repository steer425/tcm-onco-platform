import os
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app import models
from app.deps import get_current_user

router = APIRouter(prefix="/project-info", tags=["Dashboard：專案資訊"])

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_VERSION = "1.29.1"  # 與 app/main.py 的 FastAPI(version=...) 保持同步

SUMMARY_MAX_LEN = 60  # 版本摘要固定長度（超過用刪節號截斷）

DOCS = [
    {"id": "readme", "title": "README", "path": "README.md"},
    {"id": "changelog", "title": "版本更新紀錄", "path": "CHANGELOG.md"},
    {"id": "goals2026", "title": "2026 年工作目標", "path": "docs/2026_goals.md"},
    {"id": "rules", "title": "開發規範（rules.md）", "path": "rules.md"},
]


@router.get("/hosts", summary="查詢主機/服務資訊（Git／Cloudflare／Render／Neon）")
def get_hosts(current_user: models.User = Depends(get_current_user)):
    return [
        {
            "id": "git", "name": "GitHub", "role": "程式碼版本控制",
            "url": "https://github.com/steer425/tcm-onco-platform",
            "detail": "分支：main（正式）",
        },
        {
            "id": "cloudflare", "name": "Cloudflare Pages", "role": "前端靜態網站託管",
            "url": "https://fwc-tcmsp.pages.dev",
            "detail": "Build output directory: frontend；隨 main 分支自動部署",
        },
        {
            "id": "render", "name": "Render", "role": "後端 API 服務",
            "url": "https://tcm-onco-backend.onrender.com/docs",
            "detail": "免費方案，閒置一段時間會休眠，喚醒約需 30~60 秒（點「開啟」會進入 Swagger API 文件頁）",
        },
        {
            "id": "neon", "name": "Neon PostgreSQL", "role": "雲端資料庫",
            "url": "https://neon.tech",
            "detail": "主控台需另外登入 Neon 帳號查看，連線字串設定於 Render 環境變數 DATABASE_URL",
        },
    ]


def _parse_changelog(text: str) -> List[dict]:
    """將 CHANGELOG.md 依 '## v版本號 — 日期（標題）' 切成多筆版本紀錄"""
    pattern = re.compile(r"^## (v[\d.]+)\s*(?:—\s*([\d-]+))?\s*(?:[（(](.*?)[）)])?\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        version, date, title = m.group(1), m.group(2), m.group(3) or ""
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        detail = text[start:end].strip()
        summary = title if title else (detail.split("\n", 1)[0].strip("- ") if detail else "")
        summary_truncated = summary if len(summary) <= SUMMARY_MAX_LEN else summary[:SUMMARY_MAX_LEN] + "..."
        entries.append({
            "version": version, "date": date, "title": title,
            "summary": summary_truncated, "detail": detail,
        })
    return entries


@router.get("/version", summary="查詢版本資訊（目前版本 + 歷史版本摘要/詳細內容）")
def get_version_info(current_user: models.User = Depends(get_current_user)):
    changelog_path = os.path.join(REPO_ROOT, "CHANGELOG.md")
    history = []
    if os.path.isfile(changelog_path):
        with open(changelog_path, encoding="utf-8") as f:
            history = _parse_changelog(f.read())
    return {"current_version": APP_VERSION, "history": history}


@router.get("/docs", summary="查詢專案相關文件列表")
def list_docs(current_user: models.User = Depends(get_current_user)):
    return [{"id": d["id"], "title": d["title"]} for d in DOCS]


@router.get("/docs/{doc_id}", summary="查詢單一文件內容")
def get_doc(doc_id: str, current_user: models.User = Depends(get_current_user)):
    doc = next((d for d in DOCS if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="找不到這份文件")
    full_path = os.path.join(REPO_ROOT, doc["path"])
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail=f"文件檔案不存在：{doc['path']}")
    with open(full_path, encoding="utf-8") as f:
        content = f.read()
    return {"id": doc["id"], "title": doc["title"], "content": content}

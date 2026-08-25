"""從一個網址推斷出可用的新聞來源設定。

管理者只要貼上網址（例如 https://news.qq.com/ch/fx），這支負責回答三件事：

  1. 這個站有沒有 RSS/Atom？有就用 feed，遠比爬 HTML 可靠。
  2. 沒有的話，用通用規則挑得出文章連結嗎？挑得出幾篇？
  3. 站名叫什麼、是中文還是英文站？

**一定會實際抓一次並回報找到幾篇**。這是刻意的：抓不到就不要存進去，
否則問題會延到隔天清晨 4:00 的排程才爆，而且那時沒有人在看。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 常見的 feed 路徑。站方沒在 <head> 掛 rel=alternate 時，試這些通常就中了。
COMMON_FEED_PATHS = ("/rss", "/rss.xml", "/feed", "/feed.xml", "/atom.xml",
                     "/index.xml", "/rss/index.xml", "/feed/")

# 導覽列、頁尾那些一定不是文章的路徑
_NAV_WORDS = ("about", "contact", "login", "signin", "signup", "register", "privacy",
              "terms", "sitemap", "search", "rss", "feed", "help", "faq", "advertise",
              "subscribe", "download", "app", "career", "job", "關於", "聯絡", "登入",
              "註冊", "隱私", "條款", "訂閱", "下載", "招聘", "广告", "关于", "联系")

_CJK = re.compile(r"[一-鿿]")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def _looks_like_feed(text: str, content_type: str) -> bool:
    if "xml" in (content_type or "").lower():
        head = text[:2000].lower()
        return "<rss" in head or "<feed" in head or "rdf:rdf" in head
    head = text[:2000].lower().lstrip()
    return head.startswith("<?xml") and ("<rss" in head or "<feed" in head)


def _feed_entry_count(text: str) -> int:
    """數 feed 裡有幾則。用字串計數而不是完整解析，因為這裡只要知道「有沒有東西」。"""
    low = text.lower()
    return max(low.count("<item"), low.count("<entry"))


def _site_name(soup: BeautifulSoup, url: str) -> str:
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        return og["content"].strip()[:80]
    if soup.title and soup.title.string:
        # 標題常是「文章標題 - 站名」或「站名_頻道」，取最後一段通常最接近站名
        raw = soup.title.string.strip()
        for sep in ("｜", "|", " - ", "–", "—", "_"):
            if sep in raw:
                parts = [p.strip() for p in raw.split(sep) if p.strip()]
                if parts:
                    return max(parts, key=len)[:80] if len(parts) == 1 else parts[-1][:80]
        return raw[:80]
    return urlparse(url).netloc


def _plausible_article_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str]]:
    """用通用規則挑出看起來像文章的連結，回傳 [(網址, 標題)]。

    規則刻意保守：寧可少抓也不要把導覽列、廣告、標籤頁全撈進來——
    那些會直接變成當天的「新聞」，比漏抓更糟。
    """
    host = urlparse(page_url).netloc
    seen: dict[str, str] = {}
    scored: list[tuple[int, str, str]] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        # 只收同站（含子網域）的連結，避免把友站連結、廣告當成文章
        if host not in parsed.netloc and parsed.netloc not in host:
            continue
        path = parsed.path.rstrip("/")
        if not path or path.count("/") < 1:
            continue
        low = path.lower()
        if any(w in low for w in _NAV_WORDS):
            continue

        title = " ".join(a.get_text(" ", strip=True).split())
        min_len = 6 if _CJK.search(title) else 12
        if len(title) < min_len:
            continue
        if absolute in seen:
            continue
        seen[absolute] = title

        # 網址帶數字（文章編號或日期）通常代表是內容頁而不是分類頁
        score = 2 if re.search(r"\d{4,}", path) else 0
        score += 1 if path.count("/") >= 2 else 0
        scored.append((score, absolute, title))

    scored.sort(key=lambda x: -x[0])
    return [(u, t) for _, u, t in scored]


async def probe(url: str, *, contact_email: str = "research@example.org",
                timeout: float = 15.0) -> dict:
    """探測一個網址，回傳可直接存進 news_sources 的設定與試抓結果。"""
    url = normalize_url(url)
    result: dict = {"ok": False, "url": url, "kind": None, "name": "", "homepage": url,
                    "config": {}, "found": 0, "samples": [], "lang": "en",
                    "warnings": [], "error": None}
    if not url:
        result["error"] = "請輸入網址。"
        return result

    headers = {
        "User-Agent": f"TCM-Onco-Platform/1.0 (research aggregation; {contact_email})",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True,
                                 timeout=timeout) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"連不到這個網址：{str(exc)[:200]}"
            return result

        text = resp.text
        ctype = resp.headers.get("content-type", "")

        # (1) 網址本身就是 feed
        if _looks_like_feed(text, ctype):
            count = _feed_entry_count(text)
            result.update(kind="rss", config={"feed_url": str(resp.url)},
                          found=count, homepage=f"{urlparse(url).scheme}://{urlparse(url).netloc}")
            soup = BeautifulSoup(text, "html.parser")
            titles = [t.get_text(strip=True) for t in soup.find_all("title")][1:9]
            result["samples"] = [t for t in titles if t][:8]
            result["name"] = (soup.find("title").get_text(strip=True)
                              if soup.find("title") else urlparse(url).netloc)[:80]
            result["ok"] = count > 0
            if not result["ok"]:
                result["error"] = "這是一個 feed，但裡面沒有任何項目。"
            result["lang"] = "zh" if _CJK.search(" ".join(result["samples"]) + result["name"]) else "en"
            return result

        soup = BeautifulSoup(text, "html.parser")
        result["name"] = _site_name(soup, url)
        result["homepage"] = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        # (2) <head> 裡宣告的 feed，或常見 feed 路徑
        candidates: list[str] = []
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in " ".join(
                v if isinstance(v, list) else [v]).lower()):
            if "rss" in (link.get("type") or "").lower() or "atom" in (link.get("type") or "").lower():
                if link.get("href"):
                    candidates.append(urljoin(url, link["href"]))
        root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        candidates += [root + p for p in COMMON_FEED_PATHS]

        for cand in dict.fromkeys(candidates):
            try:
                r = await client.get(cand)
                if r.status_code != 200:
                    continue
                if not _looks_like_feed(r.text, r.headers.get("content-type", "")):
                    continue
                count = _feed_entry_count(r.text)
                if count <= 0:
                    continue
                fsoup = BeautifulSoup(r.text, "html.parser")
                titles = [t.get_text(strip=True) for t in fsoup.find_all("title")][1:9]
                result.update(kind="rss", config={"feed_url": cand}, found=count, ok=True,
                              samples=[t for t in titles if t][:8])
                result["lang"] = "zh" if _CJK.search(" ".join(result["samples"])) else "en"
                return result
            except Exception:  # noqa: BLE001
                continue

        # (3) 沒有 feed → 通用爬蟲
        links = _plausible_article_links(soup, url)
        result.update(kind="scrape", found=len(links),
                      samples=[t for _, t in links[:8]],
                      config={"list_urls": [url], "item_selector": "a[href]"})
        result["lang"] = "zh" if _CJK.search(" ".join(result["samples"]) + result["name"]) else "en"

        if links:
            result["ok"] = True
            result["warnings"].append(
                "這個站沒有 RSS，改用通用規則挑文章連結。"
                "站方改版時就會失準，請定期到「新聞來源健康度」確認。")
        else:
            result["error"] = "找不到任何看起來像文章的連結。"
            # 內容幾乎都靠 JS 產生的站，伺服器抓回來的只有骨架
            script_count = len(soup.find_all("script"))
            anchor_count = len(soup.find_all("a", href=True))
            if anchor_count < 15 and script_count >= 3:
                result["warnings"].append(
                    f"這個頁面只有 {anchor_count} 個連結卻有 {script_count} 段 JavaScript，"
                    "內容多半是瀏覽器執行 JS 之後才產生的。伺服器端抓不到這種頁面——"
                    "請改用該站的 RSS 網址，或找它有提供靜態列表的版本。")
        return result

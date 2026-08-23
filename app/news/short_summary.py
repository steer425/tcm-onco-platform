"""多語系「簡短摘要」（預設 200 字，長度由 news_settings.summary_length 決定）。

跟 summarizer.py 的分工：
  - summarizer.py 在**收集當下**跑，一次產出繁中標題／摘要／重點／解讀注意事項，
    是文章本身的一部分（存在 news_articles 欄位裡）。
  - 本模組產的是**給人快速掃讀的定長簡述**，而且要能換語系，
    存在 news_article_summaries（每篇 × 每語系一列）。

語系刻意只支援 'zh-TW' / 'en' / 'ko' 三種：
簡體中文由前端全站語系機制以 OpenCC 做繁→簡字形轉換（frontend/js/site-lang.js），
直接沿用繁中那一列即可，不需要另外花一次 API 費用產簡體。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("NEWS_SUMMARY_MODEL", "claude-sonnet-4-5")

SUMMARY_LANGS = ("zh-TW", "en", "ko")

# 前端全站語系代碼（tw/cn/en/ko，見 frontend/js/site-lang.js）對應到儲存用的語系。
# cn 對到 zh-TW 是刻意的：OpenCC 會在前端把繁體字轉成簡體字。
SITE_LANG_TO_SUMMARY_LANG = {"tw": "zh-TW", "cn": "zh-TW", "en": "en", "ko": "ko"}

DEFAULT_CHAR_LIMIT = 200
MIN_CHAR_LIMIT = 60
MAX_CHAR_LIMIT = 600

_LANG_INSTRUCTION = {
    "zh-TW": "用臺灣慣用的繁體中文醫學用語書寫。",
    "en": "Write in English, using standard biomedical terminology.",
    "ko": "한국어로, 표준 의학 용어를 사용하여 작성하십시오.",
}

_MATURITY_HINT = {
    "preclinical": "臨床前（細胞／動物／計算預測），不可推論至病患層級",
    "mixed": "同時含臨床前與人體資料",
    "human": "涉及人體研究",
    "unknown": "原文未明確載明研究層級",
}


def _system_prompt(lang: str, char_limit: int) -> str:
    return f"""\
你是中醫藥系統藥理學研究平台的科研情報編輯。請把每一篇研究情報壓縮成一段
**約 {char_limit} 字以內**的簡短摘要，讓研究人員可以快速掃讀後決定要不要點開原文。

{_LANG_INSTRUCTION[lang]}

嚴格規則：
1. 這是科研輔助情報，不是醫療建議。禁止「可以治療」「有效抗癌」「建議服用」
   「療效顯著」這類宣稱，也不得暗示讀者自行使用任何中藥。
2. 必須忠實反映證據層級。若原文是細胞實驗、動物模型、分子對接或網路藥理預測，
   摘要中要講明，且不得推論到病患層級。
3. 不得杜撰原文沒有的數據、樣本數、p 值或結論。資訊不足就略過，不要填空。
4. 一段連續文字，不要條列、不要標題、不要換行、不要 Markdown。
5. 長度控制在 {char_limit} 字以內，寧可短也不要超過。

輸出格式：只輸出 JSON 陣列，不要有其他文字。每個元素：
{{"id": <輸入的 id，整數>, "summary": "<摘要文字>"}}"""


def _render(idx: int, art: dict) -> str:
    lines = [f"--- id: {idx} ---", f"標題：{art.get('title') or ''}"]
    if art.get("source_name"):
        lines.append(f"來源：{art['source_name']}")
    if art.get("journal"):
        lines.append(f"期刊／主辦：{art['journal']}")
    if art.get("study_design"):
        lines.append(f"研究設計：{art['study_design']}")
    hint = _MATURITY_HINT.get(art.get("evidence_maturity") or "unknown")
    if hint:
        lines.append(f"系統判定證據成熟度：{hint}")
    if art.get("is_safety_signal"):
        lines.append("系統判定：含安全／交互作用訊號")
    body = art.get("abstract") or art.get("summary_zh") or ""
    if body:
        lines.append(f"內文：{body[:2400]}")
    return "\n".join(lines)


def _parse_json_array(text: str) -> list:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    end = t.rfind("]")
    if end > 0:
        try:
            return json.loads(t[: end + 1])
        except json.JSONDecodeError:
            pass
    out = []
    for m in re.finditer(r"\{[^{}]*\}", t, re.S):
        try:
            out.append(json.loads(m.group()))
        except json.JSONDecodeError:
            continue
    return out


def truncate(text: str, char_limit: int) -> str:
    """降級用的截斷。盡量切在句號／句點，切不到才硬切，結尾補刪節號。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or len(text) <= char_limit:
        return text
    window = text[:char_limit]
    for sep in ("。", "! ", "? ", ". ", "；", "; "):
        pos = window.rfind(sep)
        if pos >= char_limit * 0.6:          # 太前面就不要，寧可硬切也不要摘要只剩半句
            return window[: pos + len(sep)].strip()
    return window.rstrip() + "…"


def fallback(art: dict, lang: str, char_limit: int) -> str | None:
    """沒有 API key 或呼叫失敗時的降級。

    韓文刻意回 None——沒有翻譯能力時硬塞中文或英文並標成韓文摘要，
    比不顯示更糟糕（使用者會以為系統壞了，而不是知道「這個語系還沒產生」）。
    """
    if lang == "ko":
        return None
    if lang == "zh-TW":
        base = art.get("summary_zh") or art.get("abstract") or ""
    else:
        base = art.get("abstract") or ""
    base = truncate(base, char_limit)
    return base or None


async def _call(client: httpx.AsyncClient, api_key: str, lang: str, char_limit: int,
                indices: list[int], arts: list[dict]) -> dict[int, str]:
    rendered = "\n\n".join(_render(i, arts[i]) for i in indices)
    resp = await client.post(
        API_URL,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": MODEL,
            # 一篇約 char_limit 字，估 3 token/字再加 JSON 骨架，抓寬一點避免被截斷
            "max_tokens": min(8192, 400 + len(indices) * (char_limit * 3 + 80)),
            "system": _system_prompt(lang, char_limit),
            "messages": [
                {"role": "user",
                 "content": f"請處理以下 {len(indices)} 篇。\n\n{rendered}\n\n只輸出 JSON 陣列。"},
                {"role": "assistant", "content": "["},   # prefill 逼出純 JSON
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "[" + "".join(b.get("text", "") for b in data.get("content", [])
                         if b.get("type") == "text")
    out: dict[int, str] = {}
    for d in _parse_json_array(text):
        if isinstance(d, dict) and "id" in d and d.get("summary"):
            try:
                out[int(d["id"])] = str(d["summary"]).strip()
            except (TypeError, ValueError):
                continue
    return out


async def _generate_async(arts: list[dict], lang: str, char_limit: int, api_key: str,
                          batch_size: int, concurrency: int) -> list[dict]:
    results: list[dict] = [
        {"summary": fallback(a, lang, char_limit), "is_ai": False, "model": None} for a in arts
    ]
    batches = [list(range(i, min(i + batch_size, len(arts))))
               for i in range(0, len(arts), batch_size)]
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        async def run(indices: list[int]) -> None:
            async with sem:
                try:
                    got = await _call(client, api_key, lang, char_limit, indices, arts)
                except Exception as exc:  # noqa: BLE001
                    logger.error("簡短摘要批次失敗（%s），該批改用降級：%s", lang, exc)
                    return
                for i, text in got.items():
                    if 0 <= i < len(results) and text:
                        results[i] = {"summary": truncate(text, char_limit),
                                      "is_ai": True, "model": MODEL}

        await asyncio.gather(*(run(b) for b in batches))
    return results


def generate(arts: list[dict], lang: str, char_limit: int = DEFAULT_CHAR_LIMIT, *,
             api_key: str | None = None, batch_size: int = 6,
             concurrency: int = 3) -> list[dict]:
    """同步介面。回傳與 arts 等長的 list，元素為 {summary, is_ai, model}。

    summary 可能是 None（韓文且無 API key），呼叫端要能接受「這個語系暫時沒有摘要」。
    """
    if lang not in SUMMARY_LANGS:
        raise ValueError(f"不支援的摘要語系：{lang}")
    char_limit = max(MIN_CHAR_LIMIT, min(MAX_CHAR_LIMIT, int(char_limit)))
    if not arts:
        return []
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return [{"summary": fallback(a, lang, char_limit), "is_ai": False, "model": None}
                for a in arts]
    try:
        return asyncio.run(_generate_async(arts, lang, char_limit, api_key,
                                           batch_size, concurrency))
    except Exception as exc:  # noqa: BLE001
        logger.error("簡短摘要整體失敗（%s），全部降級：%s", lang, exc)
        return [{"summary": fallback(a, lang, char_limit), "is_ai": False, "model": None}
                for a in arts]

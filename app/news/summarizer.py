"""AI 中文摘要與解讀注意事項（Anthropic Messages API）。

刻意用 httpx 直接呼叫而不裝 anthropic SDK：httpx 已在 requirements.txt 內，
Render free plan 的建置時間與相依體積都能省下來。

無 API key 或呼叫失敗時自動降級為規則式摘要，不阻斷當日收集流程。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import httpx

from . import ai_client
from .collectors.base import RawItem
from .sources import SOURCE_BY_SLUG

logger = logging.getLogger(__name__)

# 端點與模型改由 ai_client 統一管理（支援 Gemini／Anthropic），這裡不再各自持有。

SYSTEM_PROMPT = """\
你是中醫藥系統藥理學研究平台的科研情報編輯，服務對象是中醫藥研究人員、
醫療 AI 團隊與腫瘤藥物篩選研究者。

你的工作是把英文／中文的官方公告、期刊文獻與臨床試驗登錄，
改寫成精確的繁體中文研究情報摘要。

嚴格規則：
1. 這是科研輔助情報，不是醫療建議。禁止出現「可以治療」「有效抗癌」
   「建議服用」「療效顯著」等宣稱，也不得暗示讀者自行使用任何中藥。
2. 必須忠實反映證據層級。若原文是細胞實驗、動物模型、分子對接或網路藥理預測，
   摘要中要明確寫出，並且不得推論到病患層級。
3. 臨床試驗登錄只代表「正在或曾經研究」，不代表有效。若狀態未完成或無結果，
   必須指出。
4. 不得杜撰原文沒有的數據、樣本數、p 值或結論。資訊不足時就寫「原文未提供」。
5. 用語精確，使用臺灣慣用的繁體中文醫學名詞（例如：隨機對照試驗、統合分析、
   化學治療、標靶治療、免疫治療、交互作用）。

輸出格式：只輸出 JSON 陣列，不要有其他文字。每個元素對應輸入的一篇，欄位：
{
  "id": <輸入的 id，整數>,
  "title_zh": "繁體中文標題，40 字以內，不加標點結尾",
  "summary_zh": "3 到 5 句摘要，說明做了什麼、對象是誰、觀察到什麼、證據層級為何",
  "key_points": ["重點一", "重點二", "重點三"],
  "caveat_zh": "一句解讀注意事項，指出這則情報在推論上的限制"
}"""

MATURITY_NOTE = {
    "preclinical": "本則屬臨床前研究（細胞／動物／計算預測），不可推論至病患層級。",
    "mixed": "本則同時含臨床前與人體資料，引用時請分辨來源。",
    "human": "本則涉及人體研究，仍需檢視樣本數、設計與偏差風險。",
    "unknown": "原文未明確載明研究層級，引用前請回查原始出處。",
}


def _fallback(item: RawItem, meta: dict) -> dict:
    src = SOURCE_BY_SLUG.get(item.source_slug)
    body = re.sub(r"\s+", " ", item.abstract or "").strip()
    return {
        "title_zh": None,
        "summary_zh": (body[:280] + ("…" if len(body) > 280 else "")) if body
                      else f"（{src.name_zh if src else item.source_slug} 公告，詳見原文）",
        "key_points": [],
        "caveat_zh": MATURITY_NOTE[meta["evidence_maturity"]],
        "ai_generated": False,
    }


def _render(idx: int, item: RawItem, meta: dict) -> str:
    src = SOURCE_BY_SLUG.get(item.source_slug)
    lines = [
        f"--- id: {idx} ---",
        f"來源：{src.name_zh if src else item.source_slug}"
        f"（證據層級：{src.evidence_level.value if src else 'unknown'}）",
        f"標題：{item.title}",
    ]
    if item.journal:
        lines.append(f"期刊／主辦：{item.journal}")
    if item.study_design:
        lines.append(f"研究設計：{item.study_design}")
    if item.external_id:
        lines.append(f"識別碼：{item.external_id}")
    lines.append(f"系統判定證據成熟度：{meta['evidence_maturity']}")
    if meta["is_safety_signal"]:
        lines.append("系統判定：含安全／交互作用訊號")
    if item.abstract:
        lines.append(f"內文摘要：{item.abstract[:2200]}")
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
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", t, re.S):
        try:
            out.append(json.loads(m.group()))
        except json.JSONDecodeError:
            continue
    return out


async def _call_batch(client: httpx.AsyncClient, api_key: str,
                      indices: list[int], pairs: list[tuple[RawItem, dict]]) -> dict[int, dict]:
    rendered = "\n\n".join(_render(i, pairs[i][0], pairs[i][1]) for i in indices)
    text = await ai_client.complete(
        client, SYSTEM_PROMPT,
        f"請處理以下 {len(indices)} 篇研究情報。\n\n{rendered}\n\n只輸出 JSON 陣列。",
        max_output_tokens=4096,
    )
    return {int(d["id"]): d for d in _parse_json_array(text)
            if isinstance(d, dict) and "id" in d}


async def _summarize_async(pairs: list[tuple[RawItem, dict]], api_key: str,
                           batch_size: int, concurrency: int) -> list[dict]:
    results = [_fallback(it, mt) for it, mt in pairs]
    batches = [list(range(i, min(i + batch_size, len(pairs))))
               for i in range(0, len(pairs), batch_size)]
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        async def run(indices: list[int]) -> None:
            async with sem:
                try:
                    out = await _call_batch(client, api_key, indices, pairs)
                except Exception as exc:  # noqa: BLE001
                    logger.error("AI 摘要批次失敗，該批改用規則式：%s", exc)
                    return
                for local_id, payload in out.items():
                    if not (0 <= local_id < len(results)):
                        continue
                    r = results[local_id]
                    for key in ("title_zh", "summary_zh", "caveat_zh"):
                        if payload.get(key):
                            r[key] = str(payload[key])
                    if isinstance(payload.get("key_points"), list):
                        r["key_points"] = [str(k) for k in payload["key_points"]]
                    r["ai_generated"] = True

        await asyncio.gather(*(run(b) for b in batches))
    return results


def summarize(pairs: list[tuple[RawItem, dict]], *, api_key: str | None = None,
              batch_size: int = 8, concurrency: int = 3) -> list[dict]:
    """同步介面（供 service.py 呼叫）。無 key 時直接回規則式摘要。"""
    if not ai_client.active_provider() or not pairs:
        return [_fallback(it, mt) for it, mt in pairs]
    try:
        return asyncio.run(_summarize_async(pairs, api_key or "", batch_size, concurrency))
    except Exception as exc:  # noqa: BLE001
        logger.error("AI 摘要整體失敗，全部改用規則式：%s", exc)
        return [_fallback(it, mt) for it, mt in pairs]

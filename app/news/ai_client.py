"""新聞模組的 AI 供應商抽象層（Gemini／Anthropic）。

為什麼要有這一層：摘要與翻譯這件事本身跟「找誰做」無關，
但兩家的端點、標頭、請求與回應結構完全不同。把差異收在這裡，
`summarizer.py`（收集時的中文標題／摘要）與 `short_summary.py`（多語系簡短摘要）
就只要處理「提示詞與解析結果」，不必各自散落一份 HTTP 細節。

供應商選擇（`NEWS_AI_PROVIDER` 可強制指定，否則依序自動偵測）：

  1. `GEMINI_API_KEY`  → Gemini（免費層不需信用卡，本專案的預設選擇）
  2. `ANTHROPIC_API_KEY` → Anthropic
  3. 都沒有 → None，呼叫端一律走降級路徑，不得中斷收集流程

端點與模型名稱都可用環境變數覆寫。這是刻意的：兩家的 API 都還在演進，
真的改版時管理者可以先改環境變數擋著，不必等重新部署程式。
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_URL = os.environ.get("NEWS_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_MODEL = os.environ.get("NEWS_SUMMARY_MODEL", "claude-sonnet-4-5")

GEMINI_URL = os.environ.get("NEWS_GEMINI_URL",
                            "https://generativelanguage.googleapis.com/v1beta/interactions")
GEMINI_MODEL = os.environ.get("NEWS_GEMINI_MODEL", "gemini-3.7-flash")


def _env(name: str) -> str | None:
    """取環境變數並去除前後空白。

    貼上金鑰時夾帶換行是最常見的意外，光看設定畫面（值是遮蔽的）完全看不出來。
    這裡容錯，但檢測端點會把「原始值有夾帶空白」這件事講出來，不默默吃掉。
    """
    value = (os.environ.get(name) or "").strip()
    return value or None


def active_provider() -> str | None:
    """目前實際會使用的供應商。回傳 'gemini' / 'anthropic' / None。"""
    forced = (os.environ.get("NEWS_AI_PROVIDER") or "").strip().lower()
    if forced == "none":
        return None
    if forced in ("gemini", "anthropic"):
        return forced if _env(f"{forced.upper()}_API_KEY") else None
    if _env("GEMINI_API_KEY"):
        return "gemini"
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def provider_model(provider: str | None = None) -> str | None:
    provider = provider or active_provider()
    return {"gemini": GEMINI_MODEL, "anthropic": ANTHROPIC_MODEL}.get(provider or "")


def _build_request(provider: str, system: str, user: str, max_output_tokens: int) -> tuple:
    if provider == "anthropic":
        return ANTHROPIC_URL, {
            "content-type": "application/json",
            "x-api-key": _env("ANTHROPIC_API_KEY") or "",
            "anthropic-version": "2023-06-01",
        }, {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

    return GEMINI_URL, {
        "content-type": "application/json",
        "x-goog-api-key": _env("GEMINI_API_KEY") or "",
    }, {
        "model": GEMINI_MODEL,
        "system_instruction": system,
        "input": user,
        # 要求純 JSON 輸出。不指定 schema 是因為兩支呼叫端各有自己的形狀，
        # 而且解析端本來就對「模型多包了一層 ``` 或少了收尾括號」有容錯。
        "response_format": {"type": "text", "mime_type": "application/json"},
        "generation_config": {"max_output_tokens": max_output_tokens, "temperature": 0.2},
    }


def _extract_text(provider: str, data: dict) -> str:
    if provider == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")

    # Interactions API 把結果放在 output_text；舊的 generateContent 形狀則在
    # candidates[].content.parts[].text。兩種都接，這樣端點若被環境變數改回舊的也還能用。
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    out = []
    for cand in data.get("candidates", []) or []:
        for part in (cand.get("content", {}) or {}).get("parts", []) or []:
            if isinstance(part.get("text"), str):
                out.append(part["text"])
    return "".join(out)


async def complete(client: httpx.AsyncClient, system: str, user: str, *,
                   max_output_tokens: int = 2048, timeout: float = 120.0) -> str:
    """送出一次生成請求，回傳模型輸出的純文字。呼叫端負責解析與容錯。"""
    provider = active_provider()
    if not provider:
        raise RuntimeError("沒有可用的 AI 供應商（未設定 GEMINI_API_KEY 或 ANTHROPIC_API_KEY）")
    url, headers, payload = _build_request(provider, system, user, max_output_tokens)
    resp = await client.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return _extract_text(provider, resp.json())


# ---------------------------------------------------------------------------
# 金鑰檢測
# ---------------------------------------------------------------------------
_HINTS = {
    "invalid": "金鑰不正確或已撤銷，請重新產生後更新環境變數。",
    "forbidden": "金鑰有效但沒有這個模型的權限。",
    "model_not_found": "找不到指定的模型，可用環境變數改成其他模型名稱。",
    "rate_limited": "額度或速率上限已達，稍後再試。",
    "billing": "帳戶額度不足或尚未設定付款方式。",
}

_KEY_ENV = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_EXPECTED_PREFIX = {"gemini": "AIza", "anthropic": "sk-ant-"}


def check_key() -> dict:
    """實際送一次最小請求，確認金鑰真的能用。

    只檢查環境變數存不存在是不夠的——金鑰打錯、過期、額度用盡時變數一樣存在，
    但每次生成都會失敗然後靜靜退回降級，症狀跟「沒設」完全一樣。

    回傳絕不包含金鑰本身，只有長度、廠商公開前綴與「有沒有夾帶空白」——
    設定畫面的值是遮蔽的，這三件事光用看的都看不出來，卻正是 401/400 最常見的原因。
    """
    provider = active_provider()
    if not provider:
        return {"ok": False, "reason": "not_set", "provider": None,
                "message": "後端未設定 GEMINI_API_KEY 或 ANTHROPIC_API_KEY（或值是空白）。"}

    env_name = _KEY_ENV[provider]
    raw = os.environ.get(env_name) or ""
    key = raw.strip()
    diag = {
        "provider": provider,
        "model": provider_model(provider),
        "key_env": env_name,
        "key_length": len(key),
        "key_prefix": key[:14],
        "had_surrounding_whitespace": raw != key,
        "looks_like_expected_key": key.startswith(_EXPECTED_PREFIX[provider]),
    }

    try:
        url, headers, payload = _build_request(provider, "You are a test.", "hi", 8)
        resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    except Exception as exc:  # noqa: BLE001
        logger.error("AI 金鑰檢測連線失敗（%s）：%s", provider, exc)
        return {"ok": False, "reason": "network", **diag,
                "message": f"連不到 {provider} API：{str(exc)[:200]}"}

    if resp.status_code == 200:
        return {"ok": True, "reason": "ok", **diag,
                "message": f"金鑰有效，{provider} 的 {diag['model']} 可正常呼叫。"}

    try:
        body = resp.json()
        detail = str(body.get("error", {}).get("message", ""))[:300]
    except Exception:  # noqa: BLE001
        detail = resp.text[:300]

    reason = {400: "invalid", 401: "invalid", 403: "forbidden",
              404: "model_not_found", 429: "rate_limited"}.get(resp.status_code, "http_error")
    if "credit" in detail.lower() or "billing" in detail.lower() or "quota" in detail.lower():
        reason = "billing" if "credit" in detail.lower() or "billing" in detail.lower() else reason

    extra = []
    if reason in ("invalid", "billing", "http_error"):
        extra.append(f"目前這把金鑰長度 {diag['key_length']} 字元，開頭 {diag['key_prefix']}…")
        if not diag["looks_like_expected_key"]:
            extra.append(f"開頭不是 {_EXPECTED_PREFIX[provider]}，可能貼錯了別的服務的金鑰。")
        if diag["had_surrounding_whitespace"]:
            extra.append("原始值前後夾帶了空白或換行（檢測時已自動去除，但請在後台清乾淨）。")

    return {"ok": False, "reason": reason, **diag,
            "message": (f"HTTP {resp.status_code}：{_HINTS.get(reason, '')} {detail} "
                        + " ".join(extra)).strip()}

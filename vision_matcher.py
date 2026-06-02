"""
Claude Vision API로 이미지가 키워드에 해당하는지 판단
"""

import base64
import requests as req

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MAX_IMAGE_BYTES = 4 * 1024 * 1024   # 4MB 초과 시 건너뜀


def _media_type(data: bytes) -> str:
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if data[:2] == b'\xff\xd8':
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    return "image/jpeg"


def check_image_matches(image_bytes: bytes, keyword: str, api_key: str) -> bool:
    """
    이미지 바이트를 Claude Haiku로 분석하여 keyword와 관련 있으면 True 반환.
    API 오류·사이즈 초과 시 False 반환 (처리 중단 없음).
    """
    if not api_key or not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return False

    b64 = base64.standard_b64encode(image_bytes).decode()
    media = _media_type(image_bytes)

    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 5,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media, "data": b64}
                },
                {
                    "type": "text",
                    "text": (
                        f"이 이미지가 '{keyword}'와 관련 있거나 '{keyword}'를 시각적으로 포함하나요? "
                        f"'yes' 또는 'no'로만 답하세요."
                    )
                }
            ]
        }]
    }

    try:
        res = req.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=20
        )
        if res.status_code == 200:
            answer = res.json()["content"][0]["text"].strip().lower()
            return answer.startswith("yes")
    except Exception:
        pass
    return False


def fetch_and_check(image_url: str, keyword: str, api_key: str, referer: str = "") -> bool:
    """URL에서 이미지를 내려받아 vision check. 실패 시 False."""
    if not api_key:
        return False
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        if referer:
            headers["Referer"] = referer
        r = req.get(image_url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.content) > 500:
            return check_image_matches(r.content, keyword, api_key)
    except Exception:
        pass
    return False

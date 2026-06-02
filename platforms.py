"""
한국 주요 플랫폼 설정
- URL 패턴 감지
- 브라우저 사전 방문(pre-warm) URL
- 플랫폼 이름
"""

_CONFIGS = [
    # ── 네이버 계열 ─────────────────────────────────
    {"match": "smartstore.naver.com",  "name": "네이버 스마트스토어", "prewarm": "https://www.naver.com"},
    {"match": "shopping.naver.com",    "name": "네이버 쇼핑",        "prewarm": "https://www.naver.com"},
    {"match": "blog.naver.com",        "name": "네이버 블로그",       "prewarm": "https://www.naver.com"},
    {"match": "cafe.naver.com",        "name": "네이버 카페",         "prewarm": "https://www.naver.com"},
    {"match": "naver.com",             "name": "네이버",              "prewarm": "https://www.naver.com"},

    # ── 오픈마켓 ────────────────────────────────────
    {"match": "coupang.com",           "name": "쿠팡",                "prewarm": "https://www.coupang.com"},
    {"match": "11st.co.kr",            "name": "11번가",              "prewarm": "https://www.11st.co.kr"},
    {"match": "gmarket.co.kr",         "name": "G마켓",               "prewarm": "https://www.gmarket.co.kr"},
    {"match": "auction.co.kr",         "name": "옥션",                "prewarm": "https://www.auction.co.kr"},
    {"match": "interpark.com",         "name": "인터파크",            "prewarm": "https://shopping.interpark.com"},

    # ── 백화점/대형마트 ─────────────────────────────
    {"match": "ssg.com",               "name": "SSG닷컴",             "prewarm": "https://www.ssg.com"},
    {"match": "lotteon.com",           "name": "롯데온",              "prewarm": "https://www.lotteon.com"},
    {"match": "hyundaihmall.com",      "name": "현대H몰",             "prewarm": "https://www.hyundaihmall.com"},
    {"match": "gsshop.com",            "name": "GS샵",                "prewarm": "https://www.gsshop.com"},
    {"match": "hmall.com",             "name": "홈앤쇼핑",            "prewarm": "https://www.hmall.com"},

    # ── 소셜커머스/특가 ─────────────────────────────
    {"match": "wemakeprice.com",       "name": "위메프",              "prewarm": "https://www.wemakeprice.com"},
    {"match": "tmon.co.kr",            "name": "티몬",                "prewarm": "https://www.tmon.co.kr"},

    # ── 패션 ────────────────────────────────────────
    {"match": "musinsa.com",           "name": "무신사",              "prewarm": "https://www.musinsa.com"},
    {"match": "zigzag.kr",             "name": "지그재그",            "prewarm": "https://zigzag.kr"},
    {"match": "ably.kr",               "name": "에이블리",            "prewarm": "https://m.ably.kr"},
    {"match": "wconcept.co.kr",        "name": "W컨셉",               "prewarm": "https://www.wconcept.co.kr"},
    {"match": "29cm.co.kr",            "name": "29CM",                "prewarm": "https://www.29cm.co.kr"},

    # ── 카카오 계열 ─────────────────────────────────
    {"match": "kakaostore.com",        "name": "카카오스토어",         "prewarm": None},
    {"match": "kakaopage.com",         "name": "카카오페이지",         "prewarm": None},

    # ── 기타 ────────────────────────────────────────
    {"match": "oliveyoung.co.kr",      "name": "올리브영",            "prewarm": "https://www.oliveyoung.co.kr"},
    {"match": "yes24.com",             "name": "YES24",               "prewarm": "https://www.yes24.com"},
    {"match": "aladin.co.kr",          "name": "알라딘",              "prewarm": "https://www.aladin.co.kr"},
]


def detect(url: str) -> dict:
    """URL에서 플랫폼 설정 반환. 없으면 {}"""
    for cfg in _CONFIGS:
        if cfg["match"] in url:
            return cfg
    return {}


def get_prewarm_url(url: str):
    """사전 방문 URL 반환. 없으면 None"""
    return detect(url).get("prewarm")


def get_platform_name(url: str) -> str:
    """플랫폼 이름 반환. 없으면 빈 문자열"""
    return detect(url).get("name", "")

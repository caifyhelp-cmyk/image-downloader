"""
다운로드 핵심 로직
"""

import asyncio
import json
import re
import time
import requests
from pathlib import Path

from vision_matcher import fetch_and_check, check_image_matches

# ══════════════════════════════════════════════
#  브라우저 실행 (여러 방법 순서대로 시도)
# ══════════════════════════════════════════════

async def _launch_browser(p, log_fn=None):
    """
    브라우저 실행 우선순위:
    1. Microsoft Edge  (Windows 10/11 기본 설치)
    2. 시스템 Chrome
    3. ms-playwright chromium (재귀 탐색)
    4. playwright 기본 경로 (개발 환경)
    """
    from browser_setup import system_chrome, find_ms_playwright_chromium

    def _log(msg):
        if log_fn:
            log_fn(msg)

    # 1. Microsoft Edge (Windows 기본 내장)
    try:
        _log("브라우저: Edge 시도...")
        return await p.chromium.launch(headless=True, channel="msedge")
    except Exception as e:
        _log(f"Edge 없음: {e}")

    # 2. 시스템 Chrome
    chrome = system_chrome()
    if chrome:
        try:
            _log(f"브라우저: Chrome 시도 ({chrome})")
            return await p.chromium.launch(headless=True, executable_path=chrome)
        except Exception as e:
            _log(f"Chrome 실패: {e}")

    # 3. ms-playwright chromium (재귀 탐색)
    exe = find_ms_playwright_chromium()
    if exe:
        try:
            _log(f"브라우저: Chromium 시도 ({exe})")
            return await p.chromium.launch(headless=True, executable_path=exe)
        except Exception as e:
            _log(f"Chromium 실패: {e}")

    # 4. 개발 환경 fallback
    _log("브라우저: 기본 경로 시도...")
    return await p.chromium.launch(headless=True)

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name.strip() or "unnamed"


def decode_unicode(obj):
    if isinstance(obj, str):
        return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), obj)
    if isinstance(obj, list):
        return [decode_unicode(i) for i in obj]
    if isinstance(obj, dict):
        return {k: decode_unicode(v) for k, v in obj.items()}
    return obj


def get_base_url(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def download_file(url: str, save_path: Path, base_url: str) -> bool:
    try:
        res = requests.get(url, headers={**BASE_HEADERS, "Referer": base_url}, timeout=30)
        if res.status_code == 200 and len(res.content) > 500:
            save_path.write_bytes(res.content)
            return True
        return False
    except Exception:
        return False


def parse_portfolio_list(html: str) -> list:
    for pattern in [
        r'list_portfolio\s*=\s*(\[.+?\])\s*;',
        r'"list_portfolio"\s*:\s*(\[.+?\])',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                return decode_unicode(json.loads(m.group(1)))
            except Exception:
                pass
    return []


def extract_og_images(html: str, base_url: str) -> list:
    og_matches = re.findall(r'/uploads/[^\s"\'<>]+_og\.[a-zA-Z]+', html)
    seen, urls = set(), []
    for src in og_matches:
        url = base_url.rstrip('/') + src
        if url not in seen:
            seen.add(url)
            urls.append(url)
    if not urls:
        all_matches = re.findall(r'/uploads/[^\s"\'<>]+\.[a-zA-Z]{3,4}', html)
        for src in all_matches:
            if any(x in src for x in ('_crop', '_thumb', '_small')):
                continue
            url = base_url.rstrip('/') + src
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _text_matches(proj: dict, keyword: str) -> bool:
    kw = keyword.lower()
    fields = ["seed_title", "seed_summary", "seed_tags", "seed_category"]
    return any(kw in (proj.get(f) or "").lower() for f in fields)


def _thumb_url(proj: dict, base_url: str) -> str:
    """포트폴리오 항목 썸네일 URL 반환"""
    for key in ("file_org_src", "file_src", "thumb_src"):
        src = proj.get(key) or ""
        if src:
            src = src.replace("\\/", "/")
            if not src.startswith("http"):
                src = base_url.rstrip("/") + "/" + src.lstrip("/")
            return src
    return ""


def apply_filter(projects: list, filter_text: str, api_key: str,
                 base_url: str, log_fn) -> list:
    """
    1단계: 텍스트 매칭 (빠름)
    2단계: 텍스트 미매칭 항목 → 썸네일 이미지 Vision 매칭 (api_key 있을 때만)
    """
    if not filter_text:
        return projects

    text_matched = []
    vision_candidates = []

    for proj in projects:
        if _text_matches(proj, filter_text):
            text_matched.append(proj)
        else:
            vision_candidates.append(proj)

    log_fn(f"텍스트 매칭: {len(text_matched)}개")

    vision_matched = []
    if api_key and vision_candidates:
        log_fn(f"이미지 AI 분석: {len(vision_candidates)}개 대상...")
        for i, proj in enumerate(vision_candidates, 1):
            thumb = _thumb_url(proj, base_url)
            title = (proj.get("seed_title") or f"항목{i}").strip()
            if thumb:
                matched = fetch_and_check(thumb, filter_text, api_key, base_url)
                if matched:
                    log_fn(f"  ✓ 이미지 매칭: {title}")
                    vision_matched.append(proj)
                else:
                    log_fn(f"  ✗ 미매칭: {title}")
            else:
                log_fn(f"  - 썸네일 없음: {title}")
    elif vision_candidates and not api_key:
        log_fn(f"  (AI 분석 키 없음 — 텍스트 매칭만 사용)")

    result = text_matched + vision_matched
    log_fn(f"최종 매칭: {len(result)}개  (텍스트 {len(text_matched)} + 이미지AI {len(vision_matched)})\n")
    return result


async def click_more_buttons(page, log_fn):
    count = 0
    selectors = [
        "text=컨텐츠 더보기", "text=더보기", ".more_btn",
        "button:has-text('more')", "button:has-text('Load more')",
        "[class*='more_btn']", "a:has-text('더보기')",
    ]
    while True:
        clicked = False
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible():
                    await loc.click()
                    await page.wait_for_timeout(2000)
                    count += 1
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            break
    if count:
        log_fn(f"  더보기 {count}회 클릭")
    return count


async def click_next_page(page) -> bool:
    selectors = [
        "a:has-text('다음')", "button:has-text('다음')",
        ".next", "[class*='next']", "a[aria-label='Next']",
        "li.next > a", ".pagination .next",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible():
                await loc.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            pass
    return False


# ══════════════════════════════════════════════
#  이미지 다운로드 모드
# ══════════════════════════════════════════════

async def run_download(url: str, save_dir: Path, log_fn, progress_fn, stop_event,
                       filter_text: str = "", api_key: str = ""):
    from playwright.async_api import async_playwright

    base_url = get_base_url(url)

    async with async_playwright() as p:
        browser = await _launch_browser(p, log_fn)
        page = await browser.new_page()

        log_fn(f"접속 중: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await click_more_buttons(page, log_fn)
        html = await page.content()

        projects = parse_portfolio_list(html)

        if not projects:
            log_fn("포트폴리오 목록 없음 → 페이지 이미지 전체 다운로드")
            img_urls = extract_og_images(html, base_url)
            if not img_urls:
                img_tags = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('img'))
                         .map(i => i.src || i.dataset.src || '')
                         .filter(s => s && !s.includes('data:'))
                """)
                img_urls = list(dict.fromkeys(img_tags))

            # 필터 적용 (Vision 포함)
            if filter_text and img_urls:
                img_urls = await _vision_filter_urls(
                    img_urls, filter_text, api_key, base_url, log_fn)

            log_fn(f"이미지 {len(img_urls)}개 저장")
            save_dir.mkdir(parents=True, exist_ok=True)
            ok = 0
            for i, img_url in enumerate(img_urls, 1):
                if stop_event.is_set():
                    break
                ext = img_url.split('.')[-1].split('?')[0].lower()
                if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                    ext = 'jpg'
                sp = save_dir / f"{i:03d}.{ext}"
                if download_file(img_url, sp, base_url):
                    log_fn(f"  [{i:03d}] OK ({sp.stat().st_size // 1024}KB)")
                    ok += 1
                progress_fn(i, len(img_urls))
                time.sleep(0.2)
            log_fn(f"\n완료! {ok}/{len(img_urls)}개 저장")
            await browser.close()
            return

        projects = apply_filter(projects, filter_text, api_key, base_url, log_fn)
        log_fn(f"프로젝트 {len(projects)}개 처리 시작\n")
        save_dir.mkdir(parents=True, exist_ok=True)
        title_counter = {}
        total_ok = total_fail = 0

        for idx, proj in enumerate(projects, 1):
            if stop_event.is_set():
                log_fn("중단됨")
                break

            title = (proj.get("seed_title") or f"project_{idx}").strip()
            seed_id = proj.get("seed_id", "")
            folder_name = sanitize(title)

            base = folder_name
            if base in title_counter:
                title_counter[base] += 1
                folder_name = f"{base}_{title_counter[base]:02d}"
            else:
                title_counter[base] = 1

            project_dir = save_dir / folder_name
            project_dir.mkdir(parents=True, exist_ok=True)

            log_fn(f"[{idx:03d}/{len(projects)}] {title}")

            img_urls = []
            if seed_id:
                detail_url = f"{base_url}/home/info/{seed_id}"
                try:
                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
                    img_urls = extract_og_images(await page.content(), base_url)
                except Exception as e:
                    log_fn(f"  오류: {e}")

            if not img_urls:
                src = _thumb_url(proj, base_url)
                if src:
                    img_urls = [src]

            log_fn(f"  이미지 {len(img_urls)}개")
            ok = 0
            for i, img_url in enumerate(img_urls, 1):
                if stop_event.is_set():
                    break
                ext = img_url.split('.')[-1].split('?')[0].lower()
                if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                    ext = 'jpg'
                sp = project_dir / f"{i:03d}.{ext}"
                if download_file(img_url, sp, base_url):
                    log_fn(f"    [{i:03d}] OK ({sp.stat().st_size // 1024}KB)")
                    ok += 1
                    total_ok += 1
                else:
                    total_fail += 1
                time.sleep(0.15)

            progress_fn(idx, len(projects))

        log_fn(f"\n{'='*40}")
        log_fn(f"완료!  프로젝트: {len(projects)}개")
        log_fn(f"성공: {total_ok}개  /  실패: {total_fail}개")
        log_fn(f"저장: {save_dir}")
        await browser.close()


# ══════════════════════════════════════════════
#  스크린샷 캡처 모드
# ══════════════════════════════════════════════

async def run_screenshot(url: str, save_dir: Path, log_fn, progress_fn, stop_event,
                         filter_text: str = "", api_key: str = ""):
    from playwright.async_api import async_playwright

    base_url = get_base_url(url)

    async with async_playwright() as p:
        browser = await _launch_browser(p, log_fn)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        log_fn(f"접속 중: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await click_more_buttons(page, log_fn)
        html = await page.content()

        projects = parse_portfolio_list(html)

        if not projects:
            log_fn("포트폴리오 목록 없음 → 스크롤 캡처 모드")
            save_dir.mkdir(parents=True, exist_ok=True)

            if filter_text:
                await _capture_filtered(page, save_dir, filter_text, api_key,
                                        base_url, log_fn, progress_fn, stop_event)
            else:
                await _scroll_capture(page, save_dir, log_fn, progress_fn, stop_event)

            await browser.close()
            return

        projects = apply_filter(projects, filter_text, api_key, base_url, log_fn)
        log_fn(f"캡처 대상: {len(projects)}개\n")
        save_dir.mkdir(parents=True, exist_ok=True)
        title_counter = {}

        for idx, proj in enumerate(projects, 1):
            if stop_event.is_set():
                log_fn("중단됨")
                break

            title = (proj.get("seed_title") or f"project_{idx}").strip()
            seed_id = proj.get("seed_id", "")
            folder_name = sanitize(title)

            base = folder_name
            if base in title_counter:
                title_counter[base] += 1
                folder_name = f"{base}_{title_counter[base]:02d}"
            else:
                title_counter[base] = 1

            log_fn(f"[{idx:03d}/{len(projects)}] {title}")

            if seed_id:
                detail_url = f"{base_url}/home/info/{seed_id}"
                try:
                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(500)
                    screenshot_path = save_dir / f"{idx:03d}_{folder_name}.png"
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    size_kb = screenshot_path.stat().st_size // 1024
                    log_fn(f"  캡처 완료 ({size_kb}KB)")
                except Exception as e:
                    log_fn(f"  오류: {e}")
            else:
                log_fn("  seed_id 없음 — 건너뜀")

            progress_fn(idx, len(projects))

        log_fn(f"\n완료! {save_dir}")
        await browser.close()


# ══════════════════════════════════════════════
#  내부 헬퍼
# ══════════════════════════════════════════════

async def _vision_filter_urls(img_urls: list, keyword: str, api_key: str,
                               base_url: str, log_fn) -> list:
    """이미지 URL 목록을 Vision으로 필터링"""
    if not api_key:
        log_fn("AI 분석 키 없음 — 전체 이미지 사용")
        return img_urls

    log_fn(f"이미지 {len(img_urls)}개 AI 분석 중...")
    matched = []
    for i, img_url in enumerate(img_urls, 1):
        ok = fetch_and_check(img_url, keyword, api_key, base_url)
        if ok:
            log_fn(f"  [{i:03d}] ✓ 매칭")
            matched.append(img_url)
        else:
            log_fn(f"  [{i:03d}] ✗ 미매칭")
    log_fn(f"AI 매칭 결과: {len(matched)}/{len(img_urls)}개")
    return matched


async def _capture_filtered(page, save_dir: Path, filter_text: str, api_key: str,
                             base_url: str, log_fn, progress_fn, stop_event):
    """
    텍스트 매칭 → 없으면 이미지 Vision 매칭 → 매칭된 요소 캡처
    """
    # 1. 텍스트 포함 요소 찾기
    text_locs = []
    try:
        loc = page.locator(f"text={filter_text}")
        cnt = await loc.count()
        text_locs = [loc.nth(i) for i in range(cnt)]
    except Exception:
        pass

    log_fn(f"텍스트 매칭 요소: {len(text_locs)}개")

    # 2. 텍스트 매칭 요소 캡처
    saved = 0
    for i, el in enumerate(text_locs, 1):
        if stop_event.is_set():
            return
        try:
            await el.scroll_into_view_if_needed()
            await page.wait_for_timeout(400)
            sp = save_dir / f"{saved+1:03d}_text.png"
            await el.screenshot(path=str(sp))
            log_fn(f"  [{saved+1:03d}] 텍스트 캡처 ({sp.stat().st_size // 1024}KB)")
            saved += 1
        except Exception as e:
            log_fn(f"  텍스트 요소 캡처 오류: {e}")

    # 3. 페이지 내 모든 이미지 Vision 분석
    if api_key:
        log_fn("이미지 Vision 분석 시작...")
        img_elements = await page.locator("img").all()
        log_fn(f"  이미지 {len(img_elements)}개 분석 대상")

        vision_saved = 0
        for i, img_el in enumerate(img_elements):
            if stop_event.is_set():
                return
            try:
                src = await img_el.get_attribute("src") or await img_el.get_attribute("data-src") or ""
                if not src or src.startswith("data:") or not src.startswith("http"):
                    continue

                matched = fetch_and_check(src, filter_text, api_key, base_url)
                if matched:
                    # 이미지 요소보다 부모 카드/섹션 캡처
                    parent = img_el.locator("xpath=ancestor::*[contains(@class,'item') or contains(@class,'card') or contains(@class,'portfolio') or contains(@class,'work')][1]")
                    target = parent if await parent.count() > 0 else img_el

                    await target.scroll_into_view_if_needed()
                    await page.wait_for_timeout(400)
                    sp = save_dir / f"{saved+1:03d}_img.png"
                    await target.screenshot(path=str(sp))
                    log_fn(f"  [{saved+1:03d}] 이미지 Vision 매칭 캡처 ({sp.stat().st_size // 1024}KB)")
                    saved += 1
                    vision_saved += 1

            except Exception as e:
                log_fn(f"  이미지 분석 오류: {e}")

            progress_fn(i + 1, len(img_elements))

        log_fn(f"Vision 매칭 캡처: {vision_saved}개")
    else:
        log_fn("(AI 분석 키 없음 — 이미지 Vision 매칭 생략)")

    if saved == 0:
        log_fn("매칭 항목 없음")
    else:
        log_fn(f"\n완료! 총 {saved}개 캡처 → {save_dir}")


async def _scroll_capture(page, save_dir: Path, log_fn, progress_fn, stop_event):
    """페이지를 스크롤하면서 뷰포트 단위로 캡처, 다음 페이지 이동"""
    page_num = 1
    while True:
        log_fn(f"  페이지 {page_num} 캡처 시작")
        total_height = await page.evaluate("document.body.scrollHeight")
        viewport_h = 900
        y = 0
        shot_idx = 1

        while y < total_height:
            if stop_event.is_set():
                log_fn("중단됨")
                return
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(500)
            sp = save_dir / f"p{page_num:02d}_{shot_idx:03d}.png"
            await page.screenshot(
                path=str(sp),
                clip={"x": 0, "y": y, "width": 1440,
                      "height": min(viewport_h, total_height - y)}
            )
            log_fn(f"  p{page_num}-{shot_idx:03d} ({sp.stat().st_size // 1024}KB)")
            y += viewport_h
            shot_idx += 1

        moved = await click_next_page(page)
        if not moved:
            break
        await page.wait_for_timeout(2000)
        page_num += 1
        log_fn(f"  → 다음 페이지({page_num})로 이동")

    log_fn(f"\n완료! {save_dir}")

"""
다운로드 핵심 로직
"""

import asyncio
import json
import re
import time
import requests
from pathlib import Path

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


async def run_download(url: str, save_dir: Path, log_fn, progress_fn, stop_event):
    from playwright.async_api import async_playwright

    base_url = get_base_url(url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        log_fn(f"접속 중: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await click_more_buttons(page, log_fn)
        html = await page.content()

        projects = parse_portfolio_list(html)

        # ── 포트폴리오 목록 구조 없음 → 현재 페이지 이미지 직접 다운 ──
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

            log_fn(f"이미지 {len(img_urls)}개 발견")
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

        # ── 포트폴리오 목록 구조 있음 → 상세 페이지 순회 ──
        log_fn(f"프로젝트 {len(projects)}개 발견\n")
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
                    await page.goto(detail_url, wait_until="networkidle", timeout=30000)
                    img_urls = extract_og_images(await page.content(), base_url)
                except Exception as e:
                    log_fn(f"  오류: {e}")

            if not img_urls:
                src = proj.get("file_org_src") or proj.get("file_src") or ""
                if src:
                    src = src.replace("\\/", "/")
                    if not src.startswith("http"):
                        src = base_url + src
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

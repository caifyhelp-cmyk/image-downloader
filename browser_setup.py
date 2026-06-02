"""
Playwright 브라우저 관리
- 시스템 Chrome → ms-playwright chromium → 자동 설치 순으로 시도
"""

import os
import sys
import glob
import subprocess
from pathlib import Path

MS_PW = Path.home() / "AppData" / "Local" / "ms-playwright"

# 시스템 Chrome 위치
_CHROME_PATHS = [
    Path(os.environ.get("PROGRAMFILES",       "C:/Program Files"))      / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
]


def system_chrome() -> str:
    for p in _CHROME_PATHS:
        if p.exists():
            return str(p)
    return ""


def find_ms_playwright_chromium() -> str:
    """ms-playwright 폴더에서 chromium 실행파일 탐색"""
    patterns = [
        str(MS_PW / "chromium_headless_shell-*" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"),
        str(MS_PW / "chromium-*" / "chrome-win" / "chrome.exe"),
    ]
    for pat in patterns:
        found = glob.glob(pat)
        if found:
            return found[0]
    return ""


def _chromium_exists() -> bool:
    return bool(system_chrome() or find_ms_playwright_chromium())


def install_chromium(log_fn=None) -> bool:
    """playwright install chromium → ms-playwright에 설치"""
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(MS_PW)}

    try:
        from playwright._impl._driver import compute_driver_executable
        driver_exe, driver_cli = compute_driver_executable()
        cmd = [str(driver_exe), str(driver_cli), "install", "chromium"]
    except Exception:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

    if log_fn:
        log_fn("Chromium 설치 중... (최초 1회, 약 1~2분 소요)")
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace"
        )
        for line in proc.stdout:
            line = line.strip()
            if line and log_fn:
                log_fn(line)
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        if log_fn:
            log_fn(f"설치 오류: {e}")
        return False


def ensure_browser_sync(log_fn=None):
    """
    Worker 스레드에서 호출. 브라우저 없으면 동기 설치.
    asyncio.run() 전에 호출해야 함.
    """
    if _chromium_exists():
        return
    ok = install_chromium(log_fn)
    if not ok and log_fn:
        log_fn("⚠ 브라우저 자동 설치 실패. 관리자 권한으로 재시도해보세요.")

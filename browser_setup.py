"""
Playwright 브라우저 설치 관리
"""

import os
import sys
import glob
import subprocess
import threading
from pathlib import Path

MS_PW = Path.home() / "AppData" / "Local" / "ms-playwright"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(MS_PW)

# 시스템 Chrome 경로들
_CHROME_PATHS = [
    Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
]


def _system_chrome_exists() -> bool:
    return any(p.exists() for p in _CHROME_PATHS)


def _ms_playwright_chromium_exists() -> bool:
    patterns = [
        str(MS_PW / "chromium_headless_shell-*" / "**" / "chrome-headless-shell.exe"),
        str(MS_PW / "chromium-*" / "chrome-win" / "chrome.exe"),
    ]
    return any(glob.glob(p, recursive=True) for p in patterns)


def _chromium_exists() -> bool:
    return _system_chrome_exists() or _ms_playwright_chromium_exists()


def _run_playwright_install(log_fn) -> bool:
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(MS_PW)}
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_exe, driver_cli = compute_driver_executable()
        cmd = [str(driver_exe), str(driver_cli), "install", "chromium"]
    except Exception:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

    log_fn("Chromium 브라우저 설치 중... (최초 1회, 약 1~2분 소요)")
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace"
        )
        for line in proc.stdout:
            line = line.strip()
            if line:
                log_fn(line)
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        log_fn(f"설치 오류: {e}")
        return False


def ensure_browser(log_fn, on_ready, on_fail):
    if _chromium_exists():
        on_ready()
        return

    def _install():
        ok = _run_playwright_install(log_fn)
        if ok and _chromium_exists():
            log_fn("브라우저 설치 완료!")
            on_ready()
        else:
            on_fail("브라우저 설치 실패. 관리자 권한으로 다시 실행해보세요.")

    threading.Thread(target=_install, daemon=True).start()

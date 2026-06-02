"""
Playwright 브라우저 설치 관리
PyInstaller --onefile 환경에서 브라우저를 고정 경로에 설치/확인
"""

import os
import sys
import glob
import subprocess
import threading
from pathlib import Path

# ─────────────────────────────────────────────
# 핵심: 브라우저를 임시폴더(_MEI...) 대신
#        %LOCALAPPDATA%\ms-playwright 에 고정
# ─────────────────────────────────────────────
BROWSERS_PATH = str(Path.home() / "AppData" / "Local" / "ms-playwright")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS_PATH


def _chromium_exists() -> bool:
    """ms-playwright 에 chromium(headless-shell 포함)이 있는지 확인"""
    base = Path(BROWSERS_PATH)
    patterns = [
        str(base / "chromium*" / "chrome-win" / "chrome.exe"),
        str(base / "chromium_headless_shell*" / "**" / "chrome-headless-shell.exe"),
        str(base / "chromium_headless_shell*" / "**" / "chrome.exe"),
    ]
    return any(glob.glob(p, recursive=True) for p in patterns)


def _run_playwright_install(log_fn):
    """playwright install chromium 실행 (frozen/개발 모두 지원)"""
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": BROWSERS_PATH}

    try:
        # playwright 내부 드라이버 실행파일 사용 (frozen exe에서도 작동)
        from playwright._impl._driver import compute_driver_executable
        driver_exe, driver_cli = compute_driver_executable()
        cmd = [str(driver_exe), str(driver_cli), "install", "chromium"]
    except Exception:
        # fallback: python -m playwright
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
    """
    브라우저 있으면 즉시 on_ready().
    없으면 백그라운드 설치 후 on_ready() 또는 on_fail().
    """
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

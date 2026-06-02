"""
자동 업데이트 모듈
앱 시작 시 새 버전 확인 → 자동 다운로드 → 자동 재시작
"""

import os
import sys
import subprocess
import tempfile
import threading
import requests
from pathlib import Path
from packaging.version import Version

from version import VERSION, REPO

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


# ──────────────────────────────────────────────
#  한글 경로 → 8.3 단축경로 (cmd.exe ASCII 호환)
# ──────────────────────────────────────────────

def _short(path) -> str:
    """
    Windows GetShortPathNameW로 8.3 단축경로 반환.
    한글·공백 등 특수문자가 있어도 cmd.exe에서 안전하게 사용 가능.
    실패 시 원본 경로 반환.
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ret = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 512)
        if ret > 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return str(path)


# ──────────────────────────────────────────────
#  메인 업데이트 함수
# ──────────────────────────────────────────────

def check_and_auto_update(log_fn, on_complete):
    """
    백그라운드에서 버전 확인.
    새 버전 있으면 자동 다운로드 후 재시작.
    on_complete(): 업데이트 없거나 실패 시 호출 (앱 정상 시작)
    """
    def _run():
        try:
            log_fn("업데이트 확인 중...")
            res = requests.get(API_URL, timeout=8,
                               headers={"Accept": "application/vnd.github+json"})
            if res.status_code != 200:
                log_fn(f"서버 응답 오류 ({res.status_code}), 앱 시작")
                on_complete()
                return

            data = res.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                on_complete()
                return

            if not Version(latest_tag) > Version(VERSION):
                log_fn(f"최신 버전입니다 (v{VERSION})")
                on_complete()
                return

            # 새 버전 발견
            assets = data.get("assets", [])
            dl_url = next((a["browser_download_url"] for a in assets
                           if a["name"].lower().endswith(".exe")), "")
            if not dl_url:
                log_fn("릴리즈에 exe 파일 없음, 앱 시작")
                on_complete()
                return

            log_fn(f"새 버전 v{latest_tag} 발견 — 자동 업데이트 중...")
            _download_and_restart(dl_url, latest_tag, log_fn, on_complete)

        except Exception as e:
            log_fn(f"업데이트 확인 실패: {e}")
            on_complete()

    threading.Thread(target=_run, daemon=True).start()


def _download_and_restart(dl_url: str, new_ver: str, log_fn, on_complete):
    try:
        res = requests.get(dl_url, timeout=120, stream=True)
        res.raise_for_status()

        total = int(res.headers.get("content-length", 0))
        downloaded = 0

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
        for chunk in res.iter_content(chunk_size=65536):
            tmp.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = int(downloaded / total * 100)
                log_fn(f"  다운로드 {pct}%...")
        tmp.close()

        log_fn("다운로드 완료. 재시작 준비 중...")

        if getattr(sys, "frozen", False):
            current_exe = Path(sys.executable)
            new_exe     = Path(tmp.name)
            batch       = _make_swap_batch(current_exe, new_exe)
            batch_short = _short(batch)

            # DETACHED_PROCESS(0x8) | CREATE_NO_WINDOW(0x8000000)
            # → 부모 종료 후에도 cmd가 독립적으로 실행됨
            subprocess.Popen(
                ["cmd", "/c", batch_short],
                creationflags=0x00000008 | 0x08000000
            )
            log_fn("업데이트 적용 중... (자동 재시작)")
            os._exit(0)
        else:
            # 개발 모드: 실제 교체 없이 경로만 알려줌
            log_fn(f"[개발 모드] 새 exe 위치: {tmp.name}")
            on_complete()

    except Exception as e:
        log_fn(f"업데이트 실패: {e}")
        on_complete()


def _make_swap_batch(current_exe: Path, new_exe: Path) -> Path:
    """
    한글 경로를 8.3 단축경로로 변환 후 배치 작성.
    cmd.exe가 한글을 깨뜨리는 문제 완전 차단.
    """
    # 모든 경로를 ASCII 8.3 단축경로로 변환
    cur = _short(current_exe)
    nw  = _short(new_exe)

    bat = Path(tempfile.gettempdir()) / "imgdl_upd.bat"
    bat_short_parent = _short(bat.parent)
    bat_ascii = bat_short_parent + "\\imgdl_upd.bat"

    content = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        # 1차 시도
        f"move /y \"{nw}\" \"{cur}\"\r\n"
        # 실패 시 2초 더 기다렸다가 재시도
        "if errorlevel 1 (\r\n"
        "  timeout /t 2 /nobreak >nul\r\n"
        f"  move /y \"{nw}\" \"{cur}\"\r\n"
        ")\r\n"
        f"start \"\" \"{cur}\"\r\n"
        "del \"%~f0\"\r\n"
    )

    # ASCII 경로만 포함되므로 ascii 인코딩으로 안전하게 저장
    Path(bat_ascii).write_text(content, encoding="ascii")
    return Path(bat_ascii)

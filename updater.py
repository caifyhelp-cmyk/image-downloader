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
                on_complete()
                return

            data = res.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag or not Version(latest_tag) > Version(VERSION):
                log_fn(f"최신 버전입니다 (v{VERSION})")
                on_complete()
                return

            # 새 버전 발견 → 자동 다운로드
            assets = data.get("assets", [])
            dl_url = next((a["browser_download_url"] for a in assets
                           if a["name"].endswith(".exe")), "")
            if not dl_url:
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

        log_fn("다운로드 완료. 재시작 중...")

        if getattr(sys, "frozen", False):
            # exe로 실행 중인 경우 → 배치 스크립트로 파일 교체 후 재시작
            current_exe = Path(sys.executable)
            new_exe = Path(tmp.name)
            batch = _make_swap_batch(current_exe, new_exe)
            subprocess.Popen(["cmd", "/c", str(batch)],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            os._exit(0)
        else:
            # 개발 모드 (python app.py)
            log_fn(f"[개발 모드] 새 exe: {tmp.name}")
            on_complete()

    except Exception as e:
        log_fn(f"업데이트 실패: {e}")
        on_complete()


def _make_swap_batch(current_exe: Path, new_exe: Path) -> Path:
    """
    현재 프로세스 종료 후 파일 교체 + 재시작하는 배치 스크립트 생성
    """
    bat = Path(tempfile.gettempdir()) / "img_dl_update.bat"
    bat.write_text(
        f"@echo off\n"
        f"timeout /t 2 /nobreak >nul\n"
        f"move /y \"{new_exe}\" \"{current_exe}\"\n"
        f"start \"\" \"{current_exe}\"\n"
        f"del \"%~f0\"\n",
        encoding="utf-8"
    )
    return bat

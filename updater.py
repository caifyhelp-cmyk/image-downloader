"""
자동 업데이트 모듈
GitHub Releases API로 최신 버전 확인 → 다운로드 → 재시작
"""

import os
import sys
import threading
import subprocess
import tempfile
import requests
from pathlib import Path
from packaging.version import Version

from version import VERSION, REPO

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def check_update(callback):
    """백그라운드에서 최신 버전 확인 후 callback(latest_ver, download_url) 호출"""
    def _check():
        try:
            res = requests.get(API_URL, timeout=8,
                               headers={"Accept": "application/vnd.github+json"})
            if res.status_code != 200:
                return
            data = res.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if not latest_tag:
                return
            if Version(latest_tag) > Version(VERSION):
                # exe asset URL 찾기
                assets = data.get("assets", [])
                dl_url = ""
                for asset in assets:
                    name = asset.get("name", "")
                    if name.endswith(".exe"):
                        dl_url = asset.get("browser_download_url", "")
                        break
                if dl_url:
                    callback(latest_tag, dl_url)
        except Exception:
            pass

    threading.Thread(target=_check, daemon=True).start()


def do_update(download_url: str, log_fn, done_fn):
    """새 exe 다운로드 후 현재 exe 교체 + 재시작"""
    def _update():
        try:
            log_fn("업데이트 다운로드 중...")
            res = requests.get(download_url, timeout=120, stream=True)
            res.raise_for_status()

            total = int(res.headers.get("content-length", 0))
            downloaded = 0

            # 임시 파일에 저장
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
            for chunk in res.iter_content(chunk_size=65536):
                tmp.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded / total * 100)
                    log_fn(f"  다운로드 {pct}%...")
            tmp.close()

            log_fn("업데이트 적용 중...")

            current_exe = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)
            if getattr(sys, 'frozen', False):
                current_exe = Path(sys.executable)
                backup = current_exe.with_suffix(".bak.exe")
                if backup.exists():
                    backup.unlink()
                current_exe.rename(backup)
                Path(tmp.name).rename(current_exe)

                # 재시작
                subprocess.Popen([str(current_exe)])
                os._exit(0)
            else:
                log_fn(f"새 버전 다운로드 완료: {tmp.name}")
                log_fn("(개발 모드: 수동으로 교체해주세요)")
                done_fn()

        except Exception as e:
            log_fn(f"업데이트 실패: {e}")
            done_fn()

    threading.Thread(target=_update, daemon=True).start()

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


def _fetch_latest() -> tuple:
    """(latest_ver, dl_url) 반환. 최신이거나 실패 시 ("", "")"""
    res = requests.get(API_URL, timeout=8,
                       headers={"Accept": "application/vnd.github+json"})
    if res.status_code != 200:
        return "", ""
    data = res.json()
    latest_tag = data.get("tag_name", "").lstrip("v")
    if not latest_tag or not Version(latest_tag) > Version(VERSION):
        return latest_tag, ""
    assets = data.get("assets", [])
    dl_url = next((a["browser_download_url"] for a in assets
                   if a["name"].lower().endswith(".exe")), "")
    return latest_tag, dl_url


def check_update_once(callback):
    """
    수동 업데이트 확인용.
    callback(status_msg: str, dl_url: str) — dl_url 비어있으면 최신 버전
    """
    def _run():
        try:
            latest, dl_url = _fetch_latest()
            if not latest:
                callback("확인 실패", "")
            elif not dl_url:
                callback(f"최신 버전입니다 (v{VERSION})", "")
            else:
                callback(f"새 버전 v{latest} 있음", dl_url)
        except Exception as e:
            callback(f"오류: {e}", "")
    threading.Thread(target=_run, daemon=True).start()


def download_and_apply(dl_url: str, log_fn, fail_fn):
    """수동 업데이트 다운로드 + 교체 + 재시작"""
    def _run():
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
                    log_fn(f"다운로드 {pct}%...")
            tmp.close()
            log_fn("완료. 재시작 중...")

            if getattr(sys, "frozen", False):
                current_exe = Path(sys.executable)
                ps1 = _make_swap_script(current_exe, Path(tmp.name))
                subprocess.Popen(
                    ["powershell", "-ExecutionPolicy", "Bypass",
                     "-WindowStyle", "Hidden", "-File", _short(ps1)],
                    creationflags=0x00000008 | 0x08000000
                )
                os._exit(0)
            else:
                log_fn(f"[개발 모드] 새 exe: {tmp.name}")
        except Exception as e:
            fail_fn(f"실패: {e}")
    threading.Thread(target=_run, daemon=True).start()


# ──────────────────────────────────────────────
#  한글 경로 → 8.3 단축경로 (하위 호환용)
# ──────────────────────────────────────────────

def _short(path) -> str:
    """
    Windows GetShortPathNameW로 8.3 단축경로 반환.
    실패 시 원본 경로 반환 (PowerShell 경로로 사용).
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
            latest_tag, dl_url = _fetch_latest()

            if not latest_tag:
                log_fn(f"최신 버전입니다 (v{VERSION})")
                on_complete()
                return

            if not dl_url:
                log_fn(f"최신 버전입니다 (v{VERSION})")
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
            ps1 = _make_swap_script(current_exe, new_exe)
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass",
                 "-WindowStyle", "Hidden", "-File", _short(ps1)],
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


def _make_swap_script(current_exe: Path, new_exe: Path) -> Path:
    """
    PowerShell 스크립트로 exe 교체.
    - PowerShell은 유니코드 경로 완벽 지원 → 한글 경로 문제 없음
    - BOM(utf-8-sig) 으로 저장해야 PowerShell이 한글을 올바르게 읽음
    """
    ps1 = Path(tempfile.gettempdir()) / "imgdl_upd.ps1"

    # PowerShell 문자열에서 작은따옴표 이스케이프
    src = str(new_exe).replace("'", "''")
    dst = str(current_exe).replace("'", "''")

    content = (
        "Start-Sleep -Seconds 3\n"
        f"$src = '{src}'\n"
        f"$dst = '{dst}'\n"
        # 파일 교체 (최대 3회 재시도)
        "for ($i = 0; $i -lt 3; $i++) {\n"
        "    try {\n"
        "        Move-Item -Force -Path $src -Destination $dst -ErrorAction Stop\n"
        "        break\n"
        "    } catch {\n"
        "        Start-Sleep -Seconds 2\n"
        "    }\n"
        "}\n"
        # 파일시스템 안정화 대기
        "Start-Sleep -Seconds 1\n"
        # Zone.Identifier 제거 (인터넷 다운로드 차단 해제)
        "Unblock-File -Path $dst -ErrorAction SilentlyContinue\n"
        # 새 exe 실행
        "Start-Process -FilePath $dst\n"
        "Remove-Item -Force -Path $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue\n"
    )

    # BOM 포함 UTF-8 — PowerShell 기본 인코딩이 이걸 요구
    ps1.write_text(content, encoding="utf-8-sig")
    return ps1


def _make_swap_batch(current_exe: Path, new_exe: Path) -> Path:
    """하위 호환용 — 내부적으로 PowerShell 스크립트 생성"""
    return _make_swap_script(current_exe, new_exe)

"""
포트폴리오 이미지 자동 다운로더
GitHub: caifyhelp-cmyk/image-downloader
"""

# ── 브라우저 경로 고정 (PyInstaller 임시폴더 문제 해결) ──
import browser_setup  # noqa: F401 — 임포트 자체로 env 세팅됨

import asyncio
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

from version import VERSION
from downloader import run_download, run_screenshot
from updater import check_and_auto_update

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

CONFIG_PATH = Path.home() / ".image_downloader_config.json"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


# ══════════════════════════════════════════════
#  색상
# ══════════════════════════════════════════════
BG      = "#1a1a2e"
PANEL   = "#16213e"
CARD    = "#0f3460"
ACCENT  = "#7c6af7"
ACCENT2 = "#a78bfa"
FG      = "#e2e8f0"
FG2     = "#94a3b8"
RED     = "#f87171"
ENTRY   = "#1e293b"
YELLOW  = "#fbbf24"
GREEN   = "#4ade80"


# ══════════════════════════════════════════════
#  업데이트 스플래시
# ══════════════════════════════════════════════

class SplashScreen(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("이미지 다운로더")
        self.geometry("380x140")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 380) // 2
        y = (self.winfo_screenheight() - 140) // 2
        self.geometry(f"380x140+{x}+{y}")
        self.overrideredirect(True)

        tk.Label(self, text="포트폴리오 이미지 다운로더",
                 bg=BG, fg=ACCENT2, font=("Malgun Gothic", 13, "bold")).pack(pady=(22, 6))
        tk.Label(self, text=f"v{VERSION}", bg=BG, fg=FG2,
                 font=("Malgun Gothic", 9)).pack()
        self.status = tk.Label(self, text="업데이트 확인 중...",
                               bg=BG, fg=YELLOW, font=("Malgun Gothic", 9))
        self.status.pack(pady=(10, 0))
        self.bar = ttk.Progressbar(self, mode="indeterminate", length=320)
        self.bar.pack(pady=8)
        self.bar.start(12)

    def set_status(self, msg: str):
        self.after(0, lambda: self.status.config(text=msg))

    def close_and_launch(self):
        self.after(0, self._do_launch)

    def _do_launch(self):
        self.destroy()
        app = App()
        app.mainloop()


# ══════════════════════════════════════════════
#  메인 GUI
# ══════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"이미지 다운로더  v{VERSION}")
        self.geometry("780x720")
        self.minsize(620, 600)
        self.configure(bg=BG)
        self.stop_event = threading.Event()
        self._cfg = load_config()
        self._build_ui()
        self._check_playwright()

    # ── UI 구성 ────────────────────────────────
    def _build_ui(self):
        # 헤더
        hdr = tk.Frame(self, bg=CARD, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="포트폴리오 이미지 다운로더",
                 bg=CARD, fg=ACCENT2, font=("Malgun Gothic", 17, "bold")).pack(side="left", padx=20)
        tk.Label(hdr, text=f"v{VERSION}",
                 bg=CARD, fg=FG2, font=("Malgun Gothic", 10)).pack(side="left", padx=4)

        # 업데이트 버튼 (헤더 우측)
        self._update_url = ""
        self._upd_btn = tk.Button(
            hdr, text=" 업데이트 확인 ",
            bg=CARD, fg=FG2, relief="flat",
            font=("Malgun Gothic", 9), padx=10, pady=4,
            command=self._check_update_manual, cursor="hand2")
        self._upd_btn.pack(side="right", padx=12)
        self._upd_label = tk.Label(hdr, text="", bg=CARD, fg=FG2,
                                   font=("Malgun Gothic", 9))
        self._upd_label.pack(side="right", padx=4)

        # 본문
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Row 0: URL ──
        self._row(body, "URL", 0)
        url_frame = tk.Frame(body, bg=BG)
        url_frame.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=6)
        self.url_var = tk.StringVar(
            value=self._cfg.get("last_url",
                  "https://www.charmspace.co.kr/home/sub/official_project"))
        self._url_entry = tk.Entry(url_frame, textvariable=self.url_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Consolas", 10), bd=6)
        self._url_entry.pack(side="left", fill="x", expand=True)
        tk.Button(url_frame, text=" 붙여넣기 ", bg=CARD, fg=FG2, relief="flat",
                  font=("Malgun Gothic", 9), pady=4,
                  command=self._paste_url, cursor="hand2"
                  ).pack(side="left", padx=(6, 0))

        # ── Row 1: 저장 폴더 ──
        self._row(body, "저장 폴더", 1)
        dir_frame = tk.Frame(body, bg=BG)
        dir_frame.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=6)
        self.dir_var = tk.StringVar(
            value=self._cfg.get("last_dir",
                  str(Path.home() / "Desktop" / "downloaded_images")))
        tk.Entry(dir_frame, textvariable=self.dir_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Consolas", 10), bd=6
                 ).pack(side="left", fill="x", expand=True)
        tk.Button(dir_frame, text=" 찾기 ", bg=CARD, fg=FG2, relief="flat",
                  font=("Malgun Gothic", 9), pady=4,
                  command=self._browse, cursor="hand2"
                  ).pack(side="left", padx=(6, 0))

        # ── Row 2: 필터 텍스트 ──
        self._row(body, "필터 텍스트", 2)
        filter_frame = tk.Frame(body, bg=BG)
        filter_frame.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=6)
        self.filter_var = tk.StringVar(value=self._cfg.get("last_filter", ""))
        tk.Entry(filter_frame, textvariable=self.filter_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Malgun Gothic", 10), bd=6
                 ).pack(side="left", fill="x", expand=True)
        tk.Label(filter_frame, text=" 빈칸이면 전체",
                 bg=BG, fg=FG2, font=("Malgun Gothic", 8)
                 ).pack(side="left", padx=(8, 0))

        # ── Row 3: AI 분석 키 ──
        self._row(body, "AI 분석 키", 3)
        key_frame = tk.Frame(body, bg=BG)
        key_frame.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=6)
        self.api_key_var = tk.StringVar(value=self._cfg.get("api_key", ""))
        self._key_entry = tk.Entry(key_frame, textvariable=self.api_key_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Consolas", 9), bd=6, show="•")
        self._key_entry.pack(side="left", fill="x", expand=True)
        tk.Button(key_frame, text=" 저장 ", bg=CARD, fg=FG2, relief="flat",
                  font=("Malgun Gothic", 9), pady=4,
                  command=self._save_api_key, cursor="hand2"
                  ).pack(side="left", padx=(6, 0))
        self._key_status = tk.Label(key_frame, text="", bg=BG, fg=GREEN,
                                    font=("Malgun Gothic", 8))
        self._key_status.pack(side="left", padx=(6, 0))
        # 저장된 키 있으면 상태 표시
        if self.api_key_var.get():
            self._key_status.config(text="✓ 저장됨", fg=GREEN)

        # ── Row 3 설명 ──
        tk.Label(body,
                 text="  Claude API 키 입력 시 이미지에 텍스트가 없어도 AI가 이미지 내용을 분석해 매칭합니다.",
                 bg=BG, fg=FG2, font=("Malgun Gothic", 8), anchor="w"
                 ).grid(row=3, column=0, columnspan=2, sticky="w",
                        padx=(0, 0), pady=(0, 0))
        # (설명 라벨은 row 3 아래에 별도 row로)
        tk.Label(body,
                 text="  ↑  Claude API 키: 이미지에 텍스트가 없어도 이미지 내용 AI 분석 후 매칭",
                 bg=BG, fg=FG2, font=("Malgun Gothic", 8), anchor="w"
                 ).grid(row=4, column=0, columnspan=2, sticky="w", padx=(4, 0))

        # ── Row 5: 스크린샷 모드 ──
        mode_frame = tk.Frame(body, bg=BG)
        mode_frame.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 6))
        self.screenshot_mode = tk.BooleanVar(value=False)
        tk.Checkbutton(mode_frame,
                       text="스크린샷 캡처 모드  (이미지 다운 대신 페이지를 PNG로 캡처)",
                       variable=self.screenshot_mode,
                       bg=BG, fg=FG2, selectcolor=CARD, activebackground=BG,
                       activeforeground=ACCENT2,
                       font=("Malgun Gothic", 9), cursor="hand2"
                       ).pack(side="left")

        body.columnconfigure(1, weight=1)

        # ── Row 6: 버튼 ──
        btn_row = tk.Frame(body, bg=BG)
        btn_row.grid(row=6, column=0, columnspan=2, pady=(4, 8))

        self.btn_start = tk.Button(
            btn_row, text="▶  시작",
            bg=ACCENT, fg="white", relief="flat",
            font=("Malgun Gothic", 11, "bold"), padx=22, pady=9,
            command=self._start, cursor="hand2")
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = tk.Button(
            btn_row, text="■  중단",
            bg=RED, fg="white", relief="flat",
            font=("Malgun Gothic", 11), padx=16, pady=9,
            command=self._stop, state="disabled", cursor="hand2")
        self.btn_stop.pack(side="left", padx=5)

        tk.Button(btn_row, text="폴더 열기", bg=CARD, fg=FG2, relief="flat",
                  font=("Malgun Gothic", 10), padx=14, pady=9,
                  command=self._open_dir, cursor="hand2"
                  ).pack(side="left", padx=5)

        # ── Row 7: 진행바 ──
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        self.status_var = tk.StringVar(value="대기 중")
        tk.Label(body, textvariable=self.status_var, bg=BG, fg=FG2,
                 font=("Malgun Gothic", 9)
                 ).grid(row=8, column=0, columnspan=2, sticky="w")

        # ── Row 9: 로그 ──
        self.log_box = scrolledtext.ScrolledText(
            body, bg=ENTRY, fg=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", bd=0, wrap="word", height=12)
        self.log_box.grid(row=9, column=0, columnspan=2,
                          sticky="nsew", pady=(10, 0))
        self.log_box.config(state="disabled")
        body.rowconfigure(9, weight=1)

        # 푸터
        ft = tk.Frame(self, bg=PANEL, pady=6)
        ft.pack(fill="x", side="bottom")
        tk.Label(ft, text="github.com/caifyhelp-cmyk/image-downloader",
                 bg=PANEL, fg=FG2, font=("Malgun Gothic", 8)).pack(side="left", padx=16)
        tk.Label(ft, text="필터 텍스트 + AI 이미지 분석 지원",
                 bg=PANEL, fg=FG2, font=("Malgun Gothic", 8)).pack(side="right", padx=16)

        # IME 비활성화 (URL 입력란)
        self.after(300, lambda: self._disable_ime(self._url_entry))

    def _disable_ime(self, widget):
        try:
            import ctypes
            hwnd = widget.winfo_id()
            ctypes.windll.imm32.ImmAssociateContextEx(hwnd, None, 0)
        except Exception:
            pass

    def _row(self, parent, label, row):
        tk.Label(parent, text=label, bg=BG, fg=FG2,
                 font=("Malgun Gothic", 10), anchor="e", width=9
                 ).grid(row=row, column=0, sticky="ne", pady=8)

    # ── 이벤트 ────────────────────────────────
    # ── 수동 업데이트 ─────────────────────────
    def _check_update_manual(self):
        self._upd_btn.config(state="disabled", text=" 확인 중... ")
        self._upd_label.config(text="", fg=FG2)

        from updater import check_update_once

        def _done(status: str, dl_url: str):
            def _ui():
                if dl_url:
                    # 새 버전 있음
                    self._update_url = dl_url
                    self._upd_label.config(text=status, fg=YELLOW)
                    self._upd_btn.config(
                        state="normal", text=" ↓ 지금 업데이트 ",
                        bg=YELLOW, fg="#1a1a2e",
                        font=("Malgun Gothic", 9, "bold"),
                        command=self._do_update)
                else:
                    self._upd_label.config(text=status, fg=FG2)
                    self._upd_btn.config(state="normal", text=" 업데이트 확인 ",
                                         bg=CARD, fg=FG2,
                                         font=("Malgun Gothic", 9),
                                         command=self._check_update_manual)
            self.after(0, _ui)

        check_update_once(callback=_done)

    def _do_update(self):
        if not self._update_url:
            return
        self._upd_btn.config(state="disabled", text=" 업데이트 중... ")
        self._upd_label.config(text="", fg=FG2)

        from updater import download_and_apply

        def _log(msg):
            self._upd_label.config(text=msg, fg=YELLOW)
            self.after(0, lambda: None)  # UI 갱신 트리거

        def _fail(msg):
            def _ui():
                self._upd_label.config(text=msg, fg=RED)
                self._upd_btn.config(state="normal", text=" ↓ 지금 업데이트 ",
                                     command=self._do_update)
            self.after(0, _ui)

        download_and_apply(self._update_url, _log, _fail)

    def _paste_url(self):
        try:
            text = self.clipboard_get().strip()
            if text:
                self.url_var.set(text)
        except Exception:
            pass

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        self._cfg["api_key"] = key
        save_config(self._cfg)
        if key:
            self._key_status.config(text="✓ 저장됨", fg=GREEN)
        else:
            self._key_status.config(text="삭제됨", fg=FG2)

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def _open_dir(self):
        d = self.dir_var.get()
        if os.path.exists(d):
            os.startfile(d)
        else:
            self.log(f"폴더 없음: {d}")

    def log(self, msg: str):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def set_progress(self, cur, total):
        def _do():
            pct = int(cur / total * 100) if total else 0
            self.progress["value"] = pct
            self.status_var.set(f"{cur} / {total}  ({pct}%)")
        self.after(0, _do)

    def _start(self):
        if not PLAYWRIGHT_OK:
            self.log("playwright 패키지 없음: pip install playwright")
            return
        from browser_setup import _chromium_exists
        if not _chromium_exists():
            self.log("브라우저 설치 중입니다. 잠시 후 다시 시도해주세요...")
            return
        url = self.url_var.get().strip()
        if not url.startswith("http"):
            self.log("올바른 URL을 입력하세요.")
            return

        save_dir = Path(self.dir_var.get())
        filter_text = self.filter_var.get().strip()
        api_key = self.api_key_var.get().strip()
        is_screenshot = self.screenshot_mode.get()

        # 설정 저장
        self._cfg.update({"last_url": url, "last_dir": str(save_dir),
                          "last_filter": filter_text})
        save_config(self._cfg)

        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress["value"] = 0
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

        mode_label = "스크린샷 캡처" if is_screenshot else "이미지 다운로드"
        self.log(f"모드: {mode_label}")
        self.log(f"URL: {url}")
        if filter_text:
            self.log(f"필터: '{filter_text}'")
            if api_key:
                self.log("AI 이미지 분석: 활성화 (텍스트 미매칭 항목도 이미지 분석)")
            else:
                self.log("AI 이미지 분석: 비활성 (텍스트 매칭만 사용)")
        self.log(f"저장: {save_dir}\n")

        def worker():
            try:
                if is_screenshot:
                    asyncio.run(run_screenshot(
                        url, save_dir, self.log, self.set_progress,
                        self.stop_event, filter_text, api_key))
                else:
                    asyncio.run(run_download(
                        url, save_dir, self.log, self.set_progress,
                        self.stop_event, filter_text, api_key))
            except Exception as e:
                self.log(f"\n오류: {e}")
            finally:
                self.after(0, self._done)

        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        self.stop_event.set()
        self.log("중단 요청...")

    def _done(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_var.set("완료")

    def _check_playwright(self):
        if not PLAYWRIGHT_OK:
            self.log("⚠ playwright 패키지 없음 — 개발 환경에서 실행:")
            self.log("  pip install playwright\n")
            return

        # 브라우저 없으면 자동 설치
        from browser_setup import ensure_browser
        ensure_browser(
            log_fn=self.log,
            on_ready=lambda: None,
            on_fail=lambda msg: self.log(f"⚠ {msg}")
        )


# ══════════════════════════════════════════════
#  진입점
# ══════════════════════════════════════════════

if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    splash = SplashScreen()
    check_and_auto_update(
        log_fn=splash.set_status,
        on_complete=splash.close_and_launch
    )
    splash.mainloop()

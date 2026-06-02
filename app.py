"""
포트폴리오 이미지 자동 다운로더
GitHub: caifyhelp-cmyk/image-downloader
"""

import asyncio
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

from version import VERSION
from downloader import run_download
from updater import check_and_auto_update

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False


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


# ══════════════════════════════════════════════
#  업데이트 스플래시 (앱 시작 시 표시)
# ══════════════════════════════════════════════

class SplashScreen(tk.Tk):
    """앱 시작 시 업데이트 확인 중 표시하는 작은 창"""

    def __init__(self):
        super().__init__()
        self.title("이미지 다운로더")
        self.geometry("380x140")
        self.resizable(False, False)
        self.configure(bg=BG)
        # 화면 중앙
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 380) // 2
        y = (self.winfo_screenheight() - 140) // 2
        self.geometry(f"380x140+{x}+{y}")
        self.overrideredirect(True)   # 타이틀바 제거

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
        """스플래시 닫고 메인 앱 열기"""
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
        self.geometry("760x620")
        self.minsize(600, 500)
        self.configure(bg=BG)
        self.stop_event = threading.Event()
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

        # 본문
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # URL
        self._row(body, "URL", 0)
        self.url_var = tk.StringVar(
            value="https://www.charmspace.co.kr/home/sub/official_project")
        tk.Entry(body, textvariable=self.url_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Consolas", 10), bd=6
                 ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=6)

        # 저장 경로
        self._row(body, "저장 폴더", 1)
        self.dir_var = tk.StringVar(
            value=str(Path.home() / "Desktop" / "downloaded_images"))
        dir_frame = tk.Frame(body, bg=BG)
        dir_frame.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=6)
        tk.Entry(dir_frame, textvariable=self.dir_var,
                 bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Consolas", 10), bd=6
                 ).pack(side="left", fill="x", expand=True)
        tk.Button(dir_frame, text=" 찾기 ", bg=CARD, fg=FG2, relief="flat",
                  font=("Malgun Gothic", 9), pady=4,
                  command=self._browse, cursor="hand2"
                  ).pack(side="left", padx=(6, 0))

        body.columnconfigure(1, weight=1)

        # 버튼
        btn_row = tk.Frame(body, bg=BG)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(12, 8))

        self.btn_start = tk.Button(
            btn_row, text="▶  다운로드 시작",
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

        # 진행바
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        self.status_var = tk.StringVar(value="대기 중")
        tk.Label(body, textvariable=self.status_var, bg=BG, fg=FG2,
                 font=("Malgun Gothic", 9)
                 ).grid(row=4, column=0, columnspan=2, sticky="w")

        # 로그
        self.log_box = scrolledtext.ScrolledText(
            body, bg=ENTRY, fg=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", bd=0, wrap="word", height=16)
        self.log_box.grid(row=5, column=0, columnspan=2,
                          sticky="nsew", pady=(10, 0))
        self.log_box.config(state="disabled")
        body.rowconfigure(5, weight=1)

        # 푸터
        ft = tk.Frame(self, bg=PANEL, pady=6)
        ft.pack(fill="x", side="bottom")
        tk.Label(ft, text="github.com/caifyhelp-cmyk/image-downloader",
                 bg=PANEL, fg=FG2, font=("Malgun Gothic", 8)).pack(side="left", padx=16)
        tk.Label(ft, text="URL만 바꾸면 다른 사이트도 지원",
                 bg=PANEL, fg=FG2, font=("Malgun Gothic", 8)).pack(side="right", padx=16)

    def _row(self, parent, label, row):
        tk.Label(parent, text=label, bg=BG, fg=FG2,
                 font=("Malgun Gothic", 10), anchor="e", width=8
                 ).grid(row=row, column=0, sticky="e", pady=6)

    # ── 이벤트 ────────────────────────────────
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
            self.log("playwright 설치 필요: pip install playwright && python -m playwright install chromium")
            return
        url = self.url_var.get().strip()
        if not url.startswith("http"):
            self.log("올바른 URL을 입력하세요.")
            return
        save_dir = Path(self.dir_var.get())
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress["value"] = 0
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self.log(f"시작: {url}")
        self.log(f"저장: {save_dir}\n")

        def worker():
            try:
                asyncio.run(run_download(
                    url, save_dir, self.log, self.set_progress, self.stop_event))
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
            self.log("⚠ playwright 미설치 — 터미널에서 실행:")
            self.log("  pip install playwright")
            self.log("  python -m playwright install chromium\n")


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

    # 1. 스플래시 띄우기
    splash = SplashScreen()

    # 2. 백그라운드에서 업데이트 확인
    #    - 업데이트 있음 → 자동 다운로드 → 자동 재시작 (앱 안 열림)
    #    - 업데이트 없음 → 스플래시 닫고 메인 앱 열기
    check_and_auto_update(
        log_fn=splash.set_status,
        on_complete=splash.close_and_launch
    )

    splash.mainloop()

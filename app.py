"""
Dashboard lokal + pengunduh video YouTube.

Jalankan:  .venv\\Scripts\\python.exe app.py   (atau klik dua kali "Buka Dashboard.bat")
Lalu buka: http://localhost:8765

- Menyajikan dashboard dari folder docs/.
- Kalau file app.local.json berisi {"data_url": "https://<username>.github.io/<repo>/videos.json"},
  daftar video diambil dari GitHub Pages (hasil bot di cloud). Kalau tidak, dari docs/videos.json.
- /api/download?id=<ID video YouTube> mengunduh video dengan yt-dlp lalu mengirimkannya ke browser.
  Hanya bisa diakses dari PC ini sendiri (127.0.0.1).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
CONFIG = ROOT / "app.local.json"
PORT = 8765
YT_ID_RE = re.compile(r"^[\w-]{11}$")

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # tanpa ffmpeg: hanya format MP4 tunggal (maks. 360p/720p)
    FFMPEG = None


def data_url() -> str | None:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8-sig")).get("data_url")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", s)[:60] or "video"


def download_youtube(video_id: str) -> tuple[Path, str]:
    tmp = Path(tempfile.mkdtemp(prefix="ytdl-"))
    opts = {
        "outtmpl": str(tmp / "%(id)s.%(ext)s"),
        "format": ("bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]/b" if FFMPEG
                   else "b[ext=mp4]/b"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
    files = [f for f in tmp.iterdir() if f.suffix in (".mp4", ".webm", ".mkv")]
    if not files:
        raise RuntimeError("File hasil unduhan tidak ditemukan.")
    f = max(files, key=lambda p: p.stat().st_size)
    name = f"{safe_name(info.get('channel') or 'youtube')}_{safe_name(info.get('title') or video_id)}{f.suffix}"
    return f, name


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DOCS), **kw)

    def log_message(self, fmt, *args):  # lebih ringkas di terminal
        if "/api/" in (args[0] if args else ""):
            print("[app]", fmt % args)

    def send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/ping":
            return self.send_json(200, {"ok": True, "ffmpeg": bool(FFMPEG)})
        if u.path == "/api/download":
            return self.handle_download(parse_qs(u.query).get("id", [""])[0])
        if u.path == "/videos.json" and data_url():
            try:
                with urllib.request.urlopen(data_url() + "?t=" + str(id(self)), timeout=30) as r:
                    body = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:
                print(f"[app] Gagal mengambil data dari {data_url()}: {e}. Memakai docs/videos.json.")
        return super().do_GET()

    def handle_download(self, video_id: str) -> None:
        if not YT_ID_RE.match(video_id):
            return self.send_json(400, {"error": "ID video tidak valid."})
        print(f"[app] Mengunduh YouTube {video_id} ...")
        try:
            path, name = download_youtube(video_id)
        except Exception as e:
            print(f"[app] Gagal: {e}")
            return self.send_json(500, {"error": str(e)[-300:]})
        try:
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
            self.end_headers()
            with path.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)
            print(f"[app] Terkirim: {name} ({size / 1024 / 1024:.1f} MB)")
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard: http://localhost:{PORT}  (tutup jendela ini untuk berhenti)")
    print("Sumber data:", data_url() or "docs/videos.json (lokal)")
    if not FFMPEG:
        print("Catatan: ffmpeg tidak ada, video YouTube diunduh dalam kualitas terbatas.")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(f"http://localhost:{PORT}")
        except Exception:
            pass
    server.serve_forever()


if __name__ == "__main__":
    main()

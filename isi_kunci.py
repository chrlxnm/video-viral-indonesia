"""Menyimpan kunci YouTube Data API ke secrets.local.json, lalu langsung menjalankan bot."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

print("\nTempel kunci YouTube Data API (klik kanan atau Ctrl+V), lalu tekan Enter.")
key = input("YouTube API key: ").strip()
if not key:
    sys.exit("Kunci kosong, dibatalkan.")

# File ditulis ulang: hanya berisi kunci YouTube (cookies X lama ikut terhapus).
(ROOT / "secrets.local.json").write_text(json.dumps({"youtube_api_key": key}), encoding="utf-8")
print("Tersimpan. Menjalankan bot...\n")
code = subprocess.call([sys.executable, str(ROOT / "src" / "collect.py")], cwd=ROOT)
print("\nSelesai." if code == 0 else f"\nBot berhenti dengan kode {code}.")

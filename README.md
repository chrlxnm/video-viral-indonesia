# Video Viral Politik Indonesia

Bot gratis ini berjalan otomatis di cloud lewat GitHub Actions, setiap 3 jam. Tugasnya mencari **video politik Indonesia yang sedang viral**, lalu **membuang potongan tayangan TV dan media berita**. Video yang tidak bertopik politik tidak disimpan.

Dashboard memuat data terbaru otomatis setiap 5 menit. Ada juga tombol **🔄 Refresh** untuk memuat ulang kapan saja.

Pencarian YouTube bawaan: kata kunci `politik`, `prabowo`, `jokowi`, `dpr`, `partai` ditambah kategori Berita & Politik, People & Blogs, dan Hiburan. Setiap putaran memakai sekitar 800 unit kuota. Video dianggap politik kalau judul atau deskripsinya menyebut tokoh, lembaga, atau istilah politik.

| Sumber | Cara mencari | Patokan viral | Tombol di dashboard |
|---|---|---|---|
| **YouTube** (termasuk Shorts) | API resmi YouTube (gratis), dengan dua cara: (1) **pencarian jenis**: "cctv", "detik-detik", "terekam kamera", "rekaman warga", "video amatir"; (2) **pencarian umum** tanpa kata kunci, yaitu video Indonesia yang paling banyak ditonton di kategori People & Blogs, Berita, Hiburan, Otomotif, dan Hewan. Hanya video pendek/Shorts **≤ 3 menit** yang diunggah **hari ini atau kemarin** (WIB) | **≥ 50.000 tayangan** | **⬇ Download** (lewat `Buka Dashboard.bat` di PC) / Salin link |
| **X/Twitter** (link yang dibagikan di Reddit r/indonesia) | Feed RSS Reddit, lalu endpoint embed publik X | **≥ 10.000 like** | **⬇ Download** MP4 langsung |

Penyaringan TV/media dilakukan berdasarkan nama channel atau akun (Kompas TV, CNN Indonesia, tvOne, dan sebagainya, termasuk nama yang mengandung "TV", "News", atau "Berita") dan teks seperti "Saksikan selengkapnya di…". Video yang dibuang tetap bisa dilihat di tab **Dibuang**.

> TikTok, Instagram, dan Facebook tidak punya pencarian gratis, sedangkan pencarian X gratis sudah ditutup. Karena itu, sumbernya hanya YouTube dan Reddit.

---

## Setup (sekali saja, sekitar 15 menit)

### 1. Buat repo di GitHub
1. Buat repo baru di https://github.com/new, misalnya `video-viral-indonesia`. Pilih **Public** supaya GitHub Pages gratis.
2. Unggah semua isi folder ini, **kecuali** `.venv` dan `secrets.local.json`.

### 2. Buat kunci YouTube Data API (gratis)
1. Buka https://console.cloud.google.com, lalu login dengan akun Google.
2. Di bagian atas, klik pilihan proyek, lalu **New Project**. Beri nama `video-viral`, lalu klik **Create**.
3. Buka menu **APIs & Services** → **Library**, cari **YouTube Data API v3**, lalu klik **Enable**.
4. Buka **APIs & Services** → **Credentials** → **Create credentials** → **API key**. Salin kunci yang muncul.
5. *(Disarankan)* Klik **Edit API key** → **API restrictions** → **Restrict key**, pilih **YouTube Data API v3**, lalu **Save**.

Tidak perlu memasukkan kartu kredit. Kuota gratis 10.000 unit per hari sudah cukup, karena bot ini memakai sekitar 8.000 unit per hari. Simpan kuncinya baik-baik dan jangan kirim lewat chat.

### 3. Isi Secrets di GitHub
Di repo, buka **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Nama | Isi |
|---|---|
| `YOUTUBE_API_KEY` | kunci dari langkah 2 |

Tab **Variables** opsional:

| Nama | Default | Arti |
|---|---|---|
| `MIN_VIEWS` | 50000 | Tayangan minimum video YouTube. |
| `MIN_LIKES_X` | 10000 | Like minimum video X. |
| `LOOKBACK_DAYS` | 1 | 1 = hari ini dan kemarin (WIB). Isi 0 untuk hari ini saja. |
| `MAX_DURATION` | 180 | Durasi maksimum video, dalam detik. 180 detik adalah batas YouTube Shorts. |
| `YT_TYPE_QUERIES` | politik, prabowo, jokowi, dpr, partai | Kata kunci jenis video, dipisah `\|\|`. Setiap kata kunci memakai 100 unit kuota per putaran. |
| `YT_CATEGORIES` | 25,22,24 | Kategori untuk pencarian umum. Setiap kategori memakai 100 unit kuota per putaran. |

Kuota: (jumlah kata kunci + jumlah kategori) × 100 unit × 8 putaran per hari harus di bawah 10.000. Dengan setelan bawaan, pemakaiannya sekitar 8.000 unit per hari. Kalau menambah kata kunci, kurangi kategori.
| `SUBREDDITS` | indonesia | Subreddit sumber link, dipisah koma. |
| `EXTRA_BLOCKED` | – | Nama channel atau akun tambahan yang dibuang, dipisah koma. |

### 4. Nyalakan dashboard (GitHub Pages)
Buka **Settings** → **Pages**. Pilih **Deploy from a branch**, branch `main`, folder `/docs`, lalu **Save**.
Dashboard bisa dibuka (juga dari HP) di `https://<username>.github.io/video-viral-indonesia/`.

### 5. Jalankan pertama kali
Buka tab **Actions**, pilih **Kumpulkan video viral Indonesia**, lalu klik **Run workflow**.

---

## Dashboard di PC dengan tombol Download YouTube
Klik dua kali **`Buka Dashboard.bat`**. Dashboard terbuka di http://localhost:8765, dan **setiap video YouTube punya tombol ⬇ Download** (MP4 sampai 1080p). Biarkan jendela hitamnya terbuka selama Anda memakai dashboard.

Supaya dashboard di PC menampilkan hasil bot di cloud (bukan hasil lokal), buat file `app.local.json`:
```json
{"data_url": "https://<username>.github.io/video-viral-indonesia/videos.json"}
```

Kalau dibuka dari GitHub Pages (misalnya di HP), tombol video YouTube berupa **Salin link**, karena pengunduh YouTube harus berjalan di PC.

Pemasangan pertama kali (sekali saja, kalau folder `.venv` belum ada):
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-local.txt
```

## Menjalankan bot di PC sendiri
- Isi kunci dan langsung jalankan bot: `.venv\Scripts\python.exe isi_kunci.py`
- Jalankan bot lagi: `.venv\Scripts\python.exe src\collect.py`

## Kalau ada masalah
- **"Kunci YouTube ditolak"**: pastikan YouTube Data API v3 sudah di-**Enable** di proyek yang sama dengan kuncinya.
- **"Kuota harian YouTube habis"**: kurangi jumlah kategori di `YT_CATEGORIES`. Kuota terisi lagi setiap hari sekitar pukul 14.00 WIB.
- **Reddit gagal (HTTP 403/429)**: Reddit kadang memblokir server GitHub. Sumber YouTube tetap berjalan.
- **Masih ada potongan TV yang lolos**: tambahkan nama channel-nya ke `EXTRA_BLOCKED`.

## Batasan
- Bot tidak bisa "melihat" isi video, jadi penyaringan hanya berdasarkan nama channel dan teks. Video viral lain seperti musik atau hiburan bisa ikut masuk.
- **Hak cipta**: video tetap milik pembuatnya. Minta izin atau cantumkan sumber sebelum mengunggah ulang.

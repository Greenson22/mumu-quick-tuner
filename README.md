# MuMu Quick Tuner

Aplikasi desktop PyQt6 untuk mengubah pengaturan MuMu Player dengan cepat:
resolusi, FPS, renderer, GPU/video memory, serta CPU & RAM — semuanya dari
satu jendela.

Aplikasi memakai **CLI resmi** `MuMuManager.exe`, jadi tidak ada penulisan
manual ke file `.nemu` atau JSON MuMu. Perubahan diverifikasi ulang setelah
diterapkan.

## Fitur

- **Tampilan** — preset resolusi (Phone 1–4, Tablet, Widescreen) atau custom
  width/height/DPI; FPS maksimum, dynamic FPS, batas bawah, V-Sync, show FPS.
- **Grafis** — DirectX/Vulkan, video memory strategy (Auto / Performa /
  Tampilan), GPU model (Low/Middle/High/Custom), paksa GPU dedicated.
- **Performa** — mode Low/Middle/High/Custom, CPU core dan RAM dari daftar
  resmi MuMu (nilai `best` ditandai).
- **Profil** — preset bawaan Hemat/Seimbang/Performa dan profil custom
  tersimpan di `%APPDATA%\mumu-quick-tuner\profiles.json`.
- Backup otomatis config ke `backups/` sebelum setiap perubahan.
- Deteksi device berjalan; karena MuMu hanya menerima perubahan setting saat
  device berhenti, aplikasi menawarkan **Matikan & Terapkan** lebih dulu.
- Peringatan dan opsi jalankan ulang sebagai Administrator bila folder MuMu
  tidak bisa ditulis.

## Kebutuhan

- Windows 10/11
- Python 3.10 atau lebih baru
- MuMu Player 15 (Global maupun versi lain yang punya `MuMuManager.exe`)

## Instalasi & menjalankan

1. Buka folder project ini.
2. Sesuaikan `.env` (sudah dibuat dari `.env.example`):

   ```env
   MUMU_MANAGER=C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe
   MUMU_VM_NAME=helmatweu20@guru.sd.belajar.id
   MUMU_VM_INDEX=
   MUMU_BACKUP_DIR=backups
   MUMU_LOG_LEVEL=INFO
   ```

   - `MUMU_VM_NAME` adalah nama device seperti yang tampil di MuMu. Aplikasi
     mencari index secara otomatis supaya tetap benar walau index bergeser.
   - Isi `MUMU_VM_INDEX` hanya bila ingin mengunci ke index tertentu.
3. Jalankan:

   ```bat
   run.bat
   ```

   atau manual:

   ```bat
   py -3 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python -m app.main
   ```

Jika MuMu terpasang di folder lain, ubah `MUMU_MANAGER`.

## Cara pakai

1. Tunggu aplikasi menampilkan nama device dan status **Berhenti/Berjalan**.
2. Ubah nilai di tab **Tampilan**, **Grafis**, atau **Performa**.
3. Klik **Terapkan**. Hanya nilai yang berubah yang dikirim ke MuMu.
4. Jika device sedang berjalan, aplikasi menawarkan **Matikan & Terapkan**
   (MuMu tidak menerima perubahan setting saat device hidup). Setelah itu
   nyalakan lagi lewat tombol **Restart Device**.
5. Gunakan tab **Profil** untuk menerapkan kombinasi setting sekaligus.

## Pemetaan setting ke MuMuManager

| Tab | Key CLI |
|---|---|
| Resolusi | `resolution_mode`, `resolution_width.custom`, `resolution_height.custom`, `resolution_dpi.custom` |
| FPS | `max_frame_rate`, `dynamic_adjust_frame_rate`, `dynamic_low_frame_rate_limit`, `vertical_sync`, `show_frame_rate` |
| Renderer | `renderer_mode` (`dx` / `vk`) |
| Video memory | `renderer_strategy` (`auto` / `perf` / `dis`) |
| GPU | `gpu_mode`, `gpu_model.custom`, `force_discrete_graphics` |
| CPU/RAM | `performance_mode`, `performance_cpu.custom`, `performance_mem.custom` |

Catatan: opsi **GPU Usage Policy (Optimal)** hanya tersedia di GUI MuMu dan
tidak diekspos oleh CLI, sehingga tidak diubah oleh aplikasi ini.

## Struktur project

```
app/
  main.py              # entry point
  config.py            # pembacaan .env
  mumu.py              # wrapper MuMuManager (subprocess + JSON)
  models.py            # key, label, parsing metadata
  services/backup.py   # backup config sebelum apply
  services/profiles.py # preset & profil custom
  ui/main_window.py    # jendela, worker thread, alur apply
  ui/sections.py       # tab Tampilan/Grafis/Performa/Profil
  ui/widgets.py        # tema & komponen
tests/                 # unit test tanpa kebutuhan MuMu/PyQt
```

## Menjalankan tes

```bat
python -m unittest discover -s tests -v
```

## Troubleshooting

- **"MuMuManager.exe tidak ditemukan"** — periksa `MUMU_MANAGER` di `.env`.
- **"Device bernama ... tidak ditemukan"** — buka MuMu, pastikan nama device
  sama persis dengan `MUMU_VM_NAME` (termasuk huruf besar/kecil).
- **Gagal menulis / butuh Administrator** — aplikasi menawarkan relaunch
  sebagai Administrator. Bisa juga jalankan terminal sebagai Admin lalu
  `run.bat`.
- **Perubahan belum terasa** — pastikan device sudah di-restart setelah
  menerapkan setting.
- Log ada di `logs/app.log`.

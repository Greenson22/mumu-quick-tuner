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
- **Grup** — deteksi semua device MuMu, pilih beberapa menjadi grup bernama,
  lalu terapkan preset yang sama ke seluruh anggota sekaligus tanpa mengubah
  nama device. Grup tersimpan di
  `%APPDATA%\mumu-quick-tuner\groups.json`.
- **Preset bernama** — simpan setting dari form device aktif sebagai preset
  baru, lalu pakai ulang kapan saja dari tab Profil maupun tab Grup.
- **Buka aplikasi otomatis** — isi nama paket Android (mis. `com.whatsapp`),
  lalu gunakan **Nyalakan & Buka**, atau centang **Buka otomatis setelah
  menyala** agar tombol Restart Device dan batch grup ikut membuka aplikasi
  setelah Android siap. Daftar aplikasi terpasang bisa dimuat lewat tombol
  **Muat Daftar**.
- **Otomatisasi grup** — pilih grup, atur jumlah device per batch (default 3),
  daftar aplikasi global, durasi acak per device (mis. 4–6 menit), dan script
  koordinat manual (tap/swipe/tunggu/tombol) per aplikasi. Device dinyalakan
  paralel per batch, aplikasi dibuka, sesi berjalan, lalu device dimatikan dan
  batch berikutnya dilanjutkan sampai seluruh grup selesai. Tersedia tombol
  **Stop** dan laporan JSON.
- Backup otomatis config ke `backups/` sebelum setiap perubahan.
- Deteksi device berjalan; karena MuMu hanya menerima perubahan setting saat
  device berhenti, aplikasi menawarkan **Matikan & Terapkan** lebih dulu.
  Untuk batch grup, device yang berjalan dimatikan lalu dinyalakan kembali
  otomatis (opsional).
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

## Membuka aplikasi otomatis

1. Pada kartu **Aplikasi**, isi nama paket Android (mis. `com.whatsapp`) atau
   pilih dari daftar bawaan. Tombol **Muat Daftar** menampilkan aplikasi yang
   terpasang di device (device harus sudah menyala dan Android siap).
2. Klik **Nyalakan & Buka** untuk menyalakan device lalu membuka aplikasi
   setelah Android siap. Kalau device sudah berjalan, tombol berubah menjadi
   **Buka Aplikasi** dan langsung membuka aplikasinya.
3. Centang **Buka otomatis setelah menyala** agar tombol **Restart Device**
   dan proses restart di batch grup juga membuka aplikasi yang sama.
4. Pilihan paket dan checkbox disimpan di
   `%APPDATA%\mumu-quick-tuner\settings.json`. Nilai awal juga bisa diberikan
   lewat `.env` (`MUMU_AUTO_APP_PACKAGE`, `MUMU_AUTO_OPEN_APP`).

## Mengelola grup device

1. Buka tab **Grup**. Semua device yang dibuat di MuMu akan terdeteksi
   otomatis beserta index dan statusnya.
2. Centang device yang ingin digabung, klik **Buat Grup…**, lalu beri nama
   grup. Grup disimpan permanen berdasarkan **nama device**, bukan index —
   jadi tetap benar walau index bergeser.
3. Untuk mengubah anggota, pilih grup lalu gunakan **Tambah Pilihan**,
   **Keluarkan Pilihan**, **Ganti Nama…**, atau **Hapus**.
4. Pilih preset pada dropdown **Preset setting**, lalu klik
   **Terapkan ke Grup**. Hanya setting yang berbeda yang dikirim, dan setiap
   device diverifikasi ulang setelah ditulis.
5. Ingin memakai setting dari device yang sedang dibuka? Klik
   **Samakan dengan Device Aktif**.
6. Ingin menyimpan setting tersebut sebagai preset baru? Klik
   **Simpan Setting Aktif sebagai Preset…** dan beri nama. Preset langsung
   muncul di dropdown tab Grup dan tab Profil.
7. Jika ada device yang gagal, proses tetap berlanjut ke device lain. Klik
   **Ulangi yang Gagal** untuk mencoba lagi hanya pada device tersebut.

Nama device tidak pernah diubah: aplikasi tidak mengirim key `player_name`
atau identitas HP, dan preset dibatasi ke 17 key yang dikelola (resolusi, FPS,
renderer, GPU, CPU/RAM).

## Otomatisasi grup

Tab **Otomatisasi** menjalankan sesi otomatis untuk seluruh anggota grup:

1. Pilih grup, jumlah device per batch (default 3), dan durasi acak per device
   dalam menit (mis. min 4 dan maks 6).
2. Isi **Aplikasi otomatisasi (global)**. Daftar ini dipakai semua grup. Paket
   bisa ditambah manual atau diambil dari device yang sedang berjalan lewat
   **Tambah dari Device…**.
3. Untuk setiap aplikasi, klik **Edit Script…** bila ingin interaksi otomatis.
   Langkah yang tersedia: **Tap**, **Swipe**, **Tunggu**, dan **Tombol**
   (back/home/recent/enter). Contoh: tap sidebar `(60, 400)` → tunggu
   `1000 ms` → tap halaman `(300, 200)`.
4. Klik **Mulai Otomatisasi**. Aplikasi akan:
   - menyalakan device per batch secara paralel;
   - menunggu Android siap dan memeriksa apakah semua aplikasi aktif terpasang;
   - mematikan device dan mencatatnya gagal jika ada aplikasi yang tidak
     terpasang;
   - membuka aplikasi berurutan lalu menjalankan script masing-masing;
   - membiarkan device menyala sampai durasi acak habis;
   - mematikan device, lalu lanjut ke batch berikutnya.
5. Tekan **Stop** kapan saja untuk menghentikan sesi; device aktif dimatikan dan
   batch berikutnya dilewati.
6. Setelah selesai, semua device yang terlibat dimatikan dan laporan ditampilkan.
   Laporan JSON disimpan di `logs/automation-YYYYMMDD-HHMMSS.json`.

Konfigurasi otomatisasi disimpan di
`%APPDATA%\mumu-quick-tuner\automation.json`. Jika daftar aplikasi masih kosong,
paket dari pengaturan **Aplikasi** lama disalin otomatis.

Koordinat script mengikuti **resolusi referensi** (default 1280×720). Jika opsi
**Skalakan koordinat** aktif, koordinat disesuaikan ke resolusi masing-masing
device. Nonaktifkan opsi tersebut bila script sudah memakai koordinat asli tiap
device.

Perintah interaksi memakai ADB bawaan MuMu:

```text
MuMuManager.exe adb -v <index> -c "input tap <x> <y>"
MuMuManager.exe adb -v <index> -c "input swipe <x1> <y1> <x2> <y2> <durasi>"
MuMuManager.exe adb -v <index> -c "input keyevent <kode>"
```

## Pemetaan setting ke MuMuManager

| Tab | Key CLI |
|---|---|
| Resolusi | `resolution_mode`, `resolution_width.custom`, `resolution_height.custom`, `resolution_dpi.custom` |
| FPS | `max_frame_rate`, `dynamic_adjust_frame_rate`, `dynamic_low_frame_rate_limit`, `vertical_sync`, `show_frame_rate` |
| Renderer | `renderer_mode` (`dx` / `vk`) |
| Video memory | `renderer_strategy` (`auto` / `perf` / `dis`) |
| GPU | `gpu_mode`, `gpu_model.custom`, `force_discrete_graphics` |
| CPU/RAM | `performance_mode`, `performance_cpu.custom`, `performance_mem.custom` |
| Buka aplikasi | `control -v <index> app launch --package <package>` |
| Interaksi otomatis | `adb -v <index> -c "input tap/swipe/keyevent ..."` |

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
  services/groups.py   # penyimpanan grup device
  services/settings.py # preferensi aplikasi otomatis
  services/group_apply.py # eksekutor batch per device
  services/automation.py # konfigurasi & laporan otomatisasi
  services/automation_run.py # eksekutor sesi otomatisasi grup
  ui/main_window.py    # jendela, worker thread, alur apply & batch
  ui/sections.py       # tab Tampilan/Grafis/Performa/Profil
  ui/groups.py         # tab Grup
  ui/automation.py     # tab Otomatisasi & editor script
  ui/widgets.py        # tema & komponen
rancangan/             # dokumen rancangan fitur
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

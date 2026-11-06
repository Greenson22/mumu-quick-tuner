# Rancangan Fitur Otomatisasi Grup

Status: sudah dibangun (lihat README bagian Otomatisasi grup).

## Tujuan

Menambahkan sesi otomatisasi per grup: menyalakan device per batch (default 3),
membuka daftar aplikasi global yang dipilih, menjalankan script koordinat
manual per aplikasi, membiarkan device menyala selama durasi acak per device
(mis. 4–6 menit), lalu mematikan device dan melanjutkan batch berikutnya sampai
seluruh anggota grup selesai. Di akhir semua device dimatikan dan laporan
disimpan.

## Keputusan

| Hal | Keputusan |
|---|---|
| Jumlah device | Batch size dapat diatur, default 3 |
| Urutan batch | Semua anggota grup diproses sampai habis |
| Konkurensi | Device dalam satu batch dinyalakan dan dijalankan bersamaan |
| Durasi | Acak per device, misal 4–6 menit |
| Daftar aplikasi | Global, dipakai semua grup |
| Aplikasi tidak terpasang | Device dimatikan dan tidak dijalankan |
| Interaksi | Script koordinat manual per aplikasi, dijalankan ke semua device |
| Kontrol | Tombol Mulai/Stop |
| Laporan | Dialog + file JSON di `logs/` |

## UI

Tab baru **Otomatisasi**:

1. **Kartu Grup & Sesi**
   - Dropdown grup.
   - Jumlah device per batch.
   - Durasi minimum/maksimum (menit, desimal).
   - Checkbox interaksi otomatis.
   - Checkbox skala koordinat + resolusi referensi script.
   - Tombol Mulai Otomatisasi / Stop.
   - Status sesi.

2. **Kartu Aplikasi Otomatisasi (Global)**
   - Tabel: aktif, nama, paket, jumlah langkah script.
   - Tambah manual / tambah dari device, hapus, edit script, naik/turun.

3. **Kartu Progres**
   - Tabel: Device, Batch, Status, Aplikasi, Durasi, Keterangan.

4. Dialog **Script Interaksi**
   - Langkah: Tap, Swipe, Tunggu, Tombol (back/home/task/enter).
   - Setiap langkah punya jeda setelah aksi (ms).
   - Contoh: tap sidebar (60, 400) → tunggu 1000 ms → tap halaman (300, 200).

Tab Grup mendapat tombol **Otomatisasi…** untuk membuka tab Otomatisasi dengan
grup yang sedang dipilih.

## Penyimpanan

`%APPDATA%\mumu-quick-tuner\automation.json`

```json
{
  "version": 1,
  "batch_size": 3,
  "duration_min_sec": 240,
  "duration_max_sec": 360,
  "interaction_enabled": true,
  "scale_coordinates": true,
  "reference_resolution": [1280, 720],
  "apps": [
    {
      "package": "com.whatsapp",
      "label": "WhatsApp",
      "enabled": true,
      "steps": [
        {"action": "tap", "x": 60, "y": 400, "delay_ms": 500},
        {"action": "wait", "delay_ms": 1000},
        {"action": "tap", "x": 300, "y": 200, "delay_ms": 500}
      ]
    }
  ]
}
```

Jika file belum ada, paket dari `settings.json` (`app_package`) disalin sebagai
aplikasi pertama.

## Alur per device

1. `control launch` jika device belum berjalan.
2. Tunggu `is_android_started` (timeout 150 detik).
3. Baca daftar aplikasi terpasang.
4. Jika ada aplikasi aktif yang tidak terpasang → shutdown, status gagal,
   device tidak dijalankan.
5. Buka setiap aplikasi aktif secara berurutan.
6. Jalankan script aplikasi jika interaksi aktif.
7. Durasi acak dipilih `randint(min_sec, max_sec)` sejak Android siap.
8. Idle sampai durasi habis; cek stop setiap ±500 ms.
9. Shutdown device dan tunggu berhenti.

Batch berikutnya dimulai setelah semua device pada batch sebelumnya selesai.
Di akhir dilakukan sapuan shutdown untuk semua device grup.

## ADB

Perintah melalui MuMuManager:

```text
MuMuManager.exe adb -v <index> -c "<command>"
```

Primitive: `input tap x y`, `input swipe x1 y1 x2 y2 durasi`,
`input keyevent <kode>`, dan `wm size` untuk scaling koordinat.

## Penanganan kasus

- Aplikasi tidak terpasang → device shutdown, status gagal, alasan dicatat.
- Gagal launch device → device dilewati, batch lanjut.
- Script gagal → dicatat sebagai peringatan, sesi lanjut.
- Stop → device aktif dimatikan, batch berikutnya dilewati, laporan tetap ditulis.
- Otomatisasi berjalan → tombol Terapkan/Restart/Refresh dan tab lain
  dinonaktifkan; Stop tetap aktif.
- Tutup aplikasi saat otomatisasi berjalan → konfirmasi, Stop, matikan device.
- Device dalam grup hilang → dicatat di laporan.
- Resolusi berbeda → koordinat diskalakan jika opsi aktif.

## File

| File | Perubahan |
|---|---|
| `app/services/automation.py` | Baru — model, stored config, laporan |
| `app/services/automation_run.py` | Baru — eksekutor sesi |
| `app/ui/automation.py` | Baru — tab Otomatisasi + dialog script |
| `app/mumu.py` | `adb_shell`, primitive input, `get_screen_size` |
| `app/ui/main_window.py` | Tab, sinyal, start/stop, worker, laporan |
| `app/ui/groups.py` | Tombol Otomatisasi… |
| `README.md` | Dokumentasi |
| `tests/test_automation_store.py` | Tes penyimpanan & validasi |
| `tests/test_automation_run.py` | Tes batch, missing app, stop, laporan |
| `tests/test_adb.py` | Tes konstruksi perintah ADB |

## Pengujian

- Grup 7 device, batch 3 → 3-3-1.
- Aplikasi hilang → device shutdown, tidak ada sesi.
- Aplikasi dibuka berurutan + script dijalankan.
- Durasi acak berada dalam rentang.
- Stop di tengah sesi → device dimatikan, batch sisa dilewati.
- Laporan JSON valid.
- Validasi konfigurasi.
- Perintah ADB tap/swipe/keyevent.

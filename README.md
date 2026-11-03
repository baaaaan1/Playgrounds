# Playgrounds

Desktop AI playground yang ringan: PyQt6, streaming SSE incremental, config via QSettings, API key di Windows Credential Manager, packaging PyInstaller `--onedir`, installer MSI lewat WiX Toolset.

## Prasyarat

- Windows 10/11 x64
- Python 3.10+
- PyQt6 6.7+ (termasuk QtSvg untuk ikon SVG)
- Dependensi build dari `.[dev]` termasuk Pillow; WiX v4+ hanya untuk MSI

## Menjalankan

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
python -m app
```

Buka **Settings** (Ctrl+,), buat koneksi bernama, isi base URL dan API key opsional,
lalu klik **Fetch models**. Fetch yang berhasil langsung menyimpan profil koneksi tersebut,
termasuk daftar model, endpoint, dan API key. Filter daftar model, klik model yang diinginkan,
lalu **Save connection** untuk menyimpan perubahan pilihan. Cancel hanya membuang perubahan
yang belum disimpan, bukan hasil fetch yang sudah tersimpan. ID model juga bisa diketik manual
jika endpoint tidak menyediakan `/models`.

Setiap koneksi menyimpan endpoint, daftar model, temperature, max tokens, system prompt,
dan referensi API key secara terpisah. Beberapa koneksi boleh memakai preset provider
yang sama. **Use preset** hanya mengisi draft aktif, bukan mengganti konfigurasi koneksi lain.
Pilih koneksi aktif melalui dropdown di toolbar. Tombol mata menampilkan/menyembunyikan
teks API key; key selalu disembunyikan kembali saat berganti koneksi atau menutup dialog.

## Perintah

| Perintah | Fungsi |
|---|---|
| `python -m app` | Jalankan aplikasi |
| `python -m pytest` | Regression test profil, credential, model discovery, UI, SSE, dan store |
| `python -m ruff check .` | Lint |
| `powershell -File build\build.ps1` | Build `dist\Playgrounds\` |
| `powershell -File build\build.ps1 -Installer` | Build exe + `dist\Playgrounds-<versi>-x64.msi` |

Test tanpa membuka window: `python -m app --smoke`. Untuk backend Windows asli:
`python -m app --smoke-native`. Kedua mode memakai konfigurasi dan percakapan sementara,
bukan data pengguna. Build menunggu kedua smoke test selesai dan memeriksa exit code.

## Struktur

```
app/
  core/   models, profiles, config (QSettings), credentials (Credential Manager), store (JSON)
  net/    sse.py, client.py, models.py (model discovery via QNetworkAccessManager)
  ui/     main_window, window_chrome, chat_view, composer, sidebar, settings, theme
  resources/line-md/  Material Line SVG dan lisensi (dibundel offline)
build/
  playgrounds.spec, version_info.txt, build.ps1, installer/Product.wxs
tests/
```

Endpoint OpenAI-compatible baru cukup ditambahkan sebagai koneksi dari UI, tanpa mengubah kode.
`ProviderInfo` di `app/core/providers/registry.py` hanya menyediakan preset awal.
Title bar memakai panel minimize/maximize/close kustom; area judul mendukung drag dan
double-click maximize/restore, serta resize dari tepi jendela.

Semua ikon aplikasi menggunakan **Material Line Icons (line-md)** oleh Vjacheslav Trushkin,
dari https://icon-sets.iconify.design/line-md/. SVG disertakan lokal dengan animasi dibekukan
ke frame akhir. Atribusi dan lisensi MIT ada di `app/resources/line-md/LICENSE.txt`.

## Data pengguna

- Konfigurasi: `QSettings("Playgrounds", "Playgrounds")` (registry HKCU)
- Percakapan: `%APPDATA%\Playgrounds\conversations\*.json`
- Log: `%APPDATA%\Playgrounds\logs\playgrounds.log`
- API key koneksi baru: Windows Credential Manager, target `Playgrounds/profile/<profile-id>`

Konfigurasi provider lama dimigrasikan otomatis menjadi profil koneksi. Referensi credential
lama (`Playgrounds/<provider-id>`) tetap dipakai agar key tidak perlu dimasukkan ulang.
API key tidak disimpan dalam QSettings atau file percakapan.

## Installer (tahap akhir)

```powershell
dotnet tool install --global wix
powershell -File build\build.ps1 -Installer
```

Installer per-user (tanpa UAC), install ke `%LOCALAPPDATA%\Playgrounds`, shortcut Start Menu, upgrade in-place via `MajorUpgrade`.

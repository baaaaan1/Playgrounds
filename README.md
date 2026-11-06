# Playgrounds

Desktop AI playground yang ringan: PyQt6, streaming SSE incremental, config via QSettings, API key di Windows Credential Manager, packaging PyInstaller `--onedir`, installer MSI lewat WiX Toolset.

## Download Windows

Unduh **`Playgrounds-<versi>-x64.msi`** dari
[GitHub Releases terbaru](https://github.com/baaaaan1/Playgrounds/releases/latest).
Untuk pengguna Windows 10/11 x64, **Python tidak perlu dipasang**. Jalankan installer,
lalu buka Playgrounds dari Start Menu. Update dapat diperiksa dari **Settings > Updates**.
Jika belum ada rilis publik, tautan Latest belum menyediakan installer.

Installer dipasang per-user tanpa UAC. Data pengguna disimpan di luar folder instalasi
dan bukan bagian dari paket installer. Lihat bagian **Data pengguna** sebelum menghapus data.

Setiap rilis menyertakan `SHA256SUMS.txt`. Untuk memeriksa installer hasil download:

```powershell
Get-FileHash -LiteralPath .\Playgrounds-0.1.0-x64.msi -Algorithm SHA256
```

Sesuaikan versi dan cocokkan hash dengan baris nama file tersebut di `SHA256SUMS.txt`.
Checksum mendeteksi file rusak/berubah, bukan pengganti tanda tangan penerbit.
Build CI saat ini **belum ditandatangani**; Windows dapat menampilkan Unknown publisher
atau peringatan SmartScreen. Jangan melewati peringatan untuk file dari sumber yang tidak dipercaya.

## Prasyarat Pengembangan

- Windows 10/11 x64
- Python 3.10+
- PyQt6 6.7+ (termasuk QtSvg untuk ikon SVG)
- Dependensi build dari `.[dev]` termasuk Pillow; WiX v5+ hanya untuk MSI
- Rilis CI memakai Python 3.12 x64, .NET SDK 8, dan WiX 7.0.1

## Menjalankan

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
python -m app
```

Buka **Settings** (Ctrl+,), buat koneksi bernama, isi base URL dan API key opsional,
lalu klik **Fetch models**. Hasil fetch belum disimpan. Filter daftar model, klik model yang
diinginkan, lalu **Save connection** untuk menyimpan profil, endpoint, API key, dan daftar model.
Cancel membuang perubahan yang belum disimpan, termasuk hasil fetch. ID model juga bisa diketik manual
jika endpoint tidak menyediakan `/models`.

Setiap koneksi menyimpan endpoint, daftar model, temperature, max tokens, system prompt,
dan referensi API key secara terpisah. Beberapa koneksi boleh memakai preset provider
yang sama. **Use preset** hanya mengisi draft aktif, bukan mengganti konfigurasi koneksi lain.
Pilih koneksi aktif melalui dropdown di toolbar. Tombol mata menampilkan/menyembunyikan
teks API key; key selalu disembunyikan kembali saat berganti koneksi atau menutup dialog.

## Perintah

English-first UI standards, Qt translation architecture, and the repeatable UI
audit checklist are documented in [the localization guide](LOCALIZATION.md).

| Perintah | Fungsi |
|---|---|
| `python -m app` | Jalankan aplikasi |
| `python -m pytest` | Regression test profil, credential, model discovery, UI, SSE, dan store |
| `python -m ruff check .` | Lint |
| `powershell -File build\build.ps1` | Build `dist\Playgrounds\` |
| `powershell -File build\build.ps1 -Installer` | Build exe + `dist\Playgrounds-<versi>-x64.msi` |
| `powershell -File build\build.ps1 -Installer -ReleaseTag v0.1.0` | Build aset rilis dari tag bersih yang sesuai versi |

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

Ikon aplikasi mencakup **Material Line Icons (line-md)** oleh Vjacheslav Trushkin,
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

## Installer

```powershell
dotnet tool install --global wix --version 7.0.1
powershell -File build\build.ps1 -Installer
```

Installer per-user (tanpa UAC), install ke `%LOCALAPPDATA%\Playgrounds`, shortcut Start Menu, upgrade in-place via `MajorUpgrade`.

Tutup aplikasi dari folder output sebelum membangun ulang karena Windows mengunci DLL
yang sedang dipakai. Alternatifnya gunakan output terpisah, misalnya
`powershell -File build\build.ps1 -Installer -OutputDir dist\verification`.

## Rilis GitHub

Workflow [Windows Release](.github/workflows/release.yml) berjalan saat tag `vMAJOR.MINOR.PATCH`
di-push. Workflow juga bisa dijalankan manual melalui Actions dengan memasukkan tag yang
sudah ada. Workflow tidak membuat commit atau tag dan hanya membuat **draft release**,
bukan langsung memublikasikannya. Workflow dibatasi ke repository `baaaaan1/Playgrounds`
karena URL updater mengarah ke repository tersebut.

1. Tentukan versi stabil di `pyproject.toml`. Tag harus cocok persis, misalnya versi
   `0.1.0` dengan tag `v0.1.0`. Versi prerelease seperti `0.1.0-rc.1` belum didukung.
2. Pastikan semua source, aset, lisensi, test, dan skrip build yang diperlukan sudah
   masuk commit rilis, lalu buat tag pada commit itu. Build bertag menolak worktree
   kotor, source yang belum dilacak, tag berbeda commit, Git LFS, dan submodule.
3. Saat siap menerbitkan ke GitHub, push commit dan tag tersebut. CI menjalankan test,
   lint, build PyInstaller, smoke test packaged exe (offscreen dan native), lalu MSI.
4. Unduh aset dari draft release. Uji install pada Windows bersih tanpa Python,
   jalankan aplikasi, uji upgrade dari MSI sebelumnya bila ada, lalu uninstall.
   Periksa juga bahwa data pengguna tidak hilang saat upgrade.
5. Tinjau release notes, status signing, notice lisensi, dan kelengkapan corresponding
   source dependensi. Publish draft sebagai rilis stabil/Latest hanya setelah semua lolos.

Aset di `dist\release\` untuk build bertag:

| File | Fungsi |
|---|---|
| `Playgrounds-<versi>-x64.msi` | Installer utama |
| `update.json` | Versi, URL MSI, dan SHA-256 untuk updater aplikasi |
| `Playgrounds-<versi>-source.zip` | Source proyek dan skrip build dari tag yang sama |
| `build-environment.json` | Commit, versi Python, platform, dan versi paket build |
| `SHA256SUMS.txt` | SHA-256 semua aset di atas |

Folder output rilis harus kosong sebelum packaging agar aset lama tidak ikut terunggah.
Workflow menolak mengganti release yang sudah ada. `build-environment.json` mencatat
versi dependensi yang dipakai, tetapi bukan jaminan build bit-for-bit reproducible.
Jangan commit `dist/`, MSI, credential, atau sertifikat signing ke repository.

Build lokal tanpa `-ReleaseTag` tetap bisa dilakukan pada source yang sedang dikerjakan;
hasilnya untuk pengujian, bukan paket rilis dengan jaminan kesesuaian source/tag.
Jangan mendistribusikan `Playgrounds.exe` sendirian karena build memakai `--onedir`.

### Code Signing

Sertifikat code signing tepercaya dan Windows SDK SignTool disediakan oleh maintainer,
bukan dibuat otomatis oleh proyek. Contoh build bertanda tangan dari tag bersih:

```powershell
powershell -File build\build.ps1 -Installer -ReleaseTag v0.1.0 `
  -SigningCertificateThumbprint "THUMBPRINT_SERTIFIKAT" `
  -SignTool "C:\Path\To\Windows SDK\signtool.exe"
```

Sertifikat harus tersedia di personal certificate store pengguna yang menjalankan build.
Script menandatangani dan memverifikasi EXE sebelum dimasukkan ke MSI, lalu menandatangani
dan memverifikasi MSI sebelum membuat manifest/checksum. Timestamp memakai DigiCert RFC 3161;
layanan lain bisa dipilih lewat `-TimestampUrl`. Jangan menandatangani atau mengubah file
di `dist\release\` setelah hash dibuat. Signing tepercaya tidak menjamin SmartScreen
langsung berhenti menampilkan peringatan.

Workflow CI bawaan tidak diberi private key dan menghasilkan build unsigned. Untuk rilis
signed saat ini, unggah aset build signed lokal ke draft secara manual dan sesuaikan release
notes; jangan mencampur MSI signed dengan manifest/checksum dari build unsigned.

## Lisensi

Playgrounds dilisensikan dengan **GNU General Public License versi 3 saja**
(`SPDX-License-Identifier: GPL-3.0-only`), bukan opsi "atau versi setelahnya".
Teks lengkap ada di [LICENSE](LICENSE) dan disertakan dalam paket aplikasi.

Dependensi dan aset pihak ketiga tetap menggunakan lisensinya masing-masing;
misalnya ikon Material Line tetap berlisensi MIT dengan atribusi yang sudah disertakan.
Saat mendistribusikan binary, sertakan akses ke corresponding source dan penuhi
ketentuan distribusi GPL v3. Build membundel notice dan teks lisensi dependensi yang
tersedia di lingkungan build ke `_internal/licenses/` (termasuk Python, PyQt6/Qt6,
SIP, dan bootloader PyInstaller), serta lisensi aset di direktori resources.
Build gagal jika teks lisensi paket wajib tidak ditemukan.

**Checklist sebelum publish:** source ZIP proyek saja tidak otomatis memenuhi seluruh
kewajiban lisensi komponen binary. Periksa corresponding source untuk versi tepat
PyQt6/Qt6 dan komponen copyleft lain yang ikut dibundel; sediakan source yang diwajibkan
beserta perubahan dan instruksi build-nya melalui release atau mekanisme distribusi
yang memenuhi lisensi terkait. Tinjau juga komponen pihak ketiga di dalam Qt/Python.
Pengumpulan notice otomatis adalah bantuan audit, bukan verifikasi legal menyeluruh.
Lisensi proyek tidak menggantikan ketentuan penggunaan tool build, termasuk EULA WiX.

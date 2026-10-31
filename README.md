# Playgrounds

Desktop AI playground yang ringan: PyQt6, streaming SSE incremental, config via QSettings, API key di Windows Credential Manager, packaging PyInstaller `--onedir`, installer MSI lewat WiX Toolset.

## Prasyarat

- Windows 10/11 x64
- Python 3.10+
- (opsional) Pillow untuk generate ikon, WiX v4+ untuk MSI

## Menjalankan

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
python -m app
```

Buka **Settings** (Ctrl+,), pilih provider, isi API key, lalu mulai chat.

## Perintah

| Perintah | Fungsi |
|---|---|
| `python -m app` | Jalankan aplikasi |
| `python -m pytest` | Unit test (SSE parser, store, markdown) |
| `python -m ruff check .` | Lint |
| `powershell -File build\build.ps1` | Build `dist\Playgrounds\` |
| `powershell -File build\build.ps1 -Installer` | Build exe + `dist\Playgrounds-<versi>-x64.msi` |

Test tanpa membuka window: `python -m app --smoke`.

## Struktur

```
app/
  core/   models, config (QSettings), credentials (Credential Manager), store (JSON)
  net/    sse.py (parser incremental), client.py (QNetworkAccessManager)
  ui/     main_window, chat_view, composer, sidebar, settings, theme
build/
  playgrounds.spec, version_info.txt, build.ps1, installer/Product.wxs
tests/
```

Menambah provider baru: tambahkan `ProviderInfo` di `app/core/providers/registry.py`; UI dan networking tidak perlu diubah.

## Data pengguna

- Konfigurasi: `QSettings("Playgrounds", "Playgrounds")` (registry HKCU)
- Percakapan: `%APPDATA%\Playgrounds\conversations\*.json`
- Log: `%APPDATA%\Playgrounds\logs\playgrounds.log`
- API key: Windows Credential Manager, target `Playgrounds/<provider-id>`

## Installer (tahap akhir)

```powershell
dotnet tool install --global wix
powershell -File build\build.ps1 -Installer
```

Installer per-user (tanpa UAC), install ke `%LOCALAPPDATA%\Playgrounds`, shortcut Start Menu, upgrade in-place via `MajorUpgrade`.

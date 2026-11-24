# Activity Sheet

Local Windows tool for signing in to work activities with barcodes. One small program runs on each PC:
a local web server with a tray icon that opens the Activity Sheet window (Microsoft Edge in app mode).

## Features

- Activity list grouped into sections, with a Code128 barcode for each activity (JsBarcode).
- **Basic mode:** barcode on the left, the warehouse page (iframe) on the right, both full height.
- **Auto mode:** the operator scans their card and the program fills the warehouse form through
  Windows UI Automation (Start a new activity → card → activity code → Confirm). No mouse macros.
- Two lists: a shared list downloaded from your server, or your own local list on this PC.
  "Add new items" merges new server items into the local list without deleting or overwriting anything.
- Admin page for editing the lists (server list requires admin sign-in on the server).
- Settings page, tray menu, start after Windows sign-in, a single app window only.
- Canvas animations (disabled automatically when Windows "reduce animations" is on).
- Local address `http://activity-sheet.localhost:8080` (falls back to port 28000).

## Layout

```
ActivitySheet/
  ActivitySheet.pyw   program (server, tray, settings, data sync)
  bridge.py           warehouse automation (UI Automation)
  tray.py             tray icon (ctypes, no extra packages)
  libs/               bundled pure-Python libraries (uiautomation, comtypes)
  web/                pages, styles, scripts, fonts
  data/server.json    example activity list
```

## Running

Requirements: Windows 10/11 64-bit, Microsoft Edge, Python 3.12+.
No pip needed – libraries are bundled in `libs/`.

Without an installed Python: download the "Windows embeddable package (64-bit)" from python.org and
extract it into `ActivitySheet/python/` (so that `python/pythonw.exe` exists). Then run `Spustit.bat`.

## Configuration

`config.json` is created next to the program on first start. Set at least:

| key             | meaning                                                        |
|-----------------|----------------------------------------------------------------|
| `server_url`    | your server with the shared activity list (`https://example.com` in this repo) |
| `warehouse_url` | the warehouse page shown in the window                         |

Company logo: put it in `ActivitySheet/web/static/assets/logo.png` (text is shown when missing).

More details (in Czech) are in `ActivitySheet/README.txt`.

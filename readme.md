

\# Mini Download Manager



A lightweight, multi-threaded download manager built with Python, CustomTkinter, and Requests.



!\[Python](https://img.shields.io/badge/Python-3.10%2B-blue)

!\[CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-green)







\## Features



\- Multi-threaded downloads (daemon threads, UI never freezes)

\- Real Pause / Resume / Cancel support

\- HTTP Range support for resuming downloads after pause

\- Automatic filename detection from `Content-Disposition`

\- Unique filename handling (appends `(1)`, `(2)`, ... if file exists)

\- Temporary `.part` file during download; renamed on success, deleted on cancel/error

\- Live progress bar, speed, and transferred/total size

\- Scrollable download list with card-based UI

\- Custom save location picker

\- Clipboard shortcuts (`Ctrl+V`, `Ctrl+A`) and right-click context menu

\- Windows DPI awareness and custom taskbar icon

\- PyInstaller-ready (`resource\_path` helper)

\- Stable with 100+ concurrent downloads



\---



\## Project Structure



```

mini-download-manager/

├── logic.py      # DownloadTask class, threading, requests, file handling

├── main.py       # CustomTkinter UI, download cards, add-URL dialog

├── download\_manager.ico

└── README.md

```



\- \*\*`logic.py`\*\* — Core download engine. Contains `DownloadTask` (start/pause/resume/cancel, streaming, Range requests, speed calculation, thread-safe UI callbacks), helper functions (`format\_size`, `is\_valid\_url`, `extract\_filename\_from\_cd`, `make\_unique\_path`), and the `start\_download` factory.

\- \*\*`main.py`\*\* — Full UI: main window, scrollable download list, per-download cards with progress and controls, add-URL modal with validation and clipboard support.



\---



\## Requirements



\- Python 3.10+

\- Windows (for DPI and icon optimizations; other platforms work with reduced features)



\---



\## Installation



```bash

git clone https://github.com/mrpanahi2/mini-download-manager.git

cd mini-download-manager

pip install customtkinter requests

python main.py

```



\---



\## How It Works



1\. User enters a URL and selects a save folder.

2\. `DownloadTask` starts a daemon thread.

3\. The thread issues a streaming GET request.

4\. Filename is resolved from `Content-Disposition` or URL path.

5\. Chunks are written to a `.part` file; progress is pushed to the UI via `root\_win.after(0, ...)`.

6\. On pause, the connection is closed. On resume, a `Range` request continues from the current byte offset (if the server supports it).

7\. On success, the `.part` file is renamed to the final filename. On cancel or error, it is deleted.



\---



\## Known Limitations



\- Resume after closing the application is not supported (each new run starts from zero unless paused in the same session).

\- Servers without `Accept-Ranges` will restart from zero after a pause.

\- No queue limit; all downloads start immediately.

\- No bandwidth throttling.

\- UI is desktop-only (CustomTkinter).




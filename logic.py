import threading
import time
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
import requests

DEFAULT_SAVE_FOLDER = Path.home() / "Downloads"


def format_size(size):
    """Convert byte count to human-readable string."""
    if size <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def is_valid_url(url: str) -> bool:
    """Simple check that the URL starts with http:// or https://."""
    return bool(url) and urlparse(url).scheme in ("http", "https")


def extract_filename_from_cd(content_disposition: str):
    """Try to pull a filename from a Content-Disposition header."""
    if not content_disposition:
        return None
    # filename*=UTF-8''encoded  or  filename="quoted"  or  filename=plain
    match = re.search(
        r"filename\*\s*=\s*UTF-8''([^;]+)|filename\s*=\s*\"([^\"]+)\"|filename\s*=\s*([^;]+)",
        content_disposition,
        re.IGNORECASE,
    )
    if not match:
        return None
    name = next((g for g in match.groups() if g), None)
    return unquote(name.strip()) if name else None


def make_unique_path(path: Path) -> Path:
    """If path already exists, append (1), (2), ... before the suffix."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class DownloadTask:
    def __init__(self, url, root_win, update_callback, save_folder=None):
        self.url = url
        self.root_win = root_win
        self.update_callback = update_callback
        self.save_folder = Path(save_folder) if save_folder else DEFAULT_SAVE_FOLDER
        self.is_cancelled = False
        self.is_paused = False
        self.is_running = False
        self.downloaded_bytes = 0
        self.total_size = 0
        self.response = None
        self.save_path = None          # final path after successful rename
        self.part_path = None          # temporary .part file during download
        self._supports_range = False
        self._lock = threading.Lock()

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.is_cancelled = False
            self.is_paused = False
            threading.Thread(target=self._run, daemon=True).start()

    def pause(self):
        """Request a true pause: close the connection so the server does not time out."""
        with self._lock:
            if not self.is_cancelled and self.is_running and not self.is_paused:
                self.is_paused = True
                # Closing the response forces iter_content to stop; we will reopen with Range later.
                if self.response is not None:
                    try:
                        self.response.close()
                    except Exception:
                        pass
                    self.response = None

    def resume(self):
        """Clear the pause flag so the worker can reopen the connection with a Range header."""
        with self._lock:
            if not self.is_cancelled and self.is_paused:
                self.is_paused = False

    def cancel(self):
        """Abort the download and clean up the partial file."""
        with self._lock:
            self.is_cancelled = True
            self.is_paused = False
            if self.response is not None:
                try:
                    self.response.close()
                except Exception:
                    pass
                self.response = None

    def _notify(self, status, speed=0, error_detail=None):
        """Push progress data to the UI thread."""
        if self.total_size > 0:
            progress = min(max(self.downloaded_bytes / self.total_size, 0.0), 1.0)
        else:
            progress = 0.0

        data = {
            "status": status,
            "progress": progress,
            "speed": f"{format_size(speed)}/s" if speed > 0 else "0 B/s",
            "downloaded_str": format_size(self.downloaded_bytes),
            "total_str": format_size(self.total_size) if self.total_size > 0 else "Unknown",
            "error_detail": error_detail,
            "save_path": str(self.save_path) if self.save_path else None,
            "is_finished": status in ("Completed ✅", "Cancelled ❌") or status.startswith("Error"),
        }
        self.root_win.after(0, lambda d=data: self.update_callback(d))

    def _resolve_filename(self, response) -> str:
        """Prefer Content-Disposition, fall back to URL path (URL-decoded)."""
        cd = response.headers.get("Content-Disposition", "")
        name = extract_filename_from_cd(cd)
        if name:
            return name
        # Fallback: last path segment of the URL, decoded
        path = urlparse(self.url).path
        name = unquote(path.split("/")[-1]) if path else ""
        return name or "downloaded_file"

    def _open_request(self, start_byte: int = 0):
        """Issue a GET (or ranged GET) and return the response."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        if start_byte > 0:
            headers["Range"] = f"bytes={start_byte}-"
        resp = requests.get(self.url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
        return resp

    def _run(self):
        try:
            self.save_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return self._finish(f"Error creating folder: {e}")

        # First request to discover size, filename and Range support
        try:
            self.response = self._open_request(0)
        except Exception as e:
            return self._finish(f"Error: {e}")

        # Determine total size
        content_length = self.response.headers.get("content-length")
        if content_length and content_length.isdigit():
            self.total_size = int(content_length)
        else:
            self.total_size = 0

        # Check whether the server accepts Range (Accept-Ranges or 206)
        accept_ranges = self.response.headers.get("Accept-Ranges", "").lower()
        self._supports_range = accept_ranges == "bytes" or self.response.status_code == 206

        filename = self._resolve_filename(self.response)
        # Sanitize filename a bit
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        final_path = make_unique_path(self.save_folder / filename)
        self.part_path = final_path.with_suffix(final_path.suffix + ".part")
        self.save_path = final_path  # will be used after successful rename

        # If a previous .part exists from a crashed session, we could resume it,
        # but for simplicity we start fresh unless the user already paused.
        if self.part_path.exists():
            try:
                self.part_path.unlink()
            except Exception:
                pass

        self.downloaded_bytes = 0
        self._notify("Downloading...", 0)

        # Main download loop that can be interrupted by pause / cancel
        while not self.is_cancelled:
            # ---- Pause handling -------------------------------------------------
            if self.is_paused:
                self._notify("Paused", 0)
                # Wait until resume or cancel
                while self.is_paused and not self.is_cancelled:
                    time.sleep(0.2)
                if self.is_cancelled:
                    break
                # Coming out of pause: reopen connection with Range if possible
                if self._supports_range and self.downloaded_bytes > 0:
                    try:
                        self.response = self._open_request(self.downloaded_bytes)
                        # Server may return 206 Partial Content; adjust total if needed
                        if self.response.status_code == 206:
                            cl = self.response.headers.get("content-length")
                            if cl and cl.isdigit():
                                # remaining bytes; total stays the same
                                pass
                        else:
                            # Server ignored Range – restart from zero
                            self.downloaded_bytes = 0
                            if self.part_path.exists():
                                self.part_path.unlink(missing_ok=True)
                    except Exception as e:
                        return self._finish(f"Error on resume: {e}")
                else:
                    # No Range support – have to restart
                    try:
                        self.response = self._open_request(0)
                        self.downloaded_bytes = 0
                        if self.part_path.exists():
                            self.part_path.unlink(missing_ok=True)
                    except Exception as e:
                        return self._finish(f"Error on resume: {e}")

                # Reset speed timers after pause so the idle time is not counted
                last_time = time.time()
                last_bytes = self.downloaded_bytes
                self._notify("Downloading...", 0)

            # ---- Streaming ------------------------------------------------------
            mode = "ab" if self.downloaded_bytes > 0 else "wb"
            try:
                with open(self.part_path, mode) as file:
                    last_time = time.time()
                    last_bytes = self.downloaded_bytes

                    for chunk in self.response.iter_content(chunk_size=65536):
                        if self.is_cancelled:
                            break
                        if self.is_paused:
                            # Exit the for-loop; outer while will handle pause
                            break

                        if chunk:
                            file.write(chunk)
                            self.downloaded_bytes += len(chunk)
                            now = time.time()
                            if now - last_time >= 0.3:
                                speed = (self.downloaded_bytes - last_bytes) / (now - last_time)
                                self._notify("Downloading...", speed)
                                last_time = now
                                last_bytes = self.downloaded_bytes

                    # If we left because of pause, close response and continue outer loop
                    if self.is_paused and not self.is_cancelled:
                        if self.response:
                            try:
                                self.response.close()
                            except Exception:
                                pass
                            self.response = None
                        continue

                    # Normal end of stream
                    if not self.is_cancelled and not self.is_paused:
                        # Success – rename .part to final name
                        try:
                            self.part_path.rename(self.save_path)
                        except Exception as e:
                            return self._finish(f"Error renaming file: {e}")
                        return self._finish("Completed ✅")

            except Exception as e:
                if self.is_cancelled:
                    break
                if self.is_paused:
                    # Connection closed because of pause – expected
                    continue
                return self._finish(f"Error: {e}")

        # Cancelled path
        self._cleanup_part()
        return self._finish("Cancelled ❌")

    def _cleanup_part(self):
        """Remove the temporary .part file if it still exists."""
        if self.part_path and self.part_path.exists():
            try:
                self.part_path.unlink()
            except Exception:
                pass

    def _finish(self, status):
        """Mark the task finished, clean up and notify the UI."""
        self.is_running = False
        if self.response:
            try:
                self.response.close()
            except Exception:
                pass
            self.response = None

        # On any non-success status, discard the partial file
        if status != "Completed ✅":
            self._cleanup_part()

        self._notify(status, speed=0)


def start_download(url, root_win, update_callback, save_folder=None):
    """Create and start a DownloadTask. Returns the task object for control buttons."""
    if not is_valid_url(url):
        # Notify immediately so the card can show the error
        def bad_url_notify(data=None):
            update_callback({
                "status": "Error: invalid URL (must start with http:// or https://)",
                "progress": 0,
                "speed": "0 B/s",
                "downloaded_str": "0 B",
                "total_str": "Unknown",
                "error_detail": "Invalid URL",
                "save_path": None,
                "is_finished": True,
            })
        root_win.after(0, bad_url_notify)
        # Return a dummy task that does nothing
        class Dummy:
            def pause(self): pass
            def resume(self): pass
            def cancel(self): pass
        return Dummy()

    task = DownloadTask(url, root_win, update_callback, save_folder)
    task.start()
    return task
import os
import sys
import ctypes
import subprocess
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from logic import start_download, DEFAULT_SAVE_FOLDER, is_valid_url

# ============================================================
# Windows Optimization (DPI & Taskbar Icon)
# ============================================================
try:
    # Prevent the default Python icon from appearing in the taskbar
    myappid = "mycompany.minidownloader.app.2.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    # Fix blurry UI on high-DPI Windows displays
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def resource_path(relative_path):
    """Return the correct path for bundled resources after PyInstaller conversion."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Consistent icon filename (underscore, not hyphen)
ICON_NAME = "download_manager.ico"

# ============================================================
# Main Window Setup
# ============================================================
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

mainwin = ctk.CTk()
mainwin.title("Mini Download Manager")
mainwin.geometry("620x420")

mainwin.grid_columnconfigure(0, weight=1)
mainwin.grid_rowconfigure(2, weight=1)

ctk.CTkLabel(mainwin, text="📥 Mini Download Manager", font=("Arial", 26, "bold")).grid(
    row=0, column=0, columnspan=2, pady=20, sticky="ew"
)

downloads_frame = ctk.CTkScrollableFrame(mainwin, fg_color="#2d2d44")
downloads_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")

empty_label = ctk.CTkLabel(
    downloads_frame, text="📭 No downloads yet", font=("Arial", 14), text_color="gray"
)
empty_label.pack(pady=30)

ctk.CTkLabel(mainwin, text="Build 2.0", font=("Arial", 9), text_color="gray").grid(
    row=3, column=1, padx=10, pady=5, sticky="se"
)

# Keep track of active cards so we can restore the empty label when the last one is removed
active_cards = []


def _check_empty():
    """Show the empty-state label when no download cards remain."""
    if not active_cards and empty_label.winfo_exists():
        empty_label.pack(pady=30)


# ============================================================
# Download Card Component
# ============================================================
def create_download_card(url, save_folder=None):
    if empty_label.winfo_exists():
        empty_label.pack_forget()

    card = ctk.CTkFrame(downloads_frame, fg_color="#1e1e2e")
    card.pack(fill="x", padx=10, pady=5)
    active_cards.append(card)

    # Filename label (will be updated once the real name is known)
    name_label = ctk.CTkLabel(card, text="📄 ...", font=("Arial", 12, "bold"))
    name_label.pack(anchor="w", padx=10, pady=(5, 0))

    progress_bar = ctk.CTkProgressBar(card)
    progress_bar.set(0)
    progress_bar.pack(fill="x", padx=10, pady=5)

    # Separate labels help avoid mixed RTL/LTR rendering issues in tkinter
    status_label = ctk.CTkLabel(
        card, text="Connecting...", font=("Arial", 10), text_color="gray"
    )
    status_label.pack(anchor="w", padx=10)

    size_label = ctk.CTkLabel(
        card, text="0 B / Unknown", font=("Arial", 10), text_color="gray"
    )
    size_label.pack(anchor="w", padx=10)

    speed_label = ctk.CTkLabel(
        card, text="Speed: 0 B/s", font=("Arial", 10), text_color="gray"
    )
    speed_label.pack(anchor="w", padx=10, pady=(0, 5))

    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(fill="x", padx=10, pady=(0, 8))

    # Control buttons (visible while download is active)
    pause_btn = ctk.CTkButton(btn_frame, text="⏸ Pause", width=80)
    resume_btn = ctk.CTkButton(btn_frame, text="▶ Resume", width=80)
    cancel_btn = ctk.CTkButton(
        btn_frame, text="❌ Cancel", width=80, fg_color="#8B2E2E", hover_color="#A33A3A"
    )

    # Post-finish buttons (hidden until the task ends)
    open_folder_btn = ctk.CTkButton(btn_frame, text="📂 Open Folder", width=110)
    remove_btn = ctk.CTkButton(
        btn_frame, text="🗑 Remove", width=90, fg_color="#555555", hover_color="#777777"
    )

    pause_btn.pack(side="left", padx=(0, 5))
    resume_btn.pack(side="left", padx=5)
    cancel_btn.pack(side="left", padx=5)

    final_save_path = {"path": None}  # mutable container for the callback

    def update_card_ui(data):
        if not card.winfo_exists():
            return

        status = data.get("status", "")
        progress_bar.set(data.get("progress", 0))
        status_label.configure(text=status)
        size_label.configure(
            text=f"{data.get('downloaded_str', '0 B')} / {data.get('total_str', 'Unknown')}"
        )
        speed_label.configure(text=f"Speed: {data.get('speed', '0 B/s')}")

        # Update filename once we know the final path
        save_path = data.get("save_path")
        if save_path:
            final_save_path["path"] = save_path
            name_label.configure(text=f"📄 {os.path.basename(save_path)}")

        # When the task finishes (success, cancel or error) swap the buttons
        if data.get("is_finished"):
            for btn in (pause_btn, resume_btn, cancel_btn):
                if btn.winfo_exists():
                    btn.pack_forget()
            if open_folder_btn.winfo_exists() and not open_folder_btn.winfo_ismapped():
                open_folder_btn.pack(side="left", padx=(0, 5))
            if remove_btn.winfo_exists() and not remove_btn.winfo_ismapped():
                remove_btn.pack(side="left", padx=5)

    def remove_card():
        if card in active_cards:
            active_cards.remove(card)
        card.destroy()
        _check_empty()

    def open_folder():
        path = final_save_path["path"]
        folder = os.path.dirname(path) if path else str(DEFAULT_SAVE_FOLDER)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    open_folder_btn.configure(command=open_folder)
    remove_btn.configure(command=remove_card)

    task = start_download(url, mainwin, update_card_ui, save_folder=save_folder)

    pause_btn.configure(command=task.pause)
    resume_btn.configure(command=task.resume)
    cancel_btn.configure(command=task.cancel)


# ============================================================
# Add Download Window
# ============================================================
def open_add_url_window():
    add_win = ctk.CTkToplevel(mainwin)
    add_win.title("Add New Download")
    add_win.geometry("450x280")
    add_win.resizable(False, False)
    add_win.grab_set()

    # Force icon change for the Toplevel window on Windows
    try:
        add_win.update()  # ensure the window handle exists
        hwnd = ctypes.windll.user32.GetParent(add_win.winfo_id())
        icon_path = resource_path(ICON_NAME)

        hicon = ctypes.windll.user32.LoadImageW(
            0, icon_path, 1, 0, 0, 0x00000010 | 0x00000040
        )
        # WM_SETICON: 0 = small icon, 1 = large icon
        ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)
        ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)
    except Exception:
        pass

    ctk.CTkLabel(add_win, text="Enter file URL:", font=("Arial", 12)).pack(
        pady=(15, 5), padx=20, anchor="w"
    )

    url_entry = ctk.CTkEntry(add_win, placeholder_text="https://example.com/file.zip")
    url_entry.pack(pady=5, padx=20, fill="x")
    url_entry.focus_force()

    error_label = ctk.CTkLabel(add_win, text="", font=("Arial", 10), text_color="#FF6B6B")
    error_label.pack(pady=(0, 5), padx=20, anchor="w")

    ctk.CTkLabel(add_win, text="Save location:", font=("Arial", 12)).pack(
        pady=(5, 5), padx=20, anchor="w"
    )

    path_frame = ctk.CTkFrame(add_win, fg_color="transparent")
    path_frame.pack(fill="x", padx=20)
    path_frame.grid_columnconfigure(0, weight=1)

    selected_folder = tk.StringVar(value=str(DEFAULT_SAVE_FOLDER))

    path_entry = ctk.CTkEntry(path_frame, textvariable=selected_folder)
    path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

    def browse_folder():
        folder = filedialog.askdirectory(
            title="Select save folder",
            initialdir=selected_folder.get() or str(DEFAULT_SAVE_FOLDER),
        )
        if folder:
            selected_folder.set(folder)
        if add_win.winfo_exists():
            add_win.lift()
            add_win.focus_force()

    ctk.CTkButton(path_frame, text="📁 Browse", width=90, command=browse_folder).grid(
        row=0, column=1
    )

    # Clipboard helpers
    def paste_from_clipboard(event=None):
        try:
            url_entry.insert(ctk.END, add_win.clipboard_get())
        except Exception:
            pass
        return "break"

    def copy_to_clipboard(event=None):
        try:
            add_win.clipboard_clear()
            add_win.clipboard_append(url_entry.selection_get())
        except Exception:
            pass

    def select_all(event=None):
        url_entry.select_range(0, ctk.END)
        url_entry.icursor(ctk.END)
        return "break"

    context_menu = tk.Menu(add_win, tearoff=0)
    context_menu.add_command(label="Paste", command=paste_from_clipboard)
    context_menu.add_command(label="Copy", command=copy_to_clipboard)
    context_menu.add_separator()
    context_menu.add_command(label="Select All", command=select_all)

    url_entry.bind("<Button-3>", lambda e: context_menu.tk_popup(e.x_root, e.y_root))
    for key in ("<Control-v>", "<Control-V>"):
        url_entry.bind(key, paste_from_clipboard)
    for key in ("<Control-a>", "<Control-A>"):
        url_entry.bind(key, select_all)

    def start_action(event=None):
        url = url_entry.get().strip()
        if not url:
            error_label.configure(text="Please enter a URL.")
            return
        if not is_valid_url(url):
            error_label.configure(text="URL must start with http:// or https://")
            return
        error_label.configure(text="")
        create_download_card(url, save_folder=selected_folder.get())
        add_win.grab_release()
        add_win.destroy()

    add_win.bind("<Return>", start_action)
    ctk.CTkButton(
        add_win, text="Start Download", fg_color="#2E8B57", command=start_action
    ).pack(pady=15)


# Button to open the Add-URL dialog
ctk.CTkButton(
    mainwin,
    text="➕ Add Download",
    fg_color="#2E8B57",
    height=40,
    width=130,
    command=open_add_url_window,
).grid(row=1, column=1, padx=(5, 20), pady=10, sticky="e")

# Safe icon assignment using the consistent filename
try:
    mainwin.after(100, lambda: mainwin.iconbitmap(resource_path(ICON_NAME)))
except Exception:
    pass

mainwin.mainloop()
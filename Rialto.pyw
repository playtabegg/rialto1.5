# RIALTO FULL VERSION
# Master .pyw file begins below
# Includes: UI, Automation, Validation, ISO, Bonus Gallery, Batch, Live Preview

import os
import sys
import json
import shutil
import subprocess
import traceback
import glob
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from PIL import Image, ImageTk
import webbrowser
import winsound  # For WAV playback on Windows
import random
import string
import time
import datetime
import platform
import urllib.request





# === LEGACY TEMPLATE SYSTEM REMOVED ===
# Now using direct menu generation via create_pyqt5_menu_launcher()




APP_NAME = "Rialto"
CONFIG_FILE = "config.json"
INPUT_DIR = "input"
OUTPUT_DIR = "output"
REQUIRED_TOOLS = ["AutoIt3.exe", "ISCC.exe"]
ISO_TOOLS = ["mkisofs.exe", "oscdimg.exe"]
LAST_PROFILE_FILE = "last_profile.json"

# Helper: Safe path for Windows
safe = lambda p: os.path.normpath(os.path.abspath(p))

def asset_path(filename):
    """Resolve path to a bundled asset file."""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'assets', filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', filename)

# Ensure folders exist
def ensure_structure():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)


class ToolTip:
    def __init__(self, widget, text, bg=None, fg=None):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        if event:
            x = event.x_root + 15
            y = event.y_root + 10
        else:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tip_bg = self.bg or "#2d2d2d"
        tip_fg = self.fg or "#e0e0e0"
        label = tk.Label(tw, text=self.text, justify='left',
                         background=tip_bg, foreground=tip_fg,
                         relief='solid', borderwidth=1,
                         font=("Segoe UI", 10),
                         wraplength=320)
        label.pack(ipadx=4, ipady=2)

    def hide(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()




# GUI class begins
class RialtoApp:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        self.root.title(f"{APP_NAME} - Disc Builder")
        
        # Set favicon for main window
        try:
            icon_path = asset_path("bird_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass
        



        self.root.overrideredirect(True)  # Hide native title bar

        self.root.geometry("650x1040")
        self.current_game_path = None

        default_font = ("Segoe UI", 10)
        self.root.option_add("*Font", default_font)

        self.dark_theme = {
            "bg": "#222222",
            "fg": "#ffffff",
            "entry_bg": "#333333",
            "button_bg": "#444444",
            "button_fg": "#ffffff",
            "button_active": "#555555",
            "disabled_fg": "#888888",
        }
        self.light_theme = {
            "bg": "#f0f0f0",
            "fg": "#000000",
            "entry_bg": "#ffffff",
            "button_bg": "#e0e0e0",
            "button_fg": "#000000",
            "button_active": "#d0d0d0",
            "disabled_fg": "#a0a0a0",
        }

        # UI Elements
        self.theme_mode = tk.StringVar(value="dark")  # Default is dark mode
        
        # Code Signing settings
        self.sign_final_build = tk.BooleanVar(value=False)
        self.remove_wti_branding = tk.BooleanVar(value=False)
        self.create_widgets()
        self.load_last_session()
        self.load_config()
        self.load_last_used_profile()







    def show_centered_popup(self, title, message, kind="info"):
        """Enhanced popup with yes/no support"""
        theme_colors = self.dark_theme if self.theme_mode.get() == "dark" else self.light_theme

        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.configure(bg=theme_colors["bg"])
        popup.geometry("360x180")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        # Optional icon for consistency
        icon_path = asset_path("bird_icon.ico")
        if os.path.exists(icon_path):
            popup.iconbitmap(icon_path)

        # Center the popup relative to the main window
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 180
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 110
        popup.geometry(f"+{x}+{y}")

        ttk.Label(
            popup, 
            text=message, 
            wraplength=280, 
            justify="center",
            background=theme_colors["bg"], 
            foreground=theme_colors["fg"]
        ).pack(pady=20)

        result = [False]

        if kind == "yesno":
            button_frame = tk.Frame(popup, bg=theme_colors["bg"])
            button_frame.pack(pady=5)
            
            def yes_clicked():
                result[0] = True
                popup.destroy()
            
            def no_clicked():
                result[0] = False
                popup.destroy()
            
            tk.Button(
                button_frame, 
                text="Yes", 
                command=yes_clicked,
                bg=theme_colors["button_bg"], 
                fg=theme_colors["button_fg"],
                padx=20, pady=6
            ).pack(side="left", padx=10)
            
            tk.Button(
                button_frame, 
                text="No", 
                command=no_clicked,
                bg=theme_colors["button_bg"], 
                fg=theme_colors["button_fg"],
                padx=20, pady=6
            ).pack(side="left", padx=10)
        else:
            tk.Button(
                popup, 
                text="OK", 
                command=popup.destroy,
                bg=theme_colors["button_bg"], 
                fg=theme_colors["button_fg"],
                padx=14, pady=6
            ).pack(pady=5)

        self.root.wait_window(popup)
        return result[0] if kind == "yesno" else None







    def on_exit(self):
        self.save_last_session()
        self.root.destroy()




    def load_last_used_profile(self):
        if not os.path.exists(LAST_PROFILE_FILE):
            return

        try:
            with open(LAST_PROFILE_FILE, "r", encoding="utf-8") as f:
                last_data = json.load(f)
                profile_name = last_data.get("last_profile")
                if not profile_name:
                    return

                profile_path = os.path.join(os.getcwd(), profile_name)
                if not os.path.exists(profile_path):
                    return

                with open(profile_path, "r", encoding="utf-8") as pf:
                    profile_data = json.load(pf)
                    for k, v in profile_data.items():
                        if k in self.entries:
                            self.entries[k].delete(0, tk.END)
                            self.entries[k].insert(0, v)
                    self.bg_path_var.set(profile_data.get("Background", ""))
                    self.ico_path_var.set(profile_data.get("Icon", ""))
                    self.disc_icon_var.set(profile_data.get("DiscIcon", ""))
                    self.disc_name_var.set(profile_data.get("DiscName", ""))


                self.update_status(f"✅ Restored session from {profile_name}")

        except Exception as e:
            self.update_status(f"[!] Failed to load last session: {e}")









    def create_widgets(self):
        # Custom Title Bar
        self.title_bar = tk.Frame(self.root, bg=self.dark_theme["bg"], relief="raised", bd=0, height=30)
        self.title_bar.pack(fill="x")


        try:
            icon_path = asset_path("bird_icon.ico")
            icon_img = Image.open(icon_path).convert("RGBA").resize((16, 16), Image.LANCZOS)
            self.toolbar_icon = ImageTk.PhotoImage(icon_img)
            icon_label = tk.Label(self.title_bar, image=self.toolbar_icon, bg=self.dark_theme["bg"])
            icon_label.pack(side="left", padx=6)
        except Exception:
            pass


        self.title_label = tk.Label(self.title_bar, text="Rialto – Disc Builder", bg=self.dark_theme["bg"], fg=self.dark_theme["fg"], font=("Segoe UI", 10, "bold"))
        self.title_label.pack(side="left", padx=10)

        # Close Button
        self.close_btn = tk.Button(
            self.title_bar, text="X",
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            command=self.root.destroy
        )
        self.close_btn.pack(side="right", padx=(2, 8))
        ToolTip(self.close_btn, "Close")

        # Minimize Button (fixed)
        self.minimize_btn = tk.Button(
            self.title_bar, text="–",
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            command=self.minimize_window
        )
        self.minimize_btn.pack(side="right", padx=(0, 2))
        ToolTip(self.minimize_btn, "Minimize")

        # Enable drag
        self.title_bar.bind("<B1-Motion>", self._move_window)
        self.title_bar.bind("<Button-1>", self._click_window)

        # Main content container (everything below title bar)
        self.main_content = tk.Frame(self.root, bg=self.dark_theme["bg"])
        self.main_content.pack(fill="both", expand=True)

        frame = ttk.Frame(self.main_content)
        style = ttk.Style()
        style.theme_use('default')  # Ensures consistency across platforms

        # Set global font and padding
        default_font = ("Segoe UI", 10)
        self.root.option_add("*Font", default_font)
        self.root.option_add("*Label.Padding", 2)
        self.root.option_add("*Entry.Padding", 2)
        self.root.option_add("*Button.Padding", 4)


        style.configure("TButton",
            background="#e0e0e0",
            foreground="#000000",
            borderwidth=1,
            focusthickness=3,
            focuscolor="none",
            padding=(8, 4)
        )

        style.map("TButton",
            background=[('active', '#d0d0d0')],
            foreground=[('disabled', '#a0a0a0')],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')]
        )
        style.configure("Rounded.TButton",
            background="#e0e0e0",
            foreground="#000000",
            borderwidth=1,
            focusthickness=0,
            padding=6,
            relief="flat"
        )



        # Tutorial / Welcome Text Box
        tutorial_text = (
            "Welcome to Rialto – your disc-based installer builder for indie games!\n\n"
            "🎮 GAME DISC CREATION:\n"
            "📁 Input Format: Each game should be in its own folder inside the 'input' directory.\n"
            "🎨 Menu Background: JPG (1280x720), GIF (animated, recommended!), or video (MP4/AVI/MOV, 720p).\n"
            "🖼 Icon.ico: 256x256 recommended. Convert PNG to ICO with an online tool (e.g., icoconvert.com).\n"
            "🎁 Bonus Content: Place anything into a /bonus folder inside the game folder.\n"
        )
        self.tutorial_box = tk.Message(frame, text=tutorial_text, width=760, relief="groove", font=("Segoe UI", 10))
        self.tutorial_box.pack(pady=(0, 10), fill="x")
        frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))


        self.game_label = ttk.Label(frame, text="Select Game Folder:")
        self.game_label.pack(anchor="w")

        select_btn = ttk.Button(frame, text="Browse Input Folder", command=self.select_game_folder, style="Rounded.TButton")
        select_btn.pack(anchor="w", pady=5)

        self.meta_frame = ttk.LabelFrame(frame, text="Metadata")
        self.meta_frame.pack(fill="x", pady=10)





        self.entries = {}

        # Essential metadata fields with display label mapping
        essential_fields = ["Title", "Developer", "Start Menu Name"]
        display_labels = {"Title": "Game Title", "Developer": "Developer", "Start Menu Name": "Start Menu Name"}

        for key in essential_fields:
            row = ttk.Frame(self.meta_frame)
            row.pack(fill="x", padx=4, pady=4)
            ttk.Label(row, text=display_labels[key] + ":", width=20).pack(side="left", padx=(0, 4), pady=2)
            entry = ttk.Entry(row)
            entry.pack(fill="x", expand=True, padx=4, pady=2)
            self.entries[key] = entry

            if key == "Title":
                ToolTip(entry, "Your game's title. This is what players see in the installer and disc menu.")
            elif key == "Developer":
                ToolTip(entry, "Who made the game \u2014 your name, studio, or team name.")
            elif key == "Start Menu Name":
                ToolTip(entry, "The name players see in their Windows Start Menu. Fills in automatically from Game Title, but you can change it.")

        # Copyright Text (inside Metadata frame, auto-populated from Developer)
        copyright_row = ttk.Frame(self.meta_frame)
        copyright_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(copyright_row, text="Copyright Text:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.publisher_text_var = tk.StringVar()
        publisher_entry = ttk.Entry(copyright_row, textvariable=self.publisher_text_var)
        publisher_entry.pack(fill="x", expand=True, padx=4, pady=2)
        ToolTip(publisher_entry, "A copyright line for your installer, like '\u00a9 2025 Your Name.' Fills in from Developer \u2014 edit anytime.")

        # Disc Name (inside Metadata frame, auto-populated from Game Title)
        disc_name_row = ttk.Frame(self.meta_frame)
        disc_name_row.pack(fill="x", padx=4, pady=4)
        ttk.Label(disc_name_row, text="Disc Name:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.disc_name_var = tk.StringVar()
        self.disc_label_entry = ttk.Entry(disc_name_row, textvariable=self.disc_name_var)
        self.disc_label_entry.pack(fill="x", expand=True, padx=4, pady=2)
        ToolTip(self.disc_label_entry, "The label players see in File Explorer when the disc is inserted, like a DVD name. Fills in from Game Title.")

        # Auto-populate tracking flags
        self._auto_start_menu = True
        self._auto_disc_name = True
        self._auto_copyright = True
        self._auto_disc_icon = True

        # StringVar traces for auto-populate
        self._title_var = tk.StringVar()
        self.entries["Title"].configure(textvariable=self._title_var)
        self._developer_var = tk.StringVar()
        self.entries["Developer"].configure(textvariable=self._developer_var)

        def _on_title_changed(*args):
            title = self._title_var.get()
            if self._auto_start_menu:
                self.entries["Start Menu Name"].delete(0, tk.END)
                self.entries["Start Menu Name"].insert(0, title)
            if self._auto_disc_name:
                self.disc_name_var.set(title)

        def _on_developer_changed(*args):
            dev = self._developer_var.get()
            if self._auto_copyright and dev.strip():
                year = datetime.datetime.now().year
                self.publisher_text_var.set(f"\u00a9 {year} {dev}. All rights reserved.")
            elif self._auto_copyright:
                self.publisher_text_var.set("")

        self._title_var.trace_add("write", _on_title_changed)
        self._developer_var.trace_add("write", _on_developer_changed)

        # Manual edit detection — stop auto-populating when user types directly
        def _on_start_menu_key(event):
            self._auto_start_menu = False
        self.entries["Start Menu Name"].bind("<Key>", _on_start_menu_key)

        def _on_copyright_key(event):
            self._auto_copyright = False
        publisher_entry.bind("<Key>", _on_copyright_key)

        def _on_disc_name_key(event):
            self._auto_disc_name = False
        self.disc_label_entry.bind("<Key>", _on_disc_name_key)







        # background jpg/video
        img_row = ttk.Frame(frame)
        img_row.pack(fill="x", pady=5)
        ttk.Label(img_row, text="Menu Background:", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.bg_path_var = tk.StringVar()
        bg_entry = ttk.Entry(img_row, textvariable=self.bg_path_var)
        bg_entry.pack(side="left", fill="x", expand=True)
        bg_browse = ttk.Button(img_row, text="Browse", command=self.browse_bg, style="Rounded.TButton")
        bg_browse.pack(side="left", padx=(0, 4), pady=2)
        bg_tip = "The background image or video for your disc's game launcher menu. Supports JPG (1280x720), animated GIF, or video (MP4, AVI, MOV). GIFs are recommended \u2014 you can make them from video at ezgif.com."
        ToolTip(img_row, bg_tip)
        ToolTip(bg_entry, bg_tip)
        ToolTip(bg_browse, "Pick a background image, GIF, or video from your files.")


        # game logo (NEW - add this before game icon)
        logo_row = ttk.Frame(frame)
        logo_row.pack(fill="x", pady=5)
        ttk.Label(logo_row, text="Game Logo (.png):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.logo_path_var = tk.StringVar()
        logo_entry = ttk.Entry(logo_row, textvariable=self.logo_path_var)
        logo_entry.pack(side="left", fill="x", expand=True)
        logo_browse = ttk.Button(logo_row, text="Browse", command=self.browse_logo, style="Rounded.TButton")
        logo_browse.pack(side="left", padx=(0, 4), pady=2)
        logo_tip = "Your game's logo, shown front-and-center on the disc menu. Use a PNG with a transparent background, ideally 400x150 pixels or smaller."
        ToolTip(logo_row, logo_tip)
        ToolTip(logo_entry, logo_tip)
        ToolTip(logo_browse, "Pick your game logo image (PNG).")

        # company logo (NEW - for bottom left of menu)
        company_logo_row = ttk.Frame(frame)
        company_logo_row.pack(fill="x", pady=5)
        ttk.Label(company_logo_row, text="Company Logo (.png):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.company_logo_var = tk.StringVar()
        cl_entry = ttk.Entry(company_logo_row, textvariable=self.company_logo_var)
        cl_entry.pack(side="left", fill="x", expand=True)
        cl_browse = ttk.Button(company_logo_row, text="Browse", command=self.browse_company_logo, style="Rounded.TButton")
        cl_browse.pack(side="left", padx=(0, 4), pady=2)
        cl_tip = "Your studio or company logo, shown in the bottom-right of the disc menu. Use a small transparent PNG, around 150x75 pixels."
        ToolTip(company_logo_row, cl_tip)
        ToolTip(cl_entry, cl_tip)
        ToolTip(cl_browse, "Pick your company or studio logo (PNG).")

        # game icon
        ico_row = ttk.Frame(frame)
        ico_row.pack(fill="x", pady=5)
        ttk.Label(ico_row, text="Game Icon (.ico):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.ico_path_var = tk.StringVar()
        ico_entry = ttk.Entry(ico_row, textvariable=self.ico_path_var)
        ico_entry.pack(side="left", fill="x", expand=True)
        ico_browse = ttk.Button(ico_row, text="Browse", command=self.browse_ico, style="Rounded.TButton")
        ico_browse.pack(side="left", padx=(0, 4), pady=2)
        ico_tip = "The icon for your installer and desktop shortcut \u2014 the small image players see in their Start Menu and taskbar. Needs to be a 256x256 .ico file. You can convert a PNG at icoconvert.com. Also fills in Disc Icon below."
        ToolTip(ico_row, ico_tip)
        ToolTip(ico_entry, ico_tip)
        ToolTip(ico_browse, "Pick your game's icon file (.ico format).")


        # disc icon
        disc_icon_row = ttk.Frame(frame)
        disc_icon_row.pack(fill="x", pady=5)
        ttk.Label(disc_icon_row, text="Disc Icon (.ico):", width=20).pack(side="left", padx=(0, 4), pady=2)
        self.disc_icon_var = tk.StringVar()
        di_entry = ttk.Entry(disc_icon_row, textvariable=self.disc_icon_var)
        di_entry.pack(side="left", fill="x", expand=True)
        di_browse = ttk.Button(disc_icon_row, text="Browse", command=self.browse_disc_icon, style="Rounded.TButton")
        di_browse.pack(side="left", padx=(0, 4), pady=2)
        di_tip = "The icon shown in File Explorer when the disc is inserted \u2014 like the small picture on a DVD drive. Must be .ico format. Fills in automatically from Game Icon above."
        ToolTip(disc_icon_row, di_tip)
        ToolTip(di_entry, di_tip)
        ToolTip(di_browse, "Pick a disc icon file (.ico format).")









        # Live status box
        self.status_text = tk.Text(frame, height=6, wrap="word", state="disabled", bg="#1e1e1e", fg="#00FF00", font=("Segoe UI", 10))
        self.status_text.pack(fill="both", expand=True, padx=2, pady=(10, 0))
        self.status_text.tag_config("success", foreground="#00FF00")
        self.status_text.tag_config("error", foreground="#FF0000")
        self.status_text.tag_config("warning", foreground="#FFA500")
        self.status_text.tag_config("processing", foreground="#00FFFF")
        self.status_text.tag_config("signing", foreground="#FF00FF")
        self.status_text.tag_config("burn", foreground="#FF8C00")
        self.status_text.tag_config("disc", foreground="#87CEEB")

        self.update_status("Ready.")





        # === Tool Groups Container (centered at bottom under status) ===
        self.tool_groups_container = tk.Frame(self.main_content, bg=self.dark_theme["bg"])
        self.tool_groups_container.pack(side="bottom", pady=(10, 20))  # Tucks it nicely at bottom

        # --- Build ---
        self.build_wrapper = tk.Frame(self.tool_groups_container, bd=1, relief="ridge", bg=self.dark_theme["bg"])
        self.build_wrapper.pack(side="left", padx=6)

        self.build_tools_frame = ttk.LabelFrame(self.build_wrapper, text="Build")
        self.build_tools_frame.pack(fill="both", expand=True, padx=2, pady=2)

        build_btn = ttk.Button(self.build_tools_frame, text="Build Game Installer",
                              command=self.run_build_process, style="Rounded.TButton")
        build_btn.pack(pady=2, fill="x")
        ToolTip(build_btn, "Build your game disc! Creates the installer, game launcher menu, and final disc image all in one step.")

        final_check = ttk.Checkbutton(self.build_tools_frame, text="Sign Final Build",
                                     variable=self.sign_final_build, command=self.save_signing_settings)
        final_check.pack(anchor="w", padx=(8, 4), pady=(4, 6))
        ToolTip(final_check, "Pause the build after creating your installer so you can digitally sign it. Signing tells Windows the file is safe and removes 'Unknown Publisher' warnings. Requires a paid certificate from a service like SSL.com (esigner.com).")

        branding_check = ttk.Checkbutton(self.build_tools_frame, text="Remove WTI Branding",
                                         variable=self.remove_wti_branding, command=self.save_signing_settings)
        branding_check.pack(anchor="w", padx=(8, 4), pady=(0, 6))
        ToolTip(branding_check, "Complimentary white label for your game. Removes the We the Indies bird logo and branding from your game's disc menu.")

        # --- Tools ---
        self.file_wrapper = tk.Frame(self.tool_groups_container, bd=1, relief="ridge", bg=self.dark_theme["bg"])
        self.file_wrapper.pack(side="left", padx=6)

        self.file_tools_frame = ttk.LabelFrame(self.file_wrapper, text="Tools")
        self.file_tools_frame.pack(fill="both", expand=True, padx=2, pady=2)

        save_btn = ttk.Button(self.file_tools_frame, text="💾 Save Profile", command=self.save_profile, style="Rounded.TButton")
        save_btn.pack(pady=2, fill="x")
        ToolTip(save_btn, "Save all your current settings to a file so you can reload them later \u2014 handy when you build the same game often.")

        load_btn = ttk.Button(self.file_tools_frame, text="📂 Load Profile", command=self.load_profile, style="Rounded.TButton")
        load_btn.pack(pady=2, fill="x")
        ToolTip(load_btn, "Load previously saved settings so you don't have to fill everything in again.")

        self.apply_dark_theme()



        def toggle_theme():
            style = ttk.Style()
            style.theme_use('default')
            style.configure(".", background="", foreground="")  # Clear inherited ttk styling

            new_mode = "light" if self.theme_mode.get() == "dark" else "dark"
            self.theme_mode.set(new_mode)

            # Apply the corresponding theme
            if new_mode == "dark":
                self.apply_dark_theme()
            else:
                self.apply_light_theme()

            # Force refresh of all widgets
            theme_colors = self.dark_theme if new_mode == "dark" else self.light_theme

            # Force all top-level frames and containers to update bg
            for frame in [self.root, self.tool_groups_container, self.file_tools_frame, self.build_tools_frame]:
                try:
                    frame.configure(bg=theme_colors["bg"])
                except tk.TclError:
                    pass

            self._force_theme_refresh(theme_colors)


        toggle_btn = ttk.Button(self.file_tools_frame, text="🌓 Toggle Theme", command=toggle_theme, style="Toggle.TButton")
        toggle_btn.pack(pady=2, fill="x")
        ToolTip(toggle_btn, "Switch between dark and light mode.")

        help_btn = ttk.Button(self.file_tools_frame, text="Help Guide", command=self.open_help_guide, style="Rounded.TButton")
        help_btn.pack(pady=2, fill="x")
        ToolTip(help_btn, "Open the Rialto help guide and documentation.")







    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {}
        
        # Load signing settings
        self.sign_final_build.set(self.config.get("sign_final_build", False))
        self.remove_wti_branding.set(self.config.get("remove_wti_branding", False))

    def open_help_guide(self):
        """Open the README help guide"""
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        ]
        if getattr(sys, 'frozen', False):
            candidates.insert(0, os.path.join(os.path.dirname(sys.executable), "README.md"))

        for readme_path in candidates:
            if os.path.exists(readme_path):
                try:
                    os.startfile(readme_path)
                    self.update_status("📖 Opened help guide")
                    return
                except Exception as e:
                    self.update_status(f"⚠️ Could not open help guide: {e}")
                    return

        self.update_status("⚠️ README.md not found")

    def save_profile(self):
        """Save profile data"""
        # Only save the essential fields (cleaned up)
        profile_data = {k: entry.get() for k, entry in self.entries.items()}
        
        # Add the additional settings
        profile_data["Background"] = self.bg_path_var.get()
        profile_data["Logo"] = self.logo_path_var.get()
        profile_data["CompanyLogo"] = self.company_logo_var.get()  # NEW
        profile_data["PublisherText"] = self.publisher_text_var.get()  # NEW
        profile_data["Icon"] = self.ico_path_var.get()
        profile_data["DiscIcon"] = self.disc_icon_var.get()
        profile_data["DiscName"] = self.disc_name_var.get()
        profile_data["RemoveWTIBranding"] = self.remove_wti_branding.get()

        # Add metadata for profile version (for future compatibility)
        profile_data["_ProfileVersion"] = "2.2"
        profile_data["_CreatedBy"] = "Rialto Enhanced"

        # Default to templates folder
        templates_dir = os.path.join(os.getcwd(), "templates")
        os.makedirs(templates_dir, exist_ok=True)

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json", 
            filetypes=[("JSON Files", "*.json")],
            title="Save Rialto Profile",
            initialdir=templates_dir
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(profile_data, f, indent=4)
                self.update_status(f"✅ Profile saved: {os.path.basename(file_path)}")
            except Exception as e:
                self.update_status(f"❌ Failed to save profile: {e}")

    def load_profile(self):
        """Load profile data"""

        # Default to templates folder
        templates_dir = os.path.join(os.getcwd(), "templates")
        os.makedirs(templates_dir, exist_ok=True)

        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="Load Rialto Profile",
            initialdir=templates_dir
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    profile_data = json.load(f)
                
                # Load the essential fields
                for k, v in profile_data.items():
                    if k in self.entries:
                        self.entries[k].delete(0, tk.END)
                        self.entries[k].insert(0, v)
                
                # Load additional settings
                self.bg_path_var.set(profile_data.get("Background", ""))
                self.logo_path_var.set(profile_data.get("Logo", ""))
                self.company_logo_var.set(profile_data.get("CompanyLogo", ""))  # NEW
                self.publisher_text_var.set(profile_data.get("PublisherText", ""))  # NEW
                self.ico_path_var.set(profile_data.get("Icon", ""))
                self.disc_icon_var.set(profile_data.get("DiscIcon", ""))
                self.disc_name_var.set(profile_data.get("DiscName", ""))
                self.remove_wti_branding.set(profile_data.get("RemoveWTIBranding", False))

                # Check profile version
                profile_version = profile_data.get("_ProfileVersion", "1.0")
                self.update_status(f"✅ Profile loaded: {os.path.basename(file_path)} (v{profile_version})")
                
                # Save as last used profile
                profile_name = Path(file_path).name
                with open(LAST_PROFILE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"last_profile": profile_name}, f)
                    
            except Exception as e:
                self.update_status(f"❌ Failed to load profile: {e}")






    def save_last_session(self):
        """Save current session"""
        session_data = {
            "last_used_game": self.current_game_path,
            "theme_mode": self.theme_mode.get()
        }

        # Save essential fields only
        for key, entry in self.entries.items():
            session_data[key] = entry.get()

        # Save additional settings
        session_data["Background"] = self.bg_path_var.get()
        session_data["Logo"] = self.logo_path_var.get()  # NEW
        session_data["Icon"] = self.ico_path_var.get()
        session_data["DiscIcon"] = self.disc_icon_var.get()
        session_data["DiscName"] = self.disc_name_var.get()

        try:
            with open("last_session.json", "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=4)
        except Exception:
            pass

    def load_last_session(self):
        """Load previous session"""
        try:
            if os.path.exists("last_session.json"):
                with open("last_session.json", "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Load theme
                theme = data.get("theme_mode", "dark")
                self.theme_mode.set(theme)
                if theme == "dark":
                    self.apply_dark_theme()
                else:
                    self.apply_light_theme()

                # Load essential fields
                for key, value in data.items():
                    if key in self.entries:
                        self.entries[key].delete(0, tk.END)
                        self.entries[key].insert(0, value)
                    elif key == "Background":
                        self.bg_path_var.set(value)
                    elif key == "Logo":
                        self.logo_path_var.set(value)  # NEW
                    elif key == "Icon":
                        self.ico_path_var.set(value)
                    elif key == "DiscIcon":
                        self.disc_icon_var.set(value)
                    elif key == "DiscName":
                        self.disc_name_var.set(value)
                        
        except Exception:
            pass





    def _apply_theme(self, theme_colors, status_bg=None, status_fg=None, labelframe_label_bg=None):
        """Shared theme application logic for both dark and light modes"""
        bg = theme_colors["bg"]
        fg = theme_colors["fg"]
        entry_bg = theme_colors["entry_bg"]
        button_bg = theme_colors["button_bg"]
        button_fg = theme_colors["button_fg"]
        button_active = theme_colors["button_active"]
        disabled_fg = theme_colors["disabled_fg"]
        frame_bg = bg

        # Apply to title bar
        self.title_bar.configure(bg=bg)
        self.title_label.configure(bg=bg, fg=fg)
        self.close_btn.configure(bg=bg, fg=fg)
        self.minimize_btn.configure(bg=bg, fg=fg)

        # Apply to manually colored frames
        self.main_content.configure(bg=bg)
        self.tool_groups_container.configure(bg=bg)
        self.build_wrapper.configure(bg=bg)
        self.file_wrapper.configure(bg=bg)

        self.status_text.configure(bg=bg, fg=status_fg or fg)

        style = ttk.Style()
        style.theme_use('default')

        self.root.configure(bg=bg)

        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelFrame", background=bg, foreground=fg)
        style.configure("TLabelFrame.Label", background=labelframe_label_bg or bg, foreground=fg)
        style.configure("TMenubutton", background=bg, foreground=fg)
        style.configure("Toggle.TButton", background=button_bg, foreground=fg)
        style.configure("Popup.TButton",
            background=button_bg,
            foreground=button_fg,
            padding=(14, 6),
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )

        style.configure("TLabelframe",
            background=frame_bg,
            borderwidth=1,
            relief="groove"
        )
        style.configure("TLabelframe.Label",
            background=frame_bg,
            foreground=fg,
            font=("Segoe UI", 9, "bold")
        )

        style.configure("TEntry",
            fieldbackground=entry_bg,
            foreground=fg)

        style.configure("TButton",
            background=button_bg,
            foreground=button_fg,
            borderwidth=1,
            focusthickness=1,
            focuscolor=frame_bg,
            relief="flat"
        )

        style.map("TButton",
            background=[('active', button_active)],
            foreground=[('disabled', disabled_fg)]
        )

        style.configure("TMenubutton",
            background=button_bg,
            foreground=button_fg,
            arrowcolor=button_fg,
            borderwidth=1
        )

        style.map("TMenubutton",
            background=[("active", button_active)],
            foreground=[("disabled", disabled_fg)],
            arrowcolor=[("active", button_fg)]
        )

        style.configure("Rounded.TButton",
            background=button_bg,
            foreground=button_fg,
            borderwidth=1,
            focusthickness=0,
            padding=6,
            relief="flat"
        )
        style.map("Rounded.TButton",
            background=[('active', button_active)],
            foreground=[('disabled', disabled_fg)],
            relief=[('pressed', 'flat'), ('!pressed', 'flat')]
        )

        style.configure("TCheckbutton",
            background=bg,
            foreground=fg,
            indicatorbackground=entry_bg,
            indicatorforeground=fg,
            focuscolor=bg
        )
        style.map("TCheckbutton",
            background=[("active", bg)],
            foreground=[("active", fg)],
            indicatorbackground=[("selected", button_active), ("active", entry_bg)]
        )

        style.map("Popup.TButton",
            background=[("active", button_active)],
            foreground=[("disabled", disabled_fg)]
        )

        if status_bg:
            self.status_text.configure(bg=status_bg, fg=status_fg or fg)

        self._update_all_widgets_recursive(self.root, bg=bg, fg=fg)
        self._force_theme_refresh(theme_colors)

    def apply_dark_theme(self):
        self._apply_theme(self.dark_theme, status_bg="#111111", status_fg="#00FF00", labelframe_label_bg="#1e1e1e")





    def apply_light_theme(self):
        self._apply_theme(self.light_theme, status_bg="#f5f5f5", status_fg="#1a6b1a", labelframe_label_bg="#e8e8e8")







    def _update_button_colors(self, widget, bg, fg):
        try:
            widget_type = widget.winfo_class()
            if widget_type in ["Button", "TButton", "Menubutton"]:
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Frame" or widget_type == "LabelFrame":
                widget.configure(background=bg)
            elif widget_type == "Label":
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Entry":
                widget.configure(background=bg, foreground=fg)
            elif widget_type == "Text":
                widget.configure(bg=bg, fg=fg)
            elif widget_type == "TMenubutton":
                widget.configure(background=bg, foreground=fg)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._update_button_colors(child, bg, fg)




    def _update_misc_widget_colors(self, widget, bg, fg):
        # Apply styles to tk.Button and OptionMenu menu elements
        if isinstance(widget, tk.Button):
            widget.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
        elif isinstance(widget, tk.OptionMenu):
            widget.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
            menu = widget["menu"]
            menu.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)




    def _force_theme_refresh(self, theme_colors):
        """Ensures all visible widgets follow the active theme."""
        bg = theme_colors["bg"]
        fg = theme_colors["fg"]

        try:
            self.status_text.configure(bg=bg, fg=fg)
        except (tk.TclError, AttributeError):
            pass

        try:
            self.tutorial_box.configure(bg=bg, fg=fg)
        except (tk.TclError, AttributeError):
            pass

        try:
            self.title_bar.configure(bg=bg)
        except (tk.TclError, AttributeError):
            pass

        try:
            self.tool_groups_container.configure(bg=bg)
        except (tk.TclError, AttributeError):
            pass

        self._update_all_widgets_recursive(self.root, bg=bg, fg=fg)





    def _update_all_widgets_recursive(self, parent, bg, fg):
        for widget in parent.winfo_children():
            try:
                widget_type = widget.winfo_class()
                if widget_type in ["TButton", "TEntry", "TLabel", "TFrame", "TLabelFrame"]:
                    widget.configure(style="")  # Reset any previously applied style
                elif isinstance(widget, tk.Button) or isinstance(widget, tk.Label):
                    widget.configure(bg=bg, fg=fg)
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=bg, fg=fg, insertbackground=fg)
                elif isinstance(widget, tk.Text):
                    widget.configure(bg=bg, fg=fg)
                elif isinstance(widget, tk.OptionMenu):
                    widget.configure(bg=bg, fg=fg)
                    try:
                        widget["menu"].configure(bg=bg, fg=fg)
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass
            self._update_all_widgets_recursive(widget, bg, fg)





    def select_game_folder(self):
        path = filedialog.askdirectory(initialdir=INPUT_DIR)
        if path:
            self.current_game_path = path
            self.show_centered_popup("Selected", f"Selected: {path}")


    def browse_bg(self):
        # Default to input directory
        initial_dir = os.path.join(os.getcwd(), "input") if os.path.exists(os.path.join(os.getcwd(), "input")) else os.getcwd()
        
        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("All Supported", "*.jpg;*.jpeg;*.gif;*.mp4;*.avi;*.mov;*.webm"),
                ("Images", "*.jpg;*.jpeg;*.gif"),
                ("Videos", "*.mp4;*.avi;*.mov;*.webm"),
                ("All Files", "*.*")
            ]
        )
        if file:
            self.bg_path_var.set(file)
            # Update status to show what type was selected
            ext = os.path.splitext(file)[1].lower()
            if ext == '.gif':
                self.update_status(f"✅ Selected animated GIF background: {os.path.basename(file)}")
            elif ext in ['.mp4', '.avi', '.mov', '.webm']:
                self.update_status(f"✅ Selected video background: {os.path.basename(file)}")
            else:
                self.update_status(f"✅ Selected image background: {os.path.basename(file)}")

    def browse_logo(self):
        """Browse for game logo PNG file"""
        # Default to input directory
        initial_dir = os.path.join(os.getcwd(), "input") if os.path.exists(os.path.join(os.getcwd(), "input")) else os.getcwd()
        
        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("PNG Images", "*.png"),
                ("All Files", "*.*")
            ]
        )
        if file:
            self.logo_path_var.set(file)
            self.update_status(f"✅ Selected game logo: {os.path.basename(file)}")

    def browse_company_logo(self):
        """Browse for company logo PNG file"""
        # Default to input directory
        initial_dir = os.path.join(os.getcwd(), "input") if os.path.exists(os.path.join(os.getcwd(), "input")) else os.getcwd()
        
        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[
                ("PNG Images", "*.png"),
                ("All Files", "*.*")
            ]
        )
        if file:
            self.company_logo_var.set(file)
            self.update_status(f"✅ Selected company logo: {os.path.basename(file)}")

    def browse_ico(self):
        # Default to input directory
        initial_dir = os.path.join(os.getcwd(), "input") if os.path.exists(os.path.join(os.getcwd(), "input")) else os.getcwd()
        
        file = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("Icon", "*.ico")]
        )
        if file:
            self.ico_path_var.set(file)
            # Auto-populate disc icon if user hasn't manually set it
            if self._auto_disc_icon:
                self.disc_icon_var.set(file)

    def browse_disc_icon(self):
        # Default to input directory (consistent with other browse buttons)
        initial_dir = os.path.join(os.getcwd(), "input") if os.path.exists(os.path.join(os.getcwd(), "input")) else os.getcwd()
        
        file = filedialog.askopenfilename(
            title="Select Disc Icon",
            initialdir=initial_dir,
            filetypes=[("Icon", "*.ico")]
        )
        if file:
            self.disc_icon_var.set(file)
            self._auto_disc_icon = False  # User manually chose, stop auto-populating

    def save_signing_settings(self):
        """Save signing settings to config"""
        if not hasattr(self, 'config'):
            self.config = {}
        
        self.config["sign_final_build"] = self.sign_final_build.get()
        self.config["remove_wti_branding"] = self.remove_wti_branding.get()

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def build_all(self):
        """Enhanced build process without DRM"""
        if not self.current_game_path:
            self.update_status("❌ Error: Game path not selected.")
            return

        game_name = os.path.basename(self.current_game_path)
        output_path = safe(os.path.abspath(os.path.join(OUTPUT_DIR, game_name)))
        os.makedirs(output_path, exist_ok=True)
        
        try:
            # 1. Copy runtime dependencies
            self.update_status("Copying runtime dependencies...")
            self.copy_runtime_dependencies(output_path)
            self.create_runtime_installer_helper(output_path)
        
            # 2. Copy game files
            self.update_status("Copying game files...")
            game_files_copied = self.copy_game_files_to_output(self.current_game_path, output_path)
            if not game_files_copied:
                self.update_status("⚠️ Warning: No game files copied")

            # 3. Collect metadata
            meta = {k: self.entries[k].get().strip() for k in self.entries}
            meta["GameName"] = game_name
            meta["Background"] = self.bg_path_var.get()
            meta["Logo"] = self.logo_path_var.get()
            meta["CompanyLogo"] = self.company_logo_var.get()
            meta["PublisherText"] = self.publisher_text_var.get()
            meta["Icon"] = self.ico_path_var.get()
            meta["InstallPath"] = f"C:\\Games\\{game_name}"

            # 4. Generate menu systems (no DRM)
            self.update_status("Compiling menu systems...")
            self.compile_menu_launcher(output_path)

            # 5. Write installer script
            self.update_status("Writing installer script...")
            self.generate_enhanced_installer_script(output_path, meta)

            # 6. Compile installer with enhanced security
            self.update_status("Compiling installer with ISCC...")
            self.compile_installer_with_iscc(output_path)
            
            # 6.1. Add security attributes to reduce false positives
            self.enhance_installer_security(output_path)

            # 7. Build extras
            self.update_status("Copying bonus content...")
            self.build_bonus_gallery(self.current_game_path, output_path)
            self.generate_readme(output_path, meta)
            
            # 8. Create autorun.inf with proper disc icon
            self.update_status("Creating autorun.inf...")
            self.generate_autorun(output_path)
        
            # 9. Create compatibility test
            self.update_status("Creating compatibility test...")
            self.create_compatibility_test_script(output_path)

            # 10. Create ISO
            self.update_status("Creating ISO image...")
            self.create_iso(output_path, meta)

            # 11. Clean output folder
            self.update_status("Cleaning output folder...")
            self.clean_output_folder_final(output_path, keep_mode="iso")

            # 12. Complete
            self.log_build_event(meta, output_path, success=True)
            self.update_status("✅ Build complete!")
            self.play_completion_jingle()
            self.show_centered_popup("Done", f"Build complete for {game_name}")

        except Exception as e:
            self.update_status(f"❌ Build failed: {e}")
            self.update_status(f"Traceback: {traceback.format_exc()}")








    def run_preflight_check(self):
        issues = []

        # Get game name from Title field
        game_name = self.entries["Title"].get().strip().replace(" ", "")
        input_path = os.path.join("input", game_name)
        config_path = os.path.join(input_path, "config.json")
        background_path = self.bg_path_var.get().strip()
        icon_path = self.ico_path_var.get().strip()

        # Check input folder
        if not os.path.isdir(input_path):
            issues.append(f"Missing input folder: {input_path}")

        # Check files
        if not os.path.isfile(background_path):
            issues.append("Missing background.jpg file.")
        if not os.path.isfile(icon_path):
            issues.append("Missing icon.ico file.")

        # Check metadata fields
        missing_fields = []
        if not self.entries["Title"].get().strip():
            missing_fields.append("Game Title")
        if not self.entries["Developer"].get().strip():
            missing_fields.append("Developer")
        if not self.entries["Start Menu Name"].get().strip():
            missing_fields.append("Start Menu Name")

        if missing_fields:
            issues.append("Missing metadata fields: " + ", ".join(missing_fields))

        if issues:
            self.show_centered_popup("Preflight Check Failed", "\n".join(issues))
            return False
        else:
            self.show_centered_popup("Preflight Check Passed", "All required files and metadata are present.")
            return True








    def compile_menu_launcher(self, output_path):
        """Enhanced menu compilation with multiple fallback systems"""
        menu_dir = os.path.join(output_path, "menu")
        os.makedirs(menu_dir, exist_ok=True)
        
        # 1. Always use the original menu creation function to preserve your design
        self.create_pyqt5_menu_launcher(menu_dir)
        self.update_status("✅ Generated original menu with enhanced features")
        
        # 2. Copy company logo if specified
        company_logo_path = self.company_logo_var.get().strip()
        if company_logo_path and os.path.exists(company_logo_path):
            logo_dest = os.path.join(menu_dir, "company_logo.png")
            try:
                shutil.copy2(company_logo_path, logo_dest)
                self.update_status("✅ Copied company logo")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy company logo: {e}")
        
        # 3. Create menu configuration file
        menu_config = {
            "company_logo": "company_logo.png" if company_logo_path and os.path.exists(company_logo_path) else "",
            "copyright_text": self.publisher_text_var.get().strip(),
            "language": "English",
            "remove_wti_branding": self.remove_wti_branding.get()
        }
        
        config_path = os.path.join(menu_dir, "menu_config.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(menu_config, f, indent=2)
            self.update_status("✅ Created menu configuration")
        except Exception as e:
            self.update_status(f"⚠️ Failed to create menu config: {e}")
        
        # 4. Copy background image/video to menu folder
        bg_source = self.bg_path_var.get()
        if bg_source and os.path.exists(bg_source):
            ext = os.path.splitext(bg_source)[1].lower()
            if ext == '.gif':
                bg_dest = os.path.join(menu_dir, "background.gif")
            elif ext in ['.mp4', '.avi', '.mov', '.webm']:
                bg_dest = os.path.join(menu_dir, "background.mp4")
            else:
                bg_dest = os.path.join(menu_dir, "background.jpg")
            try:
                shutil.copy2(bg_source, bg_dest)
                self.update_status("✅ Copied background to menu")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy background: {e}")
        
        # 5. Compile the PyQt5 menu
        launcher_pyw = os.path.join(menu_dir, "menu_launcher.pyw")
        if os.path.exists(launcher_pyw):
            success = self.compile_pyqt5_menu(output_path)
            if success:
                self.update_status("✅ PyQt5 menu compiled successfully")
            else:
                self.update_status("⚠️ PyQt5 menu compilation failed - fallbacks available")
        
        # 6. Create batch file fallback (always works)
        self.create_batch_menu_fallback(output_path)
        
        # 7. Create menu selector script
        self.create_menu_selector(output_path)
        
        return True  # Always return True since we have fallbacks





    def enhance_installer_security(self, output_path):
        """Add security attributes to reduce false positives"""
        setup_path = os.path.join(output_path, "setup.exe")
        
        if os.path.exists(setup_path):
            try:
                # Create security info file
                security_info = os.path.join(output_path, "SECURITY_INFO.txt")
                with open(security_info, "w", encoding="utf-8") as f:
                    f.write("SECURITY INFORMATION\n")
                    f.write("=" * 50 + "\n\n")
                    f.write("This installer was created with Rialto Disc Builder\n")
                    f.write("Installer Type: Inno Setup\n")
                    f.write("Source: Legitimate game distribution\n")
                    f.write("False Positive: Common with unsigned executables\n\n")
                    f.write("To verify authenticity:\n")
                    f.write("1. Check file properties for version info\n")
                    f.write("2. Scan with multiple antivirus engines\n")
                    f.write("3. Consider code signing for production releases\n\n")
                    f.write("For code signing support, enable SSL.com signing in Rialto\n")
                
                # Log security enhancement
                self.update_status("✅ Added security documentation")
                
                self.update_status("⚠️ Installer is unsigned — enable Sign Final Build for code signing")
                    
            except Exception as e:
                self.update_status(f"⚠️ Security enhancement failed: {e}")

    def compile_installer_with_iscc(self, output_path):
        """Compile the installer using ISCC with optional SSL.com Code Signing"""
        original_iss_path = os.path.join(output_path, "installer.iss")
        
        # Use original .iss file (signing happens after compilation now)
        iss_path = original_iss_path
        
        if self.sign_final_build.get():
            self.update_status("Compiling installer (signing enabled)...")
        else:
            self.update_status("Compiling installer...")
        
        # Try to find ISCC.exe
        iscc = shutil.which("ISCC.exe")
        if not iscc:
            iscc_path = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
            if os.path.exists(iscc_path):
                iscc = iscc_path

        if iscc:
            try:
                command = [iscc, iss_path]
                result = subprocess.run(command, cwd=output_path, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    setup_path = os.path.join(output_path, "setup.exe")
                    if os.path.exists(setup_path):
                        self.update_status(f"Installer compiled: {os.path.basename(setup_path)}")
                        
                        # Pause for manual code signing if requested
                        if self.sign_final_build.get():
                            self.update_status("🔐 Ready for code signing...")
                            self.update_status(f"📁 Files to sign are in: {output_path}")
                            self.update_status("🌐 Go to: https://app.esigner.com/")
                            self.update_status("📤 Upload setup.exe, sign it, download, and replace")
                            
                            # Show modal dialog for user to proceed
                            import tkinter.messagebox as msgbox
                            result = msgbox.askokcancel(
                                "Code Signing Pause",
                                f"Ready for manual code signing!\n\n"
                                f"Files location: {output_path}\n\n"
                                f"Steps:\n"
                                f"1. Go to https://app.esigner.com/\n"
                                f"2. Upload setup.exe from the build folder\n"
                                f"3. Sign it and download the signed version\n"
                                f"4. Replace the original setup.exe\n"
                                f"5. Click OK to continue with ISO packaging\n\n"
                                f"Click Cancel to skip signing and continue."
                            )
                            
                            if result:
                                self.update_status("✅ Continuing with signed files...")
                            else:
                                self.update_status("⏭️ Skipping code signing, continuing build...")
                        
                        self.update_status("Build complete")
                    else:
                        self.update_status("⚠️ ISCC ran but setup.exe is missing.")
                else:
                    self.update_status(f"❌ ISCC failed: {result.stderr}")
                    
                    
            except Exception as e:
                self.update_status(f"❌ Error running ISCC: {e}")
        else:
            self.update_status("⚠️ ISCC.exe not found. Cannot create setup.exe. Download Inno Setup: https://jrsoftware.org/isdl.php")




    def copy_runtime_dependencies(self, output_path):
        """Copy essential runtime libraries for maximum compatibility"""
        
        # First, try to copy the redistributable installers
        runtime_files = {
            "vcredist_x64.exe": [
                r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x64.exe",
                r"C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x64.exe"
            ],
            "vcredist_x86.exe": [
                r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x86.exe",
                r"C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Redist\MSVC\14.29.30133\vcredist_x86.exe"
            ]
        }
        
        copied_runtimes = 0
        
        for runtime_name, possible_paths in runtime_files.items():
            runtime_copied = False
            
            for source_path in possible_paths:
                if os.path.exists(source_path):
                    try:
                        dest_path = os.path.join(output_path, runtime_name)
                        shutil.copy2(source_path, dest_path)
                        self.update_status(f"✅ Copied runtime: {runtime_name}")
                        copied_runtimes += 1
                        runtime_copied = True
                        break
                    except Exception as e:
                        self.update_status(f"⚠️ Failed to copy {runtime_name}: {e}")
            
            if not runtime_copied:
                self.update_status(f"⚠️ Runtime not found: {runtime_name}")
        
        # Also copy the actual DLL files that the game needs
        self.copy_vcruntime_dlls(output_path)
        
        if copied_runtimes == 0:
            self.update_status("⚠️ No runtime dependencies found locally")
            self.download_essential_runtimes(output_path)
        
        return copied_runtimes > 0

    def copy_vcruntime_dlls(self, output_path):
        """Copy Visual C++ runtime DLLs directly to output folder"""
        required_dlls = [
            "msvcp140.dll",
            "msvcp140_1.dll",
            "msvcp140_2.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll",
            "concrt140.dll",
            "vccorlib140.dll"
        ]
        
        # Common locations for VC++ runtime DLLs
        dll_sources = [
            "C:\\Windows\\System32",
            "C:\\Windows\\SysWOW64",
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft Visual Studio\\2019\\Community\\VC\\Redist\\MSVC\\14.29.30133\\x64\\Microsoft.VC142.CRT"),
            os.path.join(sys.prefix, "DLLs"),
            os.path.dirname(sys.executable)
        ]
        
        copied_count = 0
        for dll in required_dlls:
            dll_found = False
            for source in dll_sources:
                source_path = os.path.join(source, dll)
                if os.path.exists(source_path):
                    try:
                        # Copy to main output directory
                        shutil.copy2(source_path, os.path.join(output_path, dll))
                        # Also copy to menu directory
                        menu_dir = os.path.join(output_path, "menu")
                        if os.path.exists(menu_dir):
                            shutil.copy2(source_path, os.path.join(menu_dir, dll))
                        self.update_status(f"✅ Copied {dll}")
                        dll_found = True
                        copied_count += 1
                        break
                    except OSError:
                        pass
            
            if not dll_found:
                self.update_status(f"⚠️ Could not find {dll}")
        
        self.update_status(f"✅ Copied {copied_count} runtime DLLs")





    def download_essential_runtimes(self, output_path):
        """Download essential runtimes if not found locally"""
        downloads = {
            "vcredist_x64.exe": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
            "vcredist_x86.exe": "https://aka.ms/vs/17/release/vc_redist.x86.exe"
        }
        
        for filename, url in downloads.items():
            try:
                dest_path = os.path.join(output_path, filename)
                self.update_status(f"⬇️ Downloading {filename}...")
                
                urllib.request.urlretrieve(url, dest_path)
                
                # Verify download
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
                    self.update_status(f"✅ Downloaded {filename}")
                else:
                    self.update_status(f"❌ Download failed: {filename}")
                    
            except Exception as e:
                self.update_status(f"❌ Download error for {filename}: {e}")




    def generate_enhanced_installer_script(self, output_path, meta):
        """Generate the enhanced installer script with maximum compatibility"""
        app_name = str(meta.get('Title') or 'Game')
        app_version = "1.0"
        publisher = str(meta.get('Developer') or 'Indie Developer')
        install_path = f"C:\\Games\\{app_name}"
        start_menu = str(meta.get('Start Menu Name') or app_name)
        output_filename = "setup"
        
        # Copy icon if exists
        icon_file = meta.get("Icon", "")
        copied_icon_path = ""
        if icon_file and os.path.exists(icon_file):
            try:
                copied_icon_path = os.path.join(output_path, "game_icon.ico")
                shutil.copy2(icon_file, copied_icon_path)
                self.update_status("✅ Copied game icon")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy icon: {e}")

        # Build installer script
        iss_script = "[Setup]\n"
        iss_script += f"AppName={app_name}\n"
        iss_script += f"AppVersion={app_version}\n"
        iss_script += f"AppPublisher={publisher}\n"
        iss_script += f"DefaultDirName={install_path}\n"
        iss_script += f"DefaultGroupName={start_menu}\n"
        iss_script += f"OutputBaseFilename={output_filename}\n"
        iss_script += "OutputDir=.\n"
        iss_script += "SolidCompression=no\n"
        iss_script += "DiskSpanning=yes\n"
        iss_script += "Compression=lzma2/fast\n"
        iss_script += "InternalCompressLevel=fast\n"
        iss_script += "DisableWelcomePage=no\n"
        iss_script += "DisableReadyPage=yes\n"
        iss_script += "UsePreviousAppDir=yes\n"
        iss_script += "ShowLanguageDialog=yes\n"  # Enable language selection dialog
        
        if copied_icon_path:
            iss_script += f"SetupIconFile={copied_icon_path}\n"
        
        iss_script += "UninstallDisplayIcon={app}\\game_icon.ico\n"
        iss_script += "UninstallFilesDir={app}\n"
        iss_script += f"UninstallDisplayName={app_name}\n"
        iss_script += "CreateUninstallRegKey=yes\n"
        iss_script += "PrivilegesRequired=lowest\n"
        iss_script += "PrivilegesRequiredOverridesAllowed=dialog commandline\n"
        iss_script += "MinVersion=6.1\n"
        iss_script += "ArchitecturesAllowed=x86 x64\n"
        iss_script += "DisableDirPage=auto\n"
        iss_script += "DisableProgramGroupPage=no\n"
        iss_script += "ChangesAssociations=no\n"
        iss_script += "RestartIfNeededByRun=no\n"
        
        # Languages section - ONLY languages with official Inno Setup translations
        iss_script += "\n[Languages]\n"
        iss_script += 'Name: "english"; MessagesFile: "compiler:Default.isl"\n'
        iss_script += 'Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\\BrazilianPortuguese.isl"\n'
        iss_script += 'Name: "catalan"; MessagesFile: "compiler:Languages\\Catalan.isl"\n'
        iss_script += 'Name: "czech"; MessagesFile: "compiler:Languages\\Czech.isl"\n'
        iss_script += 'Name: "danish"; MessagesFile: "compiler:Languages\\Danish.isl"\n'
        iss_script += 'Name: "dutch"; MessagesFile: "compiler:Languages\\Dutch.isl"\n'
        iss_script += 'Name: "finnish"; MessagesFile: "compiler:Languages\\Finnish.isl"\n'
        iss_script += 'Name: "french"; MessagesFile: "compiler:Languages\\French.isl"\n'
        iss_script += 'Name: "german"; MessagesFile: "compiler:Languages\\German.isl"\n'
        iss_script += 'Name: "hebrew"; MessagesFile: "compiler:Languages\\Hebrew.isl"\n'
        iss_script += 'Name: "italian"; MessagesFile: "compiler:Languages\\Italian.isl"\n'
        iss_script += 'Name: "japanese"; MessagesFile: "compiler:Languages\\Japanese.isl"\n'
        iss_script += 'Name: "norwegian"; MessagesFile: "compiler:Languages\\Norwegian.isl"\n'
        iss_script += 'Name: "polish"; MessagesFile: "compiler:Languages\\Polish.isl"\n'
        iss_script += 'Name: "portuguese"; MessagesFile: "compiler:Languages\\Portuguese.isl"\n'
        iss_script += 'Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"\n'
        iss_script += 'Name: "slovak"; MessagesFile: "compiler:Languages\\Slovak.isl"\n'
        iss_script += 'Name: "slovenian"; MessagesFile: "compiler:Languages\\Slovenian.isl"\n'
        iss_script += 'Name: "spanish"; MessagesFile: "compiler:Languages\\Spanish.isl"\n'
        iss_script += 'Name: "turkish"; MessagesFile: "compiler:Languages\\Turkish.isl"\n'
        iss_script += 'Name: "ukrainian"; MessagesFile: "compiler:Languages\\Ukrainian.isl"\n'
        
        # Custom messages for supported languages
        iss_script += "\n[CustomMessages]\n"
        
        # English
        iss_script += "english.SelectDirLabel=Select the folder where {#SetupSetting(\"AppName\")} should be installed, then click Next.\n"
        iss_script += "english.LaunchProgram=Launch {#SetupSetting(\"AppName\")}\n"
        
        # Brazilian Portuguese
        iss_script += "brazilianportuguese.SelectDirLabel=Selecione a pasta onde {#SetupSetting(\"AppName\")} deve ser instalado e clique em Avançar.\n"
        iss_script += "brazilianportuguese.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Catalan
        iss_script += "catalan.SelectDirLabel=Seleccioneu la carpeta on s'ha d'instal·lar {#SetupSetting(\"AppName\")}, després feu clic a Següent.\n"
        iss_script += "catalan.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Czech
        iss_script += "czech.SelectDirLabel=Vyberte složku, kam má být {#SetupSetting(\"AppName\")} nainstalován, a klikněte na Další.\n"
        iss_script += "czech.LaunchProgram=Spustit {#SetupSetting(\"AppName\")}\n"
        
        # Danish
        iss_script += "danish.SelectDirLabel=Vælg den mappe, hvor {#SetupSetting(\"AppName\")} skal installeres, og klik på Næste.\n"
        iss_script += "danish.LaunchProgram=Start {#SetupSetting(\"AppName\")}\n"
        
        # Dutch
        iss_script += "dutch.SelectDirLabel=Selecteer de map waarin {#SetupSetting(\"AppName\")} moet worden geïnstalleerd en klik op Volgende.\n"
        iss_script += "dutch.LaunchProgram={#SetupSetting(\"AppName\")} starten\n"
        
        # Finnish
        iss_script += "finnish.SelectDirLabel=Valitse kansio, johon {#SetupSetting(\"AppName\")} asennetaan, ja napsauta Seuraava.\n"
        iss_script += "finnish.LaunchProgram=Käynnistä {#SetupSetting(\"AppName\")}\n"
        
        # French
        iss_script += "french.SelectDirLabel=Sélectionnez le dossier où {#SetupSetting(\"AppName\")} doit être installé, puis cliquez sur Suivant.\n"
        iss_script += "french.LaunchProgram=Lancer {#SetupSetting(\"AppName\")}\n"
        
        # German
        iss_script += "german.SelectDirLabel=Wählen Sie den Ordner aus, in dem {#SetupSetting(\"AppName\")} installiert werden soll, und klicken Sie auf Weiter.\n"
        iss_script += "german.LaunchProgram={#SetupSetting(\"AppName\")} starten\n"
        
        # Hebrew
        iss_script += "hebrew.SelectDirLabel=בחר את התיקייה שבה יותקן {#SetupSetting(\"AppName\")}, ולאחר מכן לחץ על הבא.\n"
        iss_script += "hebrew.LaunchProgram=הפעל את {#SetupSetting(\"AppName\")}\n"
        
        # Italian
        iss_script += "italian.SelectDirLabel=Seleziona la cartella dove {#SetupSetting(\"AppName\")} deve essere installato, quindi clicca Avanti.\n"
        iss_script += "italian.LaunchProgram=Avvia {#SetupSetting(\"AppName\")}\n"
        
        # Japanese
        iss_script += "japanese.SelectDirLabel={#SetupSetting(\"AppName\")} をインストールするフォルダを選択して、次へをクリックしてください。\n"
        iss_script += "japanese.LaunchProgram={#SetupSetting(\"AppName\")} を起動\n"
        
        # Norwegian
        iss_script += "norwegian.SelectDirLabel=Velg mappen hvor {#SetupSetting(\"AppName\")} skal installeres, og klikk på Neste.\n"
        iss_script += "norwegian.LaunchProgram=Start {#SetupSetting(\"AppName\")}\n"
        
        # Polish
        iss_script += "polish.SelectDirLabel=Wybierz folder, w którym ma zostać zainstalowany {#SetupSetting(\"AppName\")}, a następnie kliknij Dalej.\n"
        iss_script += "polish.LaunchProgram=Uruchom {#SetupSetting(\"AppName\")}\n"
        
        # Portuguese
        iss_script += "portuguese.SelectDirLabel=Selecione a pasta onde {#SetupSetting(\"AppName\")} deve ser instalado e clique em Seguinte.\n"
        iss_script += "portuguese.LaunchProgram=Executar {#SetupSetting(\"AppName\")}\n"
        
        # Russian
        iss_script += "russian.SelectDirLabel=Выберите папку, в которую будет установлен {#SetupSetting(\"AppName\")}, затем нажмите Далее.\n"
        iss_script += "russian.LaunchProgram=Запустить {#SetupSetting(\"AppName\")}\n"
        
        # Slovak
        iss_script += "slovak.SelectDirLabel=Vyberte priečinok, kam sa má nainštalovať {#SetupSetting(\"AppName\")}, a potom kliknite na Ďalej.\n"
        iss_script += "slovak.LaunchProgram=Spustiť {#SetupSetting(\"AppName\")}\n"
        
        # Slovenian
        iss_script += "slovenian.SelectDirLabel=Izberite mapo, kamor naj se namesti {#SetupSetting(\"AppName\")}, nato kliknite Naprej.\n"
        iss_script += "slovenian.LaunchProgram=Zaženi {#SetupSetting(\"AppName\")}\n"
        
        # Spanish
        iss_script += "spanish.SelectDirLabel=Seleccione la carpeta donde se instalará {#SetupSetting(\"AppName\")}, luego haga clic en Siguiente.\n"
        iss_script += "spanish.LaunchProgram=Ejecutar {#SetupSetting(\"AppName\")}\n"
        
        # Turkish
        iss_script += "turkish.SelectDirLabel={#SetupSetting(\"AppName\")} programının kurulacağı klasörü seçin ve İleri'ye tıklayın.\n"
        iss_script += "turkish.LaunchProgram={#SetupSetting(\"AppName\")} Başlat\n"
        
        # Ukrainian
        iss_script += "ukrainian.SelectDirLabel=Виберіть папку, куди буде встановлено {#SetupSetting(\"AppName\")}, потім натисніть Далі.\n"
        iss_script += "ukrainian.LaunchProgram=Запустити {#SetupSetting(\"AppName\")}\n"
        
        iss_script += "\n[Files]\n"
        # IMPORTANT: Exclude unnecessary files from being installed
        iss_script += 'Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "vcredist_*.exe,*.tmp,*.log,installer.iss,temp_build,temp_spec,setup.exe,setup-*.bin,.*,launch_game.bat,start_menu.bat,menu.bat,check_runtime.bat"\n'
        iss_script += '\n; Runtime redistributables\n'
        iss_script += 'Source: "vcredist_x86.exe"; DestDir: "{app}\\runtime"; Flags: ignoreversion\n'
        iss_script += 'Source: "vcredist_x64.exe"; DestDir: "{app}\\runtime"; Flags: ignoreversion\n'
        
        iss_script += "\n[Icons]\n"
        # Direct to menu.exe if it exists, otherwise to game.exe
        iss_script += f'Name: "{{group}}\\{app_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"\n'
        iss_script += f'Name: "{{userdesktop}}\\{app_name}"; Filename: "{{app}}\\menu\\menu.exe"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\game_icon.ico"; Tasks: desktopicon\n'
        
        iss_script += "\n[Tasks]\n"
        iss_script += 'Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"\n'
        
        iss_script += "\n[Run]\n"
        iss_script += f'Filename: "{{app}}\\menu\\menu.exe"; Description: "{{cm:LaunchProgram}}"; Flags: nowait postinstall skipifsilent\n'
        
        iss_script += "\n[Code]\n"
        iss_script += "function IsWin64: Boolean;\n"
        iss_script += "begin\n"
        iss_script += "  Result := IsWin64;\n"
        iss_script += "end;\n"
        
        # Registry section
        iss_script += "\n[Registry]\n"
        iss_script += f'Root: HKA; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app_name}"; ValueType: string; ValueName: "UninstallString"; ValueData: "{{uninstallexe}}"\n'
        iss_script += f'Root: HKA; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app_name}"; ValueType: string; ValueName: "QuietUninstallString"; ValueData: "{{uninstallexe}} /SILENT"\n'
        iss_script += f'Root: HKA; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app_name}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{{app}}"\n'
        iss_script += f'Root: HKA; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{app_name}"; ValueType: string; ValueName: "Publisher"; ValueData: "{publisher}"\n'
        
        iss_script += "\n[UninstallDelete]\n"
        iss_script += 'Type: filesandordirs; Name: "{app}"\n'

        iss_path = os.path.join(output_path, "installer.iss")
        try:
            with open(iss_path, "w", encoding="utf-8") as f:
                f.write(iss_script)
            self.update_status("✅ Enhanced installer script written with 21 properly supported languages")
            
            # Create a first-run script that installs runtimes
            try:
                if hasattr(self, 'create_first_run_script'):
                    self.create_first_run_script(output_path)
            except Exception as e:
                self.update_status(f"⚠️ Could not create runtime checker: {e}")
                
        except Exception as e:
            self.update_status(f"❌ Failed to write installer script: {e}")





    def create_first_run_script(self, output_path):
        """Create a script that checks and installs runtimes on first run"""
        check_script = '''@echo off
rem Runtime checker - runs silently in background

cd /d "%~dp0"

rem Check if runtimes are already installed
reg query "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64" >nul 2>&1
if %errorlevel% equ 0 (
    rem x64 runtime already installed
    goto check_x86
)

rem Install x64 runtime if present
if exist "runtime\\vcredist_x64.exe" (
    start /wait "" "runtime\\vcredist_x64.exe" /quiet /norestart
)

:check_x86
reg query "HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x86" >nul 2>&1
if %errorlevel% equ 0 (
    rem x86 runtime already installed
    exit /b 0
)

rem Install x86 runtime if present
if exist "runtime\\vcredist_x86.exe" (
    start /wait "" "runtime\\vcredist_x86.exe" /quiet /norestart
)

exit /b 0
'''
        
        check_path = os.path.join(output_path, "check_runtime.bat")
        try:
            with open(check_path, "w") as f:
                f.write(check_script)
            self.update_status("✅ Created first-run runtime checker")
        except Exception as e:
            self.update_status(f"⚠️ Could not create runtime checker: {e}")









    def compile_pyqt5_menu(self, output_path):
        """Enhanced PyQt5 menu compilation with icon and runtime support"""
        menu_dir = os.path.join(output_path, "menu")
        launcher_pyw = os.path.join(menu_dir, "menu_launcher.pyw")
        
        if not os.path.exists(launcher_pyw):
            self.update_status("❌ menu_launcher.pyw not found for compilation")
            return False
        
        # Copy game icon to menu directory for compilation
        icon_source = os.path.join(output_path, "game_icon.ico")
        icon_dest = os.path.join(menu_dir, "game_icon.ico")
        if os.path.exists(icon_source):
            try:
                shutil.copy2(icon_source, icon_dest)
            except OSError:
                pass
        
        # Copy runtime DLLs to menu directory
        self.copy_vcruntime_dlls(menu_dir)
        
        # Enhanced PyInstaller path detection
        app_dir = os.path.dirname(os.path.abspath(__file__))
        pyinstaller_paths = [
            os.path.join(app_dir, "python39", "venv", "Scripts", "pyinstaller.exe"),
            os.path.join(sys.prefix, "Scripts", "pyinstaller.exe"),
            "pyinstaller.exe",
            os.path.join(os.path.dirname(sys.executable), "pyinstaller.exe"),
            os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller.exe")
        ]
        
        pyinstaller_path = None
        for path in pyinstaller_paths:
            if os.path.exists(path):
                pyinstaller_path = path
                self.update_status(f"✅ Found PyInstaller at: {path}")
                break
            elif shutil.which(path):
                pyinstaller_path = shutil.which(path)
                self.update_status(f"✅ Found PyInstaller in PATH: {pyinstaller_path}")
                break
        
        if not pyinstaller_path:
            self.update_status("⚠️ PyInstaller not found. Batch menu fallback will be used. Install with: pip install pyinstaller")
            return False
        
        # Build command with icon and runtime
        build_cmd = [
            pyinstaller_path,
            "--onefile",
            "--windowed", 
            "--clean",
            "--noupx",
            "--name", "menu",
            "--distpath", menu_dir,
            "--workpath", os.path.join(output_path, "temp_build"),
            "--specpath", os.path.join(output_path, "temp_spec"),
        ]
        
        # Add icon if it exists
        if os.path.exists(icon_dest):
            build_cmd.extend(["--icon", icon_dest])
        
        # Add runtime DLLs
        for dll in ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
            dll_path = os.path.join(menu_dir, dll)
            if os.path.exists(dll_path):
                build_cmd.extend(["--add-binary", f"{dll_path};."])
        
        build_cmd.append(launcher_pyw)
        
        # Add PyQt5 dependencies
        try:
            import PyQt5
            build_cmd.extend([
                "--collect-all", "PyQt5",
                "--hidden-import=PyQt5.QtCore",
                "--hidden-import=PyQt5.QtGui",
                "--hidden-import=PyQt5.QtWidgets"
            ])
            self.update_status("✅ Added PyQt5 dependencies to build")
        except ImportError:
            self.update_status("⚠️ PyQt5 not found, trying basic compilation...")
        
        # Add background image if it exists
        bg_path = os.path.join(menu_dir, "background.jpg")
        if os.path.exists(bg_path):
            build_cmd.extend(["--add-data", f"{bg_path};."])
        
        try:
            self.update_status("🔄 Compiling PyQt5 menu with PyInstaller...")
            result = subprocess.run(
                build_cmd,
                cwd=menu_dir,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=300
            )
            
            menu_exe = os.path.join(menu_dir, "menu.exe")
            
            if result.returncode == 0 and os.path.exists(menu_exe):
                self.update_status("✅ PyQt5 menu compiled successfully with icon!")
                
                # Clean up source files but keep DLLs
                files_to_clean = [
                    "menu_launcher.pyw",  # Generated file, cleaned after compilation
                    "background.jpg",
                    "game_icon.ico"
                ]
                
                cleaned_count = 0
                for file_to_clean in files_to_clean:
                    file_path = os.path.join(menu_dir, file_to_clean)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except OSError:
                            pass
                
                if cleaned_count > 0:
                    self.update_status(f"🧹 Cleaned {cleaned_count} source menu files (kept menu.exe)")
                
                return True
            else:
                self.update_status("❌ PyInstaller compilation failed")
                if result.stderr:
                    self.update_status(f"Error: {result.stderr}")
                return False
                
        except Exception as e:
            self.update_status(f"❌ PyInstaller execution failed: {e}")
            return False
        
        finally:
            # Clean up temp directories
            temp_dirs = [
                os.path.join(output_path, "temp_build"),
                os.path.join(output_path, "temp_spec")
            ]
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                    except OSError:
                        pass




    def create_batch_menu_fallback(self, output_path):
        """Create batch file menu that always works"""
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        game_title = meta.get('Title', 'Game')
        # Escape batch special characters to prevent command injection
        for ch in ('&', '|', '>', '<', '^', '(', ')'):
            game_title = game_title.replace(ch, f'^{ch}')
        game_title_upper = game_title.upper()

        batch_content = """@echo off
title {game_title} Menu
color 07
cls

:menu
echo.
echo ==========================================
echo           {game_title_upper}
echo ==========================================
echo.
echo 1. Play Game
echo 2. Open Bonus Content
echo 3. Uninstall Game
echo 4. Exit
echo.
set /p choice="Choose an option (1-4): "

if "%choice%"=="1" goto playgame
if "%choice%"=="2" goto bonus  
if "%choice%"=="3" goto uninstall
if "%choice%"=="4" goto exit
echo Invalid choice. Please try again.
timeout /t 2 >nul
goto menu

:playgame
cls
echo Starting {game_title}...
rem Find the main game executable dynamically
for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" (
        if /i not "%%f"=="unins000.exe" (
            if /i not "%%f"=="UnityCrashHandler64.exe" (
                start "" "%%f"
                goto exit
            )
        )
    )
)
echo.
echo ERROR: Game executable not found!
echo Please reinstall the game.
echo.
pause
goto menu

:bonus
cls
echo Opening bonus content...
if exist "bonus" (
    start "" "bonus"
    echo Bonus content opened in file explorer.
    timeout /t 2 >nul
    goto menu
) else (
    echo.
    echo WARNING: Bonus content not found!
    echo.
    pause
    goto menu
)

:uninstall
cls
echo.
echo Are you sure you want to uninstall {game_title}? (Y/N)
set /p confirm=""
if /i "%confirm%"=="Y" goto do_uninstall
if /i "%confirm%"=="YES" goto do_uninstall
goto menu

:do_uninstall
if exist "unins000.exe" (
    echo Starting uninstaller...
    start "" "unins000.exe"
    goto exit
) else (
    echo.
    echo WARNING: Uninstaller not found!
    echo You may need to manually remove the game.
    echo.
    pause
    goto menu
)

:exit
exit
"""
        
        batch_path = os.path.join(output_path, "menu.bat")
        with open(batch_path, "w") as f:
            f.write(batch_content.format(game_title=game_title, game_title_upper=game_title_upper))
        
        self.update_status("✅ Created batch menu fallback")





    def create_menu_selector(self, output_path):
        """Create batch file that selects the best menu option"""
        selector_content = """@echo off
rem Priority 1: Try PyQt5 advanced menu (best experience)
if exist "menu\\menu.exe" (
    start "" "menu\\menu.exe"
    exit /b 0
)

rem Priority 2: Find and launch the main game executable
for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" (
        if /i not "%%f"=="unins000.exe" (
            if /i not "%%f"=="UnityCrashHandler64.exe" (
                start "" "%%f"
                exit /b 0
            )
        )
    )
)

rem Priority 3: LAST RESORT - Show batch menu
if exist "menu.bat" (
    echo Advanced menu unavailable, starting compatibility mode...
    timeout /t 2 >nul
    call "menu.bat"
    exit /b 0
)

rem Nothing works - show error
echo.
echo ERROR: No menu system or game executable found!
echo Please contact support or reinstall the game.
echo.
pause
exit /b 1
"""
        
        selector_path = os.path.join(output_path, "start_menu.bat")
        with open(selector_path, "w") as f:
            f.write(selector_content)
        
        self.update_status("✅ Created menu selector batch")

        # Create VBScript that checks runtimes first, then runs menu
        vbs_launcher = '''Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Check DVD verification first (if DRM is enabled)
drmChecker = strPath & "\\check_dvd.bat"
If objFSO.FileExists(drmChecker) Then
    WScript.Echo "Running DRM check..."
    result = WshShell.Run(Chr(34) & drmChecker & Chr(34), 0, True)
    If result <> 0 Then
        ' DRM check failed - exit
        WScript.Quit
    End If
End If

' Check and install runtimes if needed (silently)
runtimeChecker = strPath & "\\check_runtime.bat"
If objFSO.FileExists(runtimeChecker) Then
    WshShell.Run Chr(34) & runtimeChecker & Chr(34), 0, True
End If

' Check if menu.exe exists and run it directly (no console)
menuPath = strPath & "\\menu\\menu.exe"
If objFSO.FileExists(menuPath) Then
    WshShell.Run Chr(34) & menuPath & Chr(34), 0, False
    WScript.Quit
End If

' Find and launch the main game executable
Set objFolder = objFSO.GetFolder(strPath)
For Each objFile In objFolder.Files
    If LCase(objFSO.GetExtensionName(objFile.Name)) = "exe" Then
        fileName = LCase(objFile.Name)
        If fileName <> "setup.exe" And fileName <> "unins000.exe" And fileName <> "unitycrashhandler64.exe" Then
            WshShell.Run Chr(34) & objFile.Path & Chr(34), 0, False
            WScript.Quit
        End If
    End If
Next

' Nothing found - show error
MsgBox "Game files not found. Please reinstall the game.", vbCritical, "Error"
'''
        
        vbs_path = os.path.join(output_path, "launch_silent.vbs")
        with open(vbs_path, "w") as f:
            f.write(vbs_launcher)
        
        # Create a simple batch launcher
        batch_launcher = '''@echo off
wscript.exe "%~dp0launch_silent.vbs" //B //NoLogo
exit
'''
        
        launcher_path = os.path.join(output_path, "launch_game.bat")
        with open(launcher_path, "w") as f:
            f.write(batch_launcher)
        
        self.update_status("✅ Created silent launcher system")















    def run_build_process(self):
        """Enhanced build process with preflight check"""
        self.update_status("Starting build process...")

        if not self.run_preflight_check():
            return
        self.build_all()

    def refresh_windows_icon_cache(self):
        """Refresh Windows icon cache to show updated disc icons"""
        try:
            if sys.platform == "win32":
                # Force Windows to refresh the icon cache
                self.update_status("🔄 Refreshing Windows icon cache...")
                subprocess.run([
                    "cmd", "/c", 
                    "ie4uinit.exe", "-show"
                ], capture_output=True, timeout=10)
                self.update_status("✅ Icon cache refreshed")
        except Exception as e:
            # Silently fail - this is just a nice-to-have
            pass

    def clean_output_folder_final(self, output_path, keep_mode="iso"):
        """Final cleanup - remove everything except ISO file"""
        
        # Files to KEEP (everything else gets deleted)
        keep_files = []
        
        # Add ISO files to keep
        for item in os.listdir(output_path):
            if item.lower().endswith(".iso"):
                keep_files.append(item)
        
        # Don't keep README.txt in the output folder - it's already in the ISO
        
        self.update_status(f"🧹 Final cleanup - keeping only: {', '.join(keep_files) if keep_files else 'ISO files'}")
        
        # Remove EVERYTHING else (since it's all in the installer/ISO now)
        items_to_remove = []
        for item in os.listdir(output_path):
            if item not in keep_files:
                items_to_remove.append(item)
        
        cleaned_count = 0
        for item in items_to_remove:
            item_path = os.path.join(output_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    self.update_status(f"🧹 Removed: {item}/")
                else:
                    os.remove(item_path)
                    self.update_status(f"🧹 Removed: {item}")
                cleaned_count += 1
            except Exception as e:
                self.update_status(f"⚠️ Cleanup failed on {item}: {e}")
        
        if cleaned_count > 0:
            self.update_status(f"🧹 Final cleanup complete - removed {cleaned_count} items")
            self.update_status("✅ Output folder now contains only ISO file ready for burning")
        
        # Verify final state
        remaining_files = os.listdir(output_path)
        iso_files = [f for f in remaining_files if f.lower().endswith('.iso')]
        
        if iso_files:
            iso_size = os.path.getsize(os.path.join(output_path, iso_files[0])) / (1024 * 1024)
            self.update_status(f"📀 Final result: {iso_files[0]} ({iso_size:.1f} MB) ready for disc burning")
        else:
            self.update_status("❌ Warning: No ISO file found in final output")





    def burn_to_master(self):
        """Enhanced burn to master with better ISO detection and ImgBurn integration"""
        import ctypes
        
        try:
            import win32file
        except ImportError:
            self.show_centered_popup("Missing Module", "pywin32 module required for disc burning.\nInstall with: pip install pywin32")
            return
        
        iso_path = None
        # Auto-select the most recent ISO in the output folder
        iso_files = []
        for subdir in os.listdir(OUTPUT_DIR):
            subpath = os.path.join(OUTPUT_DIR, subdir)
            if os.path.isdir(subpath):
                for f in os.listdir(subpath):
                    if f.endswith(".iso"):
                        full_path = os.path.join(subpath, f)
                        iso_files.append((os.path.getmtime(full_path), full_path))
        
        if iso_files:
            iso_files.sort(reverse=True)
            iso_path = iso_files[0][1]
        
        if not iso_path:
            self.show_centered_popup("Burn Failed", "No ISO file found to burn.")
            return

        # Find ImgBurn installation path
        imgburn_paths = [
            r"C:\Program Files\ImgBurn\ImgBurn.exe",
            r"C:\Program Files (x86)\ImgBurn\ImgBurn.exe",
            os.path.join(os.environ.get("ProgramFiles", ""), "ImgBurn", "ImgBurn.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "ImgBurn", "ImgBurn.exe")
        ]
        
        imgburn_exe = None
        for path in imgburn_paths:
            if os.path.isfile(path):
                imgburn_exe = path
                break
        
        if not imgburn_exe:
            # Try to use Windows built-in disc burning
            self.update_status("ImgBurn not found, using Windows disc burning...")
            try:
                os.startfile(iso_path)
                self.show_centered_popup("Burn Started", "ISO opened with Windows disc burning.\nSelect 'Burn disc image' when prompted.")
                return
            except Exception as e:
                self.show_centered_popup("ImgBurn Not Found", 
                                       "ImgBurn not found. Please install from:\n"
                                       "https://www.imgburn.com/\n\n"
                                       "Or use Windows built-in disc burning.")
                return

        # Auto-detect DVD drive
        dvd_drives = []
        drives = win32file.GetLogicalDrives()
        
        for i in range(26):
            if drives & (1 << i):
                drive_letter = chr(ord('A') + i)
                drive_path = f"{drive_letter}:\\"
                try:
                    drive_type = win32file.GetDriveType(drive_path)
                    if drive_type == win32file.DRIVE_CDROM:  # CD/DVD drive
                        dvd_drives.append(drive_letter)
                except Exception:
                    continue
        
        if not dvd_drives:
            self.show_centered_popup("No DVD Drive", "No DVD/CD drive detected.")
            return
        
        # Select drive
        if len(dvd_drives) == 1:
            dvd_drive = dvd_drives[0]
        else:
            # Multiple drives found, let user choose
            drive_list = ", ".join(dvd_drives)
            drive_dialog = tk.Toplevel(self.root)
            drive_dialog.title("Select DVD Drive")
            drive_dialog.geometry("300x150")
            drive_dialog.transient(self.root)
            drive_dialog.grab_set()
            
            tk.Label(drive_dialog, text=f"Multiple DVD drives found:\n{drive_list}\n\nSelect drive:").pack(pady=10)
            
            drive_var = tk.StringVar(value=dvd_drives[0])
            drive_menu = ttk.Combobox(drive_dialog, textvariable=drive_var, values=dvd_drives, state="readonly")
            drive_menu.pack(pady=10)
            
            selected_drive = [None]
            
            def select_drive():
                selected_drive[0] = drive_var.get()
                drive_dialog.destroy()
            
            tk.Button(drive_dialog, text="Select", command=select_drive).pack(pady=10)
            
            self.root.wait_window(drive_dialog)
            dvd_drive = selected_drive[0]
            
            if not dvd_drive:
                return

        try:
            # Confirm burn operation
            iso_name = os.path.basename(iso_path)
            iso_size_mb = os.path.getsize(iso_path) / (1024 * 1024)
            
            result = self.show_centered_popup("Confirm Burn", 
                f"Ready to burn:\n{iso_name} ({iso_size_mb:.1f} MB)\n\n"
                f"To drive: {dvd_drive}:\n\n"
                f"This will erase any existing data on the disc.\n"
                f"Continue?", kind="yesno")
            
            if not result:
                return
            
            # Build ImgBurn command
            cmd = [
                imgburn_exe,
                "/MODE", "WRITE",
                "/SRC", iso_path,
                "/DEST", f"{dvd_drive}:",
                "/VERIFY", "YES",
                "/CLOSESUCCESS",
                "/START",
                "/COPIES", "1"
            ]
            
            self.update_status(f"🔥 Starting DVD burn to drive {dvd_drive}:...")
            
            # Run ImgBurn
            process = subprocess.Popen(cmd)
            
            self.update_status("📀 ImgBurn launched - burning in progress...")
            self.update_status("⏳ Please wait for ImgBurn to complete the burn...")
            
        except Exception as e:
            self.show_centered_popup("Burn Failed", f"Could not start ImgBurn:\n{e}")
            self.update_status(f"❌ Burn error: {e}")











    def build_bonus_gallery(self, game_path, output_path):
        """Copy bonus content folder if it exists"""
        bonus_source = os.path.join(game_path, "bonus")
        bonus_output = os.path.join(output_path, "bonus")

        if not os.path.exists(bonus_source):
            self.update_status("ℹ️ No bonus folder found - skipping")
            return

        try:
            if os.path.exists(bonus_output):
                shutil.rmtree(bonus_output)
            shutil.copytree(bonus_source, bonus_output)
            self.update_status("✅ Bonus content copied")
        except Exception as e:
            self.update_status(f"⚠️ Failed to copy bonus content: {e}")




    def copy_game_files_to_output(self, source_dir, output_dir):
        """Copy all game files from input folder to output folder"""
        try:
            copied_files = 0
            main_py_file = None
            
            for item in os.listdir(source_dir):
                source_path = os.path.join(source_dir, item)
                dest_path = os.path.join(output_dir, item)
                
                # Skip certain files/folders that shouldn't be in the installer
                skip_items = ["menu", "installer.iss", "setup.exe", "autorun.inf"]
                if item.lower() in skip_items:
                    continue
                
                # Track main .py file for Ren'Py games
                if item.endswith(".py") and os.path.isfile(source_path) and main_py_file is None:
                    main_py_file = item
                
                # Always include game_logo.png
                if item == "game_logo.png":
                    shutil.copy2(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item} (game logo)")
                elif os.path.isfile(source_path):
                    shutil.copy2(source_path, dest_path)
                    copied_files += 1
                    self.update_status(f"📁 Copied: {item}")
                elif os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                    copied_files += 1
                    self.update_status(f"📁 Copied folder: {item}")
            
            # For Ren'Py games: also copy main .py file as game.py
            if main_py_file and main_py_file != "game.py":
                # Check if this is a Ren'Py game (has renpy folder)
                if os.path.exists(os.path.join(output_dir, "renpy")) or os.path.exists(os.path.join(output_dir, "lib")):
                    game_py_src = os.path.join(output_dir, main_py_file)
                    game_py_dest = os.path.join(output_dir, "game.py")
                    if os.path.exists(game_py_src) and not os.path.exists(game_py_dest):
                        shutil.copy2(game_py_src, game_py_dest)
                        self.update_status(f"📁 Created game.py from {main_py_file} (Ren'Py launcher)")
                        copied_files += 1
            
            self.update_status(f"✅ Copied {copied_files} game files/folders")
            return copied_files > 0
            
        except Exception as e:
            self.update_status(f"❌ Failed to copy game files: {e}")
            return False




    def cleanup_before_installer(self, output_path):
        """Remove unnecessary files before creating installer"""
        cleanup_items = [
            "installer.iss",  # Don't include the script itself
            "menu_launcher.pyw",  # Don't include source file
            "temp_build",
            "temp_spec", 
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "error_log.txt"
        ]
        
        # Don't clean the menu folder - we need those files!
        protected_folders = ["menu", "bonus", "engine", "data"]
        
        for item in cleanup_items:
            if "*" in item:
                # Handle wildcards
                for file_path in glob.glob(os.path.join(output_path, "**", item), recursive=True):
                    # Skip protected folders
                    skip = False
                    for protected in protected_folders:
                        if protected in file_path:
                            skip = True
                            break
                    
                    if not skip:
                        try:
                            os.remove(file_path)
                            self.update_status(f"🧹 Removed: {os.path.basename(file_path)}")
                        except OSError:
                            pass
            else:
                item_path = os.path.join(output_path, item)
                if os.path.exists(item_path):
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        self.update_status(f"🧹 Removed: {item}")
                    except Exception as e:
                        self.update_status(f"⚠️ Cleanup warning: {e}")










    def create_iso(self, output_path, meta):
        """Restored original working ISO creation method"""
        game_name = meta["GameName"]
        iso_path = os.path.join(output_path, f"{game_name}.iso")
        
        self.update_status("Creating ISO using original method...")
        
        # Clean up temp files before ISO creation
        temp_files_to_remove = ["installer.iss", "compatibility_test.bat"]
        for temp_file in temp_files_to_remove:
            temp_path = os.path.join(output_path, temp_file)
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
        
        # Files to include in ISO (essential files only)
        iso_files = ["setup.exe", "autorun.inf", "README.txt"]
        
        # Add all setup binary files dynamically
        for file in os.listdir(output_path):
            if file.startswith("setup-") and file.endswith(".bin"):
                iso_files.append(file)
        
        # Add any .ico files for disc icon
        for file in os.listdir(output_path):
            if file.lower().endswith(".ico"):
                iso_files.append(file)
        
        # Add menu files for compatibility
        menu_files = ["start_menu.bat", "menu.bat"]
        for menu_file in menu_files:
            if os.path.exists(os.path.join(output_path, menu_file)):
                iso_files.append(menu_file)
        
        # Add menu folder if it exists
        if os.path.exists(os.path.join(output_path, "menu")):
            iso_files.append("menu")
        
        # Add DRM lock folders (if DRM enabled)
        drm_items = []
        for item in os.listdir(output_path):
            if item.startswith(".") and os.path.isdir(os.path.join(output_path, item)):
                iso_files.append(item)
                drm_items.append(item)
                self.update_status(f"🔒 Including DRM folder in ISO: {item}/")
        
        self.update_status(f"📦 ISO will contain {len(iso_files)} items")
        
        # Try to locate mkisofs or oscdimg
        mkisofs = shutil.which("mkisofs")
        oscdimg = shutil.which("oscdimg")
        
        tool = None
        if mkisofs:
            self.update_status("✅ Found mkisofs - creating professional ISO")
            # Build command for mkisofs with only the files that exist
            existing_files = []
            for f in iso_files:
                if os.path.exists(os.path.join(output_path, f)):
                    existing_files.append(f)
            
            tool = [mkisofs, "-o", iso_path, "-J", "-R", "-V", game_name[:16]] + existing_files
            
        elif oscdimg:
            # For oscdimg, we need to create a temp folder with only the files we want
            temp_iso_folder = os.path.join(output_path, "temp_iso_build")
            if os.path.exists(temp_iso_folder):
                shutil.rmtree(temp_iso_folder)
            os.makedirs(temp_iso_folder)
    
            # Copy only the files we want to the temp folder
            for item in iso_files:
                src_path = os.path.join(output_path, item)
                if os.path.exists(src_path):
                    dst_path = os.path.join(temp_iso_folder, item)
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)
    
            tool = [oscdimg, "-m", "-j1", f"-l{game_name[:16]}", temp_iso_folder, iso_path]
            
        else:
            self.update_status("⚠️ No professional ISO tools found")
            # Fallback to Python ZIP method (but still create .iso extension)
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
            return
        
        # Run the ISO creation tool
        try:
            self.update_status("🔄 Running ISO creation...")
            result = subprocess.run(
                tool,
                cwd=output_path,
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=120
            )
            
            # Check if ISO was created successfully
            if os.path.exists(iso_path):
                iso_size = os.path.getsize(iso_path) / (1024 * 1024)  # MB
                self.update_status(f"✅ ISO created successfully: {iso_size:.1f} MB")
                self.refresh_windows_icon_cache()
                
                if drm_items:
                    self.update_status(f"🔒 ISO includes {len(drm_items)} DRM protection files")
                
                self.update_status("📀 Ready to burn: Use disc burning software to burn this ISO")
                temp_iso_folder = os.path.join(output_path, "temp_iso_build")
                if os.path.exists(temp_iso_folder):
                    try:
                        shutil.rmtree(temp_iso_folder)
                        self.update_status("🧹 Cleaned temp ISO build folder")
                    except OSError:
                        pass

            else:
                self.update_status("❌ ISO tool ran but no file was generated")
                temp_iso_folder = os.path.join(output_path, "temp_iso_build")
                if os.path.exists(temp_iso_folder):
                    try:
                        shutil.rmtree(temp_iso_folder)
                        self.update_status("🧹 Cleaned temp ISO build folder")
                    except OSError:
                        pass
                self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
                
        except subprocess.CalledProcessError as e:
            self.update_status(f"❌ ISO creation failed: {e}")
            if e.stderr:
                self.update_status(f"   Error details: {e.stderr.strip()}")
            self.update_status("🔄 Trying Python fallback method...")
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)
            
        except Exception as e:
            self.update_status(f"❌ ISO creation error: {e}")
            self.create_python_iso_fallback(output_path, iso_path, iso_files, meta)

    def create_python_iso_fallback(self, output_path, iso_path, iso_files, meta):
        """Python-based ISO creation fallback"""
        try:
            self.update_status("📦 Creating ISO with Python fallback...")
            
            with zipfile.ZipFile(iso_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
                files_added = 0
                
                for item in iso_files:
                    item_path = os.path.join(output_path, item)
                    
                    if os.path.isfile(item_path):
                        zipf.write(item_path, item)
                        files_added += 1
                        
                    elif os.path.isdir(item_path):
                        # Add entire directory
                        for root, dirs, files in os.walk(item_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_name = os.path.relpath(file_path, output_path)
                                zipf.write(file_path, arc_name)
                                files_added += 1
                
                self.update_status(f"📦 Added {files_added} files to ISO")
            
            if os.path.exists(iso_path) and os.path.getsize(iso_path) > 1024:
                iso_size = os.path.getsize(iso_path) / (1024 * 1024)  # MB
                self.update_status(f"✅ Python ISO created: {iso_size:.1f} MB")
                self.refresh_windows_icon_cache()
                self.update_status("📀 Note: Extract contents before burning to disc")
            else:
                self.update_status("❌ Python ISO creation failed")
                
        except Exception as e:
            self.update_status(f"❌ Python ISO fallback failed: {e}")










    def generate_readme(self, output_path, meta):
        readme_path = os.path.join(output_path, "README.txt")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"""=== INSTALLATION GUIDE ===

    Thank you for installing {meta['Title']}!

    If the installer doesn't auto-start:
    1. Open this folder manually.
    2. Run 'setup.exe' to install the game.
    3. Once installed, you can launch the game from your Start Menu.

    Enjoy!
""")
            if not self.remove_wti_branding.get():
                f.write("    ~ We the Indies\n")





    def create_lock_file(self, output_path, game_name):
        # Random folder nesting to obfuscate location
        subdir = ''.join(random.choices(string.ascii_lowercase, k=5))
        lock_dir = os.path.join(output_path, subdir)
        os.makedirs(lock_dir, exist_ok=True)

        # Create the .lock file with game-specific name
        lock_name = f".{game_name.lower().replace(' ', '_')}.lock"
        lock_path = os.path.join(lock_dir, lock_name)

        try:
            with open(lock_path, "w", encoding="utf-8") as f:
                f.write("verified")
        except Exception:
            pass











    def generate_autorun(self, output_path):
        """Create autorun.inf with proper disc icon and label"""
        self.update_status("Creating autorun.inf...")
        
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        disc_label = self.disc_name_var.get().strip() or meta.get('Title', 'Game Disc')
        disc_icon_path = self.disc_icon_var.get().strip()
        
        # Debug: print disc icon path
        self.update_status(f"🔍 Disc icon path: '{disc_icon_path}'")
        
        # Copy disc icon if provided. Always use a consistent filename.
        icon_filename = "disc_icon.ico"
        dest_path = os.path.join(output_path, icon_filename)

        # Clear any existing disc_icon.ico first
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except Exception:
            pass

        if disc_icon_path and os.path.exists(disc_icon_path):
            try:
                shutil.copy(disc_icon_path, dest_path)
                self.update_status(f"✅ Copied disc icon from: {os.path.basename(disc_icon_path)}")
            except Exception as e:
                self.update_status(f"⚠️ Failed to copy disc icon: {e}")
                icon_filename = "game_icon.ico"  # Fallback to game icon
        else:
            # Use game icon as fallback - copy it to be the disc icon
            self.update_status("📝 No disc icon specified, using game icon as fallback")
            game_icon_path = os.path.join(output_path, "game_icon.ico")
            if os.path.exists(game_icon_path):
                try:
                    shutil.copy(game_icon_path, dest_path)
                    self.update_status("✅ Copied game icon as disc icon")
                except Exception as e:
                    self.update_status(f"⚠️ Failed to copy game icon as disc icon: {e}")
                    icon_filename = "game_icon.ico"
            else:
                icon_filename = "game_icon.ico"
        
        # Create autorun.inf content (canonical keys; include extra icon directives for robustness)
        autorun_content = f"""[AutoRun]
Open=setup.exe
Icon={icon_filename}
IconFile={icon_filename}
IconResource={icon_filename},0
IconIndex=0
Label={disc_label}
"""
        
        autorun_path = os.path.join(output_path, "autorun.inf")
        try:
            # Use Windows-1252 encoding and CRLF to match Windows INF expectations
            with open(autorun_path, "w", encoding="cp1252", newline="\r\n") as f:
                f.write(autorun_content)
            self.update_status("✅ Created autorun.inf")
        except Exception as e:
            self.update_status(f"❌ Failed to create autorun.inf: {e}")












    def create_compatibility_test_script(self, output_path):
        """Create automated compatibility test script"""
        
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        game_title = meta.get('Title', 'Game')
        # Escape batch special characters
        for ch in ('&', '|', '>', '<', '^', '(', ')'):
            game_title = game_title.replace(ch, f'^{ch}')

        test_script = f"""@echo off
echo ================================
echo {game_title} - Compatibility Test
echo ================================
echo.

set ERRORS=0
set GAME_EXE_FOUND=0

rem Test 1: Check required files
echo [TEST 1] Checking required files...

rem Check for any game executable (not just game.exe)
for %%f in (*.exe) do (
    if /i not "%%f"=="setup.exe" (
        if /i not "%%f"=="unins000.exe" (
            if /i not "%%f"=="UnityCrashHandler64.exe" (
                echo [OK] Game executable found: %%f
                set GAME_EXE_FOUND=1
            )
        )
    )
)

if %GAME_EXE_FOUND%==0 (
    echo [X] No game executable found
    set /a ERRORS+=1
)

if not exist "setup.exe" (
    echo [X] setup.exe missing
    set /a ERRORS+=1
) else (
    echo [OK] setup.exe found
)

if not exist "autorun.inf" (
    echo [X] autorun.inf missing
    set /a ERRORS+=1
) else (
    echo [OK] autorun.inf found
)

rem Test 2: Check menu systems
echo.
echo [TEST 2] Checking menu systems...
if exist "start_menu.bat" (
    echo [OK] Menu selector found
) else (
    echo [X] Menu selector missing
    set /a ERRORS+=1
)

if exist "menu\\menu.exe" (
    echo [OK] Advanced menu found
) else (
    echo [!] Advanced menu missing (fallbacks available)
)

if exist "menu.bat" (
    echo [OK] Compatibility menu found
) else (
    echo [X] Compatibility menu missing
    set /a ERRORS+=1
)

rem Test 3: Check runtime dependencies
echo.
echo [TEST 3] Checking runtime dependencies...
if exist "vcredist_x64.exe" (
    echo [OK] VC++ x64 runtime included
) else (
    echo [!] VC++ x64 runtime missing
)

if exist "vcredist_x86.exe" (
    echo [OK] VC++ x86 runtime included
) else (
    echo [!] VC++ x86 runtime missing
)

rem Test 4: Check game executable
echo.
echo [TEST 4] Checking game executable...
if %GAME_EXE_FOUND%==1 (
    echo [OK] Game executable is present
) else (
    echo [X] No valid game executable found
    set /a ERRORS+=1
)

rem Test 5: Check disc structure
echo.
echo [TEST 5] Checking disc structure...
if exist "bonus" (
    echo [OK] Bonus content folder found
) else (
    echo [i] No bonus content (optional)
)

if exist "README.txt" (
    echo [OK] README.txt found
) else (
    echo [!] README.txt missing (recommended)
)

rem Results
echo.
echo ================================
if %ERRORS%==0 (
    echo [OK] ALL TESTS PASSED
    echo This disc should work on most systems
    echo ================================
    exit /b 0
) else (
    echo [X] %ERRORS% CRITICAL ERRORS FOUND
    echo This disc may not work on all systems
    echo ================================
    exit /b 1
)
"""
        
        test_path = os.path.join(output_path, "compatibility_test.bat")
        try:
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_script)
            self.update_status("✅ Created compatibility test script")
            
            # Run the test automatically
            self.run_compatibility_test(test_path, output_path)
            
        except Exception as e:
            self.update_status(f"❌ Failed to create test script: {e}")






    def run_compatibility_test(self, test_script_path, output_path):
        """Run the compatibility test and report results"""
        try:
            self.update_status("🧪 Running compatibility test...")
            
            result = subprocess.run(
                [test_script_path],
                cwd=output_path,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=60
            )
            
            # Show test output
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        self.update_status(f"   {line}")
            
            if result.returncode == 0:
                self.update_status("✅ Compatibility test PASSED - disc ready for distribution")
            else:
                self.update_status("❌ Compatibility test FAILED - check errors above")
                
        except Exception as e:
            self.update_status(f"⚠️ Could not run compatibility test: {e}")




    def create_runtime_installer_helper(self, output_path):
        """Create a helper script for runtime installation"""
        helper_content = '''@echo off
title Runtime Installer
color 0A
cls

echo =========================================
echo    Visual C++ Runtime Installer
echo =========================================
echo.

cd /d "%~dp0runtime"

if not exist vcredist_x64.exe if not exist vcredist_x86.exe (
    echo ERROR: Runtime files not found!
    echo.
    echo Please download from:
    echo https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo https://aka.ms/vs/17/release/vc_redist.x86.exe
    echo.
    pause
    exit /b 1
)

echo This will install required runtime components.
echo Administrator privileges may be required.
echo.
pause

if exist vcredist_x64.exe (
    echo.
    echo Installing Visual C++ Runtime x64...
    start /wait vcredist_x64.exe /quiet /norestart
    if errorlevel 1 (
        echo [!] Installation may require admin rights.
        echo [!] Right-click this file and select "Run as administrator"
    ) else (
        echo [OK] x64 runtime installed successfully
    )
)

if exist vcredist_x86.exe (
    echo.
    echo Installing Visual C++ Runtime x86...
    start /wait vcredist_x86.exe /quiet /norestart
    if errorlevel 1 (
        echo [!] Installation may require admin rights.
    ) else (
        echo [OK] x86 runtime installed successfully
    )
)

echo.
echo =========================================
echo Runtime installation complete!
echo You can now run the game.
echo =========================================
echo.
pause
'''
        
        helper_path = os.path.join(output_path, "install_runtimes.bat")
        with open(helper_path, "w") as f:
            f.write(helper_content)
        
        self.update_status("✅ Created runtime installer helper")














    def log_build_event(self, meta, output_path, success=True):
        log_path = os.path.join("build_log.txt")
        from datetime import datetime

        with open(log_path, "a", encoding="utf-8") as f:
            f.write("=== Rialto Build ===\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Title: {meta.get('Title', 'Unknown')}\n")
            f.write(f"Version: {meta.get('Version', 'N/A')}\n")
            f.write(f"Output: {output_path}\n")
            f.write(f"Success: {'Yes' if success else 'No'}\n")
            f.write(f"Features: menu.exe, setup.exe, gallery, readme, iso\n")
            f.write("\n")




    def update_status(self, message):
        """Enhanced status updates with emoji indicators and timestamps"""
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.status_text.configure(state="normal")
        self.status_text.insert("end", formatted_message + "\n")
        
        # Color code based on message type
        if "✅" in message or "Success" in message:
            self.status_text.tag_add("success", f"end-2l", f"end-1l")
        elif "❌" in message or "Error" in message or "Failed" in message:
            self.status_text.tag_add("error", f"end-2l", f"end-1l")
        elif "⚠️" in message or "Warning" in message:
            self.status_text.tag_add("warning", f"end-2l", f"end-1l")
        elif "🔄" in message or "Processing" in message:
            self.status_text.tag_add("processing", f"end-2l", f"end-1l")
        elif "🔒" in message or "sign" in message.lower():
            self.status_text.tag_add("signing", f"end-2l", f"end-1l")
        elif "🔥" in message or "burn" in message.lower():
            self.status_text.tag_add("burn", f"end-2l", f"end-1l")
        elif "💿" in message or "disc" in message.lower() or "ISO" in message:
            self.status_text.tag_add("disc", f"end-2l", f"end-1l")
        
        self.status_text.see("end")
        self.status_text.configure(state="disabled")
        self.status_text.update_idletasks()







    def play_completion_jingle(self):
        jingle_path = asset_path("success.wav")
        if os.path.exists(jingle_path):
            try:
                winsound.PlaySound(jingle_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass




    def burn_to_dvd(self):
        import ctypes
        iso_path = None

        # Auto-select the most recent ISO in the output folder
        for subdir in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            subpath = os.path.join(OUTPUT_DIR, subdir)
            if os.path.isdir(subpath):
                for f in os.listdir(subpath):
                    if f.endswith(".iso"):
                        iso_path = os.path.join(subpath, f)
                        break
                if iso_path:
                    break

        if not iso_path:
            messagebox.showerror("Burn Failed", "No ISO file found to burn.")
            return

        try:
            # Launch ISO with the default Windows disc burner
            os.startfile(iso_path)
            messagebox.showinfo("Burn Started", "The ISO was opened with your default burner software.")
        except Exception as e:
            messagebox.showerror("Burn Failed", f"Could not open ISO with default burner:\n{e}")










    def _click_window(self, event):
        self._x_offset = event.x
        self._y_offset = event.y

    def _move_window(self, event):
        x = event.x_root - self._x_offset
        y = event.y_root - self._y_offset
        self.root.geometry(f"+{x}+{y}")


    def minimize_window(self):
        self.root.withdraw()  # Hide the window (simulate minimize)
        self.root.after(200, self._create_restore_listener)

    def _create_restore_listener(self):
        # Create a small listener window to restore Rialto
        restore_popup = tk.Toplevel()
        restore_popup.title("Restore Rialto")
        restore_popup.geometry("200x60+100+100")
        restore_popup.attributes("-topmost", True)
        restore_popup.configure(bg=self.dark_theme["bg"])

        tk.Label(restore_popup, text="Click to restore Rialto",
                 bg=self.dark_theme["bg"],
                 fg=self.dark_theme["fg"]).pack(pady=5)

        tk.Button(restore_popup, text="Restore",
                  bg=self.dark_theme["button_bg"],
                  fg=self.dark_theme["button_fg"],
                  command=lambda: self._restore_window(restore_popup)).pack(pady=5)

    def _restore_window(self, popup):
        popup.destroy()
        self.root.deiconify()







    def create_pyqt5_menu_launcher(self, menu_dir):
        """Create professional PyQt5 menu with Company of Heroes inspired design"""
        
        meta = {k: self.entries[k].get().strip() for k in self.entries}
        game_title = meta.get('Title', 'Game')
        # Sanitize title for safe embedding in generated Python source
        safe_title = game_title.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")

        # Copy background image/video to menu folder
        bg_source = self.bg_path_var.get()
        bg_type = "none"
        if bg_source and os.path.exists(bg_source):
            # Determine if it's video, gif, or image
            ext = os.path.splitext(bg_source)[1].lower()
            if ext == '.gif':
                bg_dest = os.path.join(menu_dir, "background.gif")
                bg_type = "gif"
            elif ext in ['.mp4', '.avi', '.mov', '.webm']:
                bg_dest = os.path.join(menu_dir, "background.mp4")
                bg_type = "video"
            else:
                bg_dest = os.path.join(menu_dir, "background.jpg")
                bg_type = "image"
            try:
                shutil.copy2(bg_source, bg_dest)
                self.update_status(f"✅ Copied background {bg_type}")
            except OSError:
                pass
        
        # Check for game_logo.png in input folder OR from browse selector
        logo_exists = False
        logo_source = None
        
        # First check if user selected a logo via browse
        if self.logo_path_var.get() and os.path.exists(self.logo_path_var.get()):
            logo_source = self.logo_path_var.get()
        # Otherwise check input folder
        elif self.current_game_path:
            potential_logo = os.path.join(self.current_game_path, "game_logo.png")
            if os.path.exists(potential_logo):
                logo_source = potential_logo
        
        if logo_source:
            logo_dest = os.path.join(menu_dir, "game_logo.png")
            try:
                shutil.copy2(logo_source, logo_dest)
                logo_exists = True
                self.update_status("✅ Copied game logo")
            except OSError:
                pass
        
        # Copy bird logo from Rialto root to menu directory (unless white-labeled)
        if not self.remove_wti_branding.get():
            bird_logo_source = asset_path("bird_logo.PNG")
            if os.path.exists(bird_logo_source):
                bird_logo_dest = os.path.join(menu_dir, "bird_logo.PNG")
                try:
                    shutil.copy2(bird_logo_source, bird_logo_dest)
                    self.update_status("✅ Copied bird logo")
                except Exception as e:
                    self.update_status(f"⚠️ Failed to copy bird logo: {e}")
        
        pyqt5_menu_code = '''import sys
import os
import subprocess
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# Set the AppUserModelID to ensure proper icon in taskbar
try:
    import ctypes
    myappid = 'company.game.''' + safe_title.replace(" ", "") + '''.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

class GameMenu(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # Initialize drag variables
        self.offset = None
        
        # Get the installation directory
        if getattr(sys, 'frozen', False):
            self.game_dir = os.path.dirname(os.path.dirname(sys.executable))
        else:
            self.game_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Set window icon
        icon_path = os.path.join(self.game_dir, "game_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
            # Also set for the application
            QtWidgets.QApplication.instance().setWindowIcon(QtGui.QIcon(icon_path))
        
        # Comprehensive language translations
        self.translations = {
            "Arabic": {
                "play": "العب اللعبة", "bonus": "محتوى إضافي", "uninstall": "إلغاء التثبيت", "exit": "خروج",
                "language": "اللغة:", "error": "خطأ", "warning": "تحذير",
                "game_not_found": "لم يتم العثور على ملف اللعبة القابل للتنفيذ!",
                "bonus_not_found": "لم يتم العثور على المحتوى الإضافي!",
                "uninstaller_not_found": "لم يتم العثور على برنامج إلغاء التثبيت!",
                "confirm_uninstall": "هل أنت متأكد من أنك تريد إلغاء تثبيت هذه اللعبة؟",
                "yes": "نعم", "no": "لا", "cancel": "إلغاء"
            },
            "Bulgarian": {
                "play": "Играй", "bonus": "Бонус съдържание", "uninstall": "Деинсталирай", "exit": "Изход",
                "language": "Език:", "error": "Грешка", "warning": "Предупреждение",
                "game_not_found": "Изпълнимият файл на играта не е намерен!",
                "bonus_not_found": "Бонус съдържанието не е намерено!",
                "uninstaller_not_found": "Деинсталаторът не е намерен!",
                "confirm_uninstall": "Сигурни ли сте, че искате да деинсталирате тази игра?",
                "yes": "Да", "no": "Не", "cancel": "Отказ"
            },
            "Chinese (Simplified)": {
                "play": "开始游戏", "bonus": "额外内容", "uninstall": "卸载", "exit": "退出",
                "language": "语言:", "error": "错误", "warning": "警告",
                "game_not_found": "找不到游戏可执行文件！",
                "bonus_not_found": "找不到额外内容！",
                "uninstaller_not_found": "找不到卸载程序！",
                "confirm_uninstall": "您确定要卸载此游戏吗？",
                "yes": "是", "no": "否", "cancel": "取消"
            },
            "Chinese (Traditional)": {
                "play": "開始遊戲", "bonus": "額外內容", "uninstall": "移除", "exit": "結束",
                "language": "語言:", "error": "錯誤", "warning": "警告",
                "game_not_found": "找不到遊戲執行檔！",
                "bonus_not_found": "找不到額外內容！",
                "uninstaller_not_found": "找不到移除程式！",
                "confirm_uninstall": "您確定要移除此遊戲嗎？",
                "yes": "是", "no": "否", "cancel": "取消"
            },
            "Croatian": {
                "play": "Igraj", "bonus": "Bonus sadržaj", "uninstall": "Deinstaliraj", "exit": "Izlaz",
                "language": "Jezik:", "error": "Greška", "warning": "Upozorenje",
                "game_not_found": "Izvršna datoteka igre nije pronađena!",
                "bonus_not_found": "Bonus sadržaj nije pronađen!",
                "uninstaller_not_found": "Deinstalater nije pronađen!",
                "confirm_uninstall": "Jeste li sigurni da želite deinstalirati ovu igru?",
                "yes": "Da", "no": "Ne", "cancel": "Otkaži"
            },
            "Czech": {
                "play": "Hrát", "bonus": "Bonusový obsah", "uninstall": "Odinstalovat", "exit": "Ukončit",
                "language": "Jazyk:", "error": "Chyba", "warning": "Varování",
                "game_not_found": "Spustitelný soubor hry nebyl nalezen!",
                "bonus_not_found": "Bonusový obsah nebyl nalezen!",
                "uninstaller_not_found": "Odinstalátor nebyl nalezen!",
                "confirm_uninstall": "Jste si jisti, že chcete tuto hru odinstalovat?",
                "yes": "Ano", "no": "Ne", "cancel": "Zrušit"
            },
            "Danish": {
                "play": "Spil", "bonus": "Bonusindhold", "uninstall": "Afinstaller", "exit": "Afslut",
                "language": "Sprog:", "error": "Fejl", "warning": "Advarsel",
                "game_not_found": "Spil eksekverbar fil ikke fundet!",
                "bonus_not_found": "Bonusindhold ikke fundet!",
                "uninstaller_not_found": "Afinstallationsprogram ikke fundet!",
                "confirm_uninstall": "Er du sikker på, at du vil afinstallere dette spil?",
                "yes": "Ja", "no": "Nej", "cancel": "Annuller"
            },
            "Dutch": {
                "play": "Spelen", "bonus": "Bonus Inhoud", "uninstall": "Verwijderen", "exit": "Afsluiten",
                "language": "Taal:", "error": "Fout", "warning": "Waarschuwing",
                "game_not_found": "Game uitvoerbaar bestand niet gevonden!",
                "bonus_not_found": "Bonus inhoud niet gevonden!",
                "uninstaller_not_found": "Verwijderprogramma niet gevonden!",
                "confirm_uninstall": "Weet je zeker dat je dit spel wilt verwijderen?",
                "yes": "Ja", "no": "Nee", "cancel": "Annuleren"
            },
            "English": {
                "play": "Play Game", "bonus": "Bonus Content", "uninstall": "Uninstall", "exit": "Exit",
                "language": "Language:", "error": "Error", "warning": "Warning",
                "game_not_found": "Game executable not found!",
                "bonus_not_found": "Bonus content not found!",
                "uninstaller_not_found": "Uninstaller not found!",
                "confirm_uninstall": "Are you sure you want to uninstall this game?",
                "yes": "Yes", "no": "No", "cancel": "Cancel"
            },
            "Finnish": {
                "play": "Pelaa", "bonus": "Bonussisältö", "uninstall": "Poista asennus", "exit": "Poistu",
                "language": "Kieli:", "error": "Virhe", "warning": "Varoitus",
                "game_not_found": "Pelin suoritettava tiedosto ei löytynyt!",
                "bonus_not_found": "Bonussisältöä ei löytynyt!",
                "uninstaller_not_found": "Asennuksen poisto-ohjelmaa ei löytynyt!",
                "confirm_uninstall": "Oletko varma, että haluat poistaa tämän pelin asennuksen?",
                "yes": "Kyllä", "no": "Ei", "cancel": "Peruuta"
            },
            "French": {
                "play": "Jouer", "bonus": "Contenu Bonus", "uninstall": "Désinstaller", "exit": "Quitter",
                "language": "Langue:", "error": "Erreur", "warning": "Avertissement",
                "game_not_found": "Exécutable du jeu introuvable!",
                "bonus_not_found": "Contenu bonus introuvable!",
                "uninstaller_not_found": "Désinstallateur introuvable!",
                "confirm_uninstall": "Êtes-vous sûr de vouloir désinstaller ce jeu?",
                "yes": "Oui", "no": "Non", "cancel": "Annuler"
            },
            "German": {
                "play": "Spielen", "bonus": "Bonusinhalte", "uninstall": "Deinstallieren", "exit": "Beenden",
                "language": "Sprache:", "error": "Fehler", "warning": "Warnung",
                "game_not_found": "Spiel-Datei nicht gefunden!",
                "bonus_not_found": "Bonusinhalte nicht gefunden!",
                "uninstaller_not_found": "Deinstallationsprogramm nicht gefunden!",
                "confirm_uninstall": "Sind Sie sicher, dass Sie dieses Spiel deinstallieren möchten?",
                "yes": "Ja", "no": "Nein", "cancel": "Abbrechen"
            },
            "Greek": {
                "play": "Παίξε", "bonus": "Bonus Περιεχόμενο", "uninstall": "Απεγκατάσταση", "exit": "Έξοδος",
                "language": "Γλώσσα:", "error": "Σφάλμα", "warning": "Προειδοποίηση",
                "game_not_found": "Το εκτελέσιμο αρχείο του παιχνιδιού δεν βρέθηκε!",
                "bonus_not_found": "Το bonus περιεχόμενο δεν βρέθηκε!",
                "uninstaller_not_found": "Το πρόγραμμα απεγκατάστασης δεν βρέθηκε!",
                "confirm_uninstall": "Είστε σίγουροι ότι θέλετε να απεγκαταστήσετε αυτό το παιχνίδι?",
                "yes": "Ναι", "no": "Όχι", "cancel": "Ακύρωση"
            },
            "Hebrew": {
                "play": "שחק", "bonus": "תוכן בונוס", "uninstall": "הסר התקנה", "exit": "יציאה",
                "language": "שפה:", "error": "שגיאה", "warning": "אזהרה",
                "game_not_found": "קובץ המשחק לא נמצא!",
                "bonus_not_found": "תוכן הבונוס לא נמצא!",
                "uninstaller_not_found": "תוכנת ההסרה לא נמצאה!",
                "confirm_uninstall": "האם אתה בטוח שברצונך להסיר את המשחק?",
                "yes": "כן", "no": "לא", "cancel": "בטל"
            },
            "Hindi": {
                "play": "खेल खेलें", "bonus": "बोनस सामग्री", "uninstall": "अनइंस्टॉल", "exit": "बाहर निकलें",
                "language": "भाषा:", "error": "त्रुटि", "warning": "चेतावनी",
                "game_not_found": "गेम एक्जीक्यूटेबल नहीं मिला!",
                "bonus_not_found": "बोनस सामग्री नहीं मिली!",
                "uninstaller_not_found": "अनइंस्टॉलर नहीं मिला!",
                "confirm_uninstall": "क्या आप वाकई इस गेम को अनइंस्टॉल करना चाहते हैं?",
                "yes": "हाँ", "no": "नहीं", "cancel": "रद्द करें"
            },
            "Hungarian": {
                "play": "Játék", "bonus": "Bónusz tartalom", "uninstall": "Eltávolítás", "exit": "Kilépés",
                "language": "Nyelv:", "error": "Hiba", "warning": "Figyelmeztetés",
                "game_not_found": "A játék futtatható fájlja nem található!",
                "bonus_not_found": "A bónusz tartalom nem található!",
                "uninstaller_not_found": "Az eltávolító nem található!",
                "confirm_uninstall": "Biztos benne, hogy el szeretné távolítani ezt a játékot?",
                "yes": "Igen", "no": "Nem", "cancel": "Mégse"
            },
            "Indonesian": {
                "play": "Main Game", "bonus": "Konten Bonus", "uninstall": "Hapus Instalan", "exit": "Keluar",
                "language": "Bahasa:", "error": "Kesalahan", "warning": "Peringatan",
                "game_not_found": "File game tidak ditemukan!",
                "bonus_not_found": "Konten bonus tidak ditemukan!",
                "uninstaller_not_found": "Uninstaller tidak ditemukan!",
                "confirm_uninstall": "Apakah Anda yakin ingin menghapus game ini?",
                "yes": "Ya", "no": "Tidak", "cancel": "Batal"
            },
            "Italian": {
                "play": "Gioca", "bonus": "Contenuti Bonus", "uninstall": "Disinstalla", "exit": "Esci",
                "language": "Lingua:", "error": "Errore", "warning": "Avvertimento",
                "game_not_found": "File eseguibile del gioco non trovato!",
                "bonus_not_found": "Contenuti bonus non trovati!",
                "uninstaller_not_found": "Programma di disinstallazione non trovato!",
                "confirm_uninstall": "Sei sicuro di voler disinstallare questo gioco?",
                "yes": "Sì", "no": "No", "cancel": "Annulla"
            },
            "Japanese": {
                "play": "ゲームを開始", "bonus": "ボーナスコンテンツ", "uninstall": "アンインストール", "exit": "終了",
                "language": "言語:", "error": "エラー", "warning": "警告",
                "game_not_found": "ゲームファイルが見つかりません！",
                "bonus_not_found": "ボーナスコンテンツが見つかりません！",
                "uninstaller_not_found": "アンインストーラーが見つかりません！",
                "confirm_uninstall": "このゲームをアンインストールしてもよろしいですか？",
                "yes": "はい", "no": "いいえ", "cancel": "キャンセル"
            },
            "Korean": {
                "play": "게임 시작", "bonus": "보너스 콘텐츠", "uninstall": "제거", "exit": "종료",
                "language": "언어:", "error": "오류", "warning": "경고",
                "game_not_found": "게임 실행 파일을 찾을 수 없습니다!",
                "bonus_not_found": "보너스 콘텐츠를 찾을 수 없습니다!",
                "uninstaller_not_found": "제거 프로그램을 찾을 수 없습니다!",
                "confirm_uninstall": "이 게임을 제거하시겠습니까?",
                "yes": "예", "no": "아니요", "cancel": "취소"
            },
            "Norwegian": {
                "play": "Spill", "bonus": "Bonusinnhold", "uninstall": "Avinstaller", "exit": "Avslutt",
                "language": "Språk:", "error": "Feil", "warning": "Advarsel",
                "game_not_found": "Spillkjørbar fil ikke funnet!",
                "bonus_not_found": "Bonusinnhold ikke funnet!",
                "uninstaller_not_found": "Avinstallerer ikke funnet!",
                "confirm_uninstall": "Er du sikker på at du vil avinstallere dette spillet?",
                "yes": "Ja", "no": "Nei", "cancel": "Avbryt"
            },
            "Polish": {
                "play": "Graj", "bonus": "Zawartość Bonusowa", "uninstall": "Odinstaluj", "exit": "Wyjście",
                "language": "Język:", "error": "Błąd", "warning": "Ostrzeżenie",
                "game_not_found": "Plik wykonywalny gry nie został znaleziony!",
                "bonus_not_found": "Zawartość bonusowa nie została znaleziona!",
                "uninstaller_not_found": "Program dezinstalacyjny nie został znaleziony!",
                "confirm_uninstall": "Czy na pewno chcesz odinstalować tę grę?",
                "yes": "Tak", "no": "Nie", "cancel": "Anuluj"
            },
            "Portuguese": {
                "play": "Jogar", "bonus": "Conteúdo Bônus", "uninstall": "Desinstalar", "exit": "Sair",
                "language": "Idioma:", "error": "Erro", "warning": "Aviso",
                "game_not_found": "Executável do jogo não encontrado!",
                "bonus_not_found": "Conteúdo bônus não encontrado!",
                "uninstaller_not_found": "Desinstalador não encontrado!",
                "confirm_uninstall": "Tem certeza de que deseja desinstalar este jogo?",
                "yes": "Sim", "no": "Não", "cancel": "Cancelar"
            },
            "Portuguese (Brazil)": {
                "play": "Jogar", "bonus": "Conteúdo Bônus", "uninstall": "Desinstalar", "exit": "Sair",
                "language": "Idioma:", "error": "Erro", "warning": "Aviso",
                "game_not_found": "Executável do jogo não encontrado!",
                "bonus_not_found": "Conteúdo bônus não encontrado!",
                "uninstaller_not_found": "Desinstalador não encontrado!",
                "confirm_uninstall": "Tem certeza de que deseja desinstalar este jogo?",
                "yes": "Sim", "no": "Não", "cancel": "Cancelar"
            },
            "Romanian": {
                "play": "Joacă", "bonus": "Conținut Bonus", "uninstall": "Dezinstalează", "exit": "Ieșire",
                "language": "Limba:", "error": "Eroare", "warning": "Avertisment",
                "game_not_found": "Fișierul executabil al jocului nu a fost găsit!",
                "bonus_not_found": "Conținutul bonus nu a fost găsit!",
                "uninstaller_not_found": "Dezinstalatorul nu a fost găsit!",
                "confirm_uninstall": "Ești sigur că vrei să dezinstalezi acest joc?",
                "yes": "Da", "no": "Nu", "cancel": "Anulează"
            },
            "Russian": {
                "play": "Играть", "bonus": "Бонусный контент", "uninstall": "Удалить", "exit": "Выход",
                "language": "Язык:", "error": "Ошибка", "warning": "Предупреждение",
                "game_not_found": "Исполняемый файл игры не найден!",
                "bonus_not_found": "Бонусный контент не найден!",
                "uninstaller_not_found": "Программа удаления не найдена!",
                "confirm_uninstall": "Вы уверены, что хотите удалить эту игру?",
                "yes": "Да", "no": "Нет", "cancel": "Отмена"
            },
            "Serbian": {
                "play": "Igraj", "bonus": "Bonus sadržaj", "uninstall": "Deinstaliraj", "exit": "Izlaz",
                "language": "Jezik:", "error": "Greška", "warning": "Upozorenje",
                "game_not_found": "Izvršna datoteka igre nije pronađena!",
                "bonus_not_found": "Bonus sadržaj nije pronađen!",
                "uninstaller_not_found": "Deinstalater nije pronađen!",
                "confirm_uninstall": "Da li ste sigurni da želite da deinstalirate ovu igru?",
                "yes": "Da", "no": "Ne", "cancel": "Otkaži"
            },
            "Slovak": {
                "play": "Hrať", "bonus": "Bonusový obsah", "uninstall": "Odinštalovať", "exit": "Ukončiť",
                "language": "Jazyk:", "error": "Chyba", "warning": "Varovanie",
                "game_not_found": "Spustiteľný súbor hry nebol nájdený!",
                "bonus_not_found": "Bonusový obsah nebol nájdený!",
                "uninstaller_not_found": "Odinštalátor nebol nájdený!",
                "confirm_uninstall": "Ste si istí, že chcete odinštalovať túto hru?",
                "yes": "Áno", "no": "Nie", "cancel": "Zrušiť"
            },
            "Spanish": {
                "play": "Jugar", "bonus": "Contenido Extra", "uninstall": "Desinstalar", "exit": "Salir",
                "language": "Idioma:", "error": "Error", "warning": "Advertencia",
                "game_not_found": "¡Ejecutable del juego no encontrado!",
                "bonus_not_found": "¡Contenido extra no encontrado!",
                "uninstaller_not_found": "¡Desinstalador no encontrado!",
                "confirm_uninstall": "¿Estás seguro de que quieres desinstalar este juego?",
                "yes": "Sí", "no": "No", "cancel": "Cancelar"
            },
            "Swedish": {
                "play": "Spela", "bonus": "Bonusinnehåll", "uninstall": "Avinstallera", "exit": "Avsluta",
                "language": "Språk:", "error": "Fel", "warning": "Varning",
                "game_not_found": "Spelkörbar fil hittades inte!",
                "bonus_not_found": "Bonusinnehåll hittades inte!",
                "uninstaller_not_found": "Avinstallerare hittades inte!",
                "confirm_uninstall": "Är du säker på att du vill avinstallera detta spel?",
                "yes": "Ja", "no": "Nej", "cancel": "Avbryt"
            },
            "Thai": {
                "play": "เล่นเกม", "bonus": "เนื้อหาโบนัส", "uninstall": "ถอนการติดตั้ง", "exit": "ออก",
                "language": "ภาษา:", "error": "ข้อผิดพลาด", "warning": "คำเตือน",
                "game_not_found": "ไม่พบไฟล์เกมที่สามารถเรียกใช้ได้!",
                "bonus_not_found": "ไม่พบเนื้อหาโบนัส!",
                "uninstaller_not_found": "ไม่พบโปรแกรมถอนการติดตั้ง!",
                "confirm_uninstall": "คุณแน่ใจหรือว่าต้องการถอนการติดตั้งเกมนี้?",
                "yes": "ใช่", "no": "ไม่", "cancel": "ยกเลิก"
            },
            "Turkish": {
                "play": "Oyunu Oyna", "bonus": "Bonus İçerik", "uninstall": "Kaldır", "exit": "Çıkış",
                "language": "Dil:", "error": "Hata", "warning": "Uyarı",
                "game_not_found": "Oyun yürütülebilir dosyası bulunamadı!",
                "bonus_not_found": "Bonus içerik bulunamadı!",
                "uninstaller_not_found": "Kaldırıcı bulunamadı!",
                "confirm_uninstall": "Bu oyunu kaldırmak istediğinizden emin misiniz?",
                "yes": "Evet", "no": "Hayır", "cancel": "İptal"
            },
            "Ukrainian": {
                "play": "Грати", "bonus": "Бонусний контент", "uninstall": "Видалити", "exit": "Вихід",
                "language": "Мова:", "error": "Помилка", "warning": "Попередження",
                "game_not_found": "Виконуваний файл гри не знайдено!",
                "bonus_not_found": "Бонусний контент не знайдено!",
                "uninstaller_not_found": "Програму видалення не знайдено!",
                "confirm_uninstall": "Ви впевнені, що хочете видалити цю гру?",
                "yes": "Так", "no": "Ні", "cancel": "Скасувати"
            },
            "Vietnamese": {
                "play": "Chơi Game", "bonus": "Nội dung Bonus", "uninstall": "Gỡ cài đặt", "exit": "Thoát",
                "language": "Ngôn ngữ:", "error": "Lỗi", "warning": "Cảnh báo",
                "game_not_found": "Không tìm thấy file thực thi game!",
                "bonus_not_found": "Không tìm thấy nội dung bonus!",
                "uninstaller_not_found": "Không tìm thấy chương trình gỡ cài đặt!",
                "confirm_uninstall": "Bạn có chắc chắn muốn gỡ cài đặt game này?",
                "yes": "Có", "no": "Không", "cancel": "Hủy"
            }
        }
        
        self.current_lang = "English"  # Default to English
        self.media_player = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("''' + safe_title + '''")
        
        # 4K scaling support
        app = QtWidgets.QApplication.instance()
        screen = app.primaryScreen()
        screen_dpi = screen.logicalDotsPerInch()
        base_dpi = 96
        self.scale_factor = max(1.0, screen_dpi / base_dpi)
        
        # Scale window size for 4K displays
        base_width, base_height = 1280, 720
        scaled_width = int(base_width * self.scale_factor)
        scaled_height = int(base_height * self.scale_factor)
        
        self.setFixedSize(scaled_width, scaled_height)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        
        # Create main layout
        self.main_layout = QtWidgets.QStackedLayout()
        self.setLayout(self.main_layout)
        
        # Background widget
        self.bg_widget = QtWidgets.QWidget()
        self.main_layout.addWidget(self.bg_widget)
        
        # Set dark background color as default
        self.bg_widget.setStyleSheet("background-color: #1a1a1a;")
        
        # Check for video/gif background first
        video_path = os.path.join(os.path.dirname(__file__), "background.mp4")
        gif_path = os.path.join(os.path.dirname(__file__), "background.gif")
        
        if not os.path.exists(video_path) and getattr(sys, 'frozen', False):
            video_path = os.path.join(os.path.dirname(sys.executable), "background.mp4")
        if not os.path.exists(gif_path) and getattr(sys, 'frozen', False):
            gif_path = os.path.join(os.path.dirname(sys.executable), "background.gif")
        
        video_loaded = False
        
        # Try GIF first (more compatible)
        if os.path.exists(gif_path):
            try:
                self.movie_label = QtWidgets.QLabel(self.bg_widget)
                self.movie_label.setGeometry(0, 0, scaled_width, scaled_height)
                self.movie_label.setScaledContents(True)
                
                self.movie = QtGui.QMovie(gif_path)
                self.movie.setScaledSize(QtCore.QSize(scaled_width, scaled_height))
                self.movie_label.setMovie(self.movie)
                self.movie.start()
                video_loaded = True
            except Exception:
                video_loaded = False
        
        # Try video if no GIF
        if not video_loaded and os.path.exists(video_path):
            try:
                # Video background
                self.video_widget = QVideoWidget(self.bg_widget)
                self.video_widget.setGeometry(0, 0, scaled_width, scaled_height)
                
                self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
                self.media_player.setVideoOutput(self.video_widget)
                
                # Try to load video with explicit format hint
                media_content = QMediaContent(QtCore.QUrl.fromLocalFile(video_path))
                self.media_player.setMedia(media_content)
                self.media_player.setVolume(0)  # Mute video
                
                # Set up error handling
                self.media_player.error.connect(lambda: None)
                
                # Loop video
                self.media_player.mediaStatusChanged.connect(self.handle_media_status)
                self.media_player.setPosition(0)
                self.media_player.play()
                video_loaded = True
            except Exception:
                video_loaded = False
        
        if not video_loaded:
            # Image background fallback
            bg_path = os.path.join(os.path.dirname(__file__), "background.jpg")
            if not os.path.exists(bg_path) and getattr(sys, 'frozen', False):
                bg_path = os.path.join(os.path.dirname(sys.executable), "background.jpg")
            
            if os.path.exists(bg_path):
                self.background = QtWidgets.QLabel(self.bg_widget)
                pixmap = QtGui.QPixmap(bg_path).scaled(scaled_width, scaled_height, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                self.background.setPixmap(pixmap)
                self.background.setGeometry(0, 0, scaled_width, scaled_height)
        
        # Add dark overlay for better text contrast (more subtle)
        overlay = QtWidgets.QWidget(self.bg_widget)
        overlay.setGeometry(0, 0, scaled_width, scaled_height)
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 30);")  # Reduced from 50 to 30
        
        # Main container for UI elements
        ui_container = QtWidgets.QWidget(self.bg_widget)
        ui_container.setGeometry(0, 0, scaled_width, scaled_height)
        ui_container.setStyleSheet("background-color: transparent;")
        
        main_layout = QtWidgets.QHBoxLayout(ui_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Left side - Menu buttons (neutral color scheme)
        left_panel = QtWidgets.QWidget()
        left_panel.setFixedWidth(int(480 * self.scale_factor))
        left_panel.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(15, 15, 15, 220),
                    stop: 0.6 rgba(20, 20, 20, 200),
                    stop: 0.8 rgba(20, 20, 20, 140),
                    stop: 1 rgba(20, 20, 20, 0));
                border: none;
                margin: 0px;
                padding: 0px;
            }
        """)
        
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(int(40 * self.scale_factor), int(50 * self.scale_factor), int(50 * self.scale_factor), int(50 * self.scale_factor))
        left_layout.setSpacing(0)
        
        # Game title or logo
        logo_path = None
        
        # Look for game logo in current directory first (most up-to-date)
        potential_paths = []
        
        if getattr(sys, 'frozen', False):
            # Running as compiled exe - check exe directory first
            exe_dir = os.path.dirname(sys.executable)
            potential_paths = [
                os.path.join(exe_dir, "game_logo.png"),  # Same dir as executable
                os.path.join(os.path.dirname(exe_dir), "game_logo.png"),  # Parent dir
            ]
        else:
            # Running as script - check script directory
            script_dir = os.path.dirname(__file__)
            potential_paths = [
                os.path.join(script_dir, "game_logo.png"),
            ]
        
        # Find the first existing logo file
        for path in potential_paths:
            if os.path.exists(path):
                logo_path = path
                break
        
        # logo work
        if logo_path and os.path.exists(logo_path):
            try:
                logo_label = QtWidgets.QLabel()
                logo_pixmap = QtGui.QPixmap(logo_path)
                
                # Check if pixmap loaded successfully
                if not logo_pixmap.isNull():
                    # Check if logo is square (or nearly square)
                    logo_size = logo_pixmap.size()
                    width_ratio = logo_size.width() / logo_size.height() if logo_size.height() > 0 else 1.0
                    is_square = 0.8 <= width_ratio <= 1.2  # Allow some tolerance for "square"
                    
                    # Scale logo to fit properly within available space
                    max_width = int(350 * self.scale_factor)  # Base size
                    max_height = int(120 * self.scale_factor)  # Base size
                    
                    # If square, increase size by 2x
                    if is_square:
                        max_width *= 2
                        max_height *= 2
                    
                    scaled_logo = logo_pixmap.scaled(max_width, max_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    logo_label.setPixmap(scaled_logo)
                    logo_label.setStyleSheet("background: transparent;")
                    logo_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
                    left_layout.addWidget(logo_label)
                else:
                    raise Exception("Failed to load pixmap")
            except Exception:
                pass
                # Fallback to text
                title_label = QtWidgets.QLabel("''' + safe_title.upper() + '''")
                title_label.setStyleSheet("""
                    color: white;
                    font-size: """ + str(int(36 * self.scale_factor)) + """px;
                    font-weight: bold;
                    letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                    margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                    background: transparent;
                """)
                title_label.setWordWrap(True)
                left_layout.addWidget(title_label)
        else:
            # No logo found, use text
            title_label = QtWidgets.QLabel("''' + safe_title.upper() + '''")
            title_label.setStyleSheet("""
                color: white;
                font-size: """ + str(int(36 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(3 * self.scale_factor)) + """px;
                margin-bottom: """ + str(int(20 * self.scale_factor)) + """px;
                background: transparent;
            """)
            title_label.setWordWrap(True)
            left_layout.addWidget(title_label)
        
        # Add some spacing
        left_layout.addSpacing(int(40 * self.scale_factor))
        
        # Menu buttons - Neutral white/gray color scheme
        button_style_template = """
            QPushButton {{
                background-color: transparent;
                color: {color};
                border: none;
                border-left: {border_width}px solid {border_color};
                text-align: left;
                padding: """ + str(int(15 * self.scale_factor)) + """px 0px """ + str(int(15 * self.scale_factor)) + """px """ + str(int(20 * self.scale_factor)) + """px;
                font-size: """ + str(int(22 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(2 * self.scale_factor)) + """px;
                margin: """ + str(int(5 * self.scale_factor)) + """px 0px;
            }}
            QPushButton:hover {{
                color: white;
                border-left: """ + str(int(4 * self.scale_factor)) + """px solid #ffffff;
                background-color: rgba(255, 255, 255, 10);
                padding-left: """ + str(int(30 * self.scale_factor)) + """px;
            }}
            QPushButton:pressed {{
                color: #cccccc;
                padding-left: """ + str(int(35 * self.scale_factor)) + """px;
            }}
        """
        
        # Create menu buttons with neutral colors
        self.play_btn = QtWidgets.QPushButton("PLAY GAME")
        self.play_btn.clicked.connect(self.launch_game)
        self.play_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(button_style_template.format(
            color="#ffffff", border_width="3", border_color="#ffffff"
        ))
        
        # Only show bonus button if bonus folder exists
        bonus_exists = False
        bonus_paths = [
            os.path.join(self.game_dir, "bonus"),
            os.path.join(self.game_dir, "BONUS"),
            os.path.join(self.game_dir, "Bonus")
        ]
        for bonus_path in bonus_paths:
            if os.path.exists(bonus_path) and os.path.isdir(bonus_path):
                bonus_exists = True
                break
        
        if bonus_exists:
            self.bonus_btn = QtWidgets.QPushButton("BONUS CONTENT")
            self.bonus_btn.clicked.connect(self.open_bonus)
            self.bonus_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self.bonus_btn.setStyleSheet(button_style_template.format(
                color="#dddddd", border_width="2", border_color="transparent"
            ))
        
        self.uninstall_btn = QtWidgets.QPushButton("UNINSTALL")
        self.uninstall_btn.clicked.connect(self.uninstall_game)
        self.uninstall_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.uninstall_btn.setStyleSheet(button_style_template.format(
            color="#cccccc", border_width="3", border_color="transparent"
        ))
        
        self.exit_btn = QtWidgets.QPushButton("EXIT")
        self.exit_btn.clicked.connect(self.close)
        self.exit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.exit_btn.setStyleSheet(button_style_template.format(
            color="#cccccc", border_width="3", border_color="transparent"
        ))
        
        # Add buttons to layout conditionally
        buttons_to_add = [self.play_btn]
        if bonus_exists:
            buttons_to_add.append(self.bonus_btn)
        buttons_to_add.extend([self.uninstall_btn, self.exit_btn])
        
        for btn in buttons_to_add:
            left_layout.addWidget(btn)
        
        left_layout.addStretch()
        
        # Language selector at bottom
        lang_container = QtWidgets.QWidget()
        lang_container.setStyleSheet("background: transparent;")
        lang_layout = QtWidgets.QHBoxLayout(lang_container)
        lang_layout.setContentsMargins(int(20 * self.scale_factor), int(10 * self.scale_factor), 0, int(30 * self.scale_factor))
        
        self.lang_label = QtWidgets.QLabel("Menu Language:")
        self.lang_label.setStyleSheet("""
            color: #888888;
            font-size: """ + str(int(11 * self.scale_factor)) + """px;
            font-weight: bold;
            letter-spacing: """ + str(int(2 * self.scale_factor)) + """px;
            background: transparent;
        """)
        
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems(sorted(list(self.translations.keys())))
        self.lang_combo.setCurrentText("English")
        self.lang_combo.currentTextChanged.connect(self.change_language)
        self.lang_combo.setFixedWidth(int(180 * self.scale_factor))
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 40, 40, 180);
                color: #ffffff;
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 20);
                border-radius: 0px;
                padding: """ + str(int(8 * self.scale_factor)) + """px """ + str(int(15 * self.scale_factor)) + """px;
                font-size: """ + str(int(12 * self.scale_factor)) + """px;
                font-weight: bold;
                letter-spacing: """ + str(int(1 * self.scale_factor)) + """px;
            }
            QComboBox::drop-down {
                border: none;
                width: """ + str(int(30 * self.scale_factor)) + """px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: """ + str(int(4 * self.scale_factor)) + """px solid transparent;
                border-right: """ + str(int(4 * self.scale_factor)) + """px solid transparent;
                border-top: """ + str(int(5 * self.scale_factor)) + """px solid #ffffff;
                margin-right: """ + str(int(10 * self.scale_factor)) + """px;
            }
            QComboBox:hover {
                background-color: rgba(60, 60, 60, 200);
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 40);
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 30, 30, 240);
                color: #ffffff;
                selection-background-color: rgba(255, 255, 255, 30);
                selection-color: white;
                border: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 40);
                padding: """ + str(int(5 * self.scale_factor)) + """px;
            }
            QComboBox QAbstractItemView::item {
                padding: """ + str(int(8 * self.scale_factor)) + """px;
                border-bottom: """ + str(int(1 * self.scale_factor)) + """px solid rgba(255, 255, 255, 10);
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: rgba(60, 60, 60, 200);
            }
        """)
        
        lang_layout.addWidget(self.lang_label)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        
        # Disable tab focus for language selector to prevent keyboard navigation
        self.lang_combo.setFocusPolicy(QtCore.Qt.NoFocus)
        
        left_layout.addWidget(lang_container)
        
        main_layout.addWidget(left_panel)
        main_layout.addStretch()
        
        # Add close button in top-right
        close_btn = QtWidgets.QPushButton("×", ui_container)
        close_btn.setGeometry(int(1225 * self.scale_factor), int(15 * self.scale_factor), int(40 * self.scale_factor), int(40 * self.scale_factor))
        close_btn.clicked.connect(self.close)
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666666;
                border: """ + str(int(2 * self.scale_factor)) + """px solid #666666;
                border-radius: """ + str(int(20 * self.scale_factor)) + """px;
                font-size: """ + str(int(28 * self.scale_factor)) + """px;
                font-weight: bold;
                text-align: center;
                padding-bottom: """ + str(int(4 * self.scale_factor)) + """px;
            }
            QPushButton:hover {
                color: white;
                border-color: white;
                background-color: rgba(255, 255, 255, 20);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 40);
            }
        """)
        
        # Add company logo in bottom-right
        company_logo_path = None
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            potential_paths = [
                os.path.join(exe_dir, "company_logo.png"),
                os.path.join(os.path.dirname(exe_dir), "company_logo.png"),
            ]
            for path in potential_paths:
                if os.path.exists(path):
                    company_logo_path = path
                    break
        else:
            company_logo_path = os.path.join(os.path.dirname(__file__), "company_logo.png")
            if not os.path.exists(company_logo_path):
                company_logo_path = None
        
        # Add company logo and bird logo to bottom right (increased space by 1.25x)
        logo_spacing = int(25 * self.scale_factor)  # Space between logos
        right_margin = int(25 * self.scale_factor)  # Right margin (increased from 20)
        bottom_margin = int(25 * self.scale_factor)  # Bottom margin (increased from 20)
        
        # Scale logo sizes by 1.25x
        max_logo_width = int(187 * self.scale_factor)  # 150 * 1.25
        max_logo_height = int(94 * self.scale_factor)   # 75 * 1.25
        
        # Load bird logo first (rightmost position)
        # Look for bird logo in multiple locations
        bird_logo_path = None
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            potential_bird_paths = [
                os.path.join(exe_dir, "bird_logo.PNG"),
                os.path.join(os.path.dirname(exe_dir), "bird_logo.PNG"),
            ]
            for path in potential_bird_paths:
                if os.path.exists(path):
                    bird_logo_path = path
                    break
        else:
            bird_logo_path = os.path.join(os.path.dirname(__file__), "bird_logo.PNG")
            if not os.path.exists(bird_logo_path):
                bird_logo_path = None
        
        bird_logo_width = 0
        
        if bird_logo_path and os.path.exists(bird_logo_path):
            try:
                bird_logo_label = QtWidgets.QLabel(ui_container)
                bird_logo_pixmap = QtGui.QPixmap(bird_logo_path)
                if not bird_logo_pixmap.isNull():
                    scaled_bird_logo = bird_logo_pixmap.scaled(max_logo_width, max_logo_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    bird_logo_label.setPixmap(scaled_bird_logo)
                    bird_logo_label.setStyleSheet("background: transparent;")
                    bird_logo_width = scaled_bird_logo.width()
                    
                    # Position bird logo at rightmost position
                    bird_x = scaled_width - bird_logo_width - right_margin
                    bird_y = scaled_height - max_logo_height - bottom_margin
                    bird_logo_label.setGeometry(bird_x, bird_y, bird_logo_width, max_logo_height)
            except Exception:
                pass
        
        # Load company logo (to the left of bird logo)
        if company_logo_path and os.path.exists(company_logo_path):
            try:
                company_logo_label = QtWidgets.QLabel(ui_container)
                company_logo_pixmap = QtGui.QPixmap(company_logo_path)
                if not company_logo_pixmap.isNull():
                    scaled_company_logo = company_logo_pixmap.scaled(max_logo_width, max_logo_height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    company_logo_label.setPixmap(scaled_company_logo)
                    company_logo_label.setStyleSheet("background: transparent;")
                    company_logo_width = scaled_company_logo.width()
                    
                    # Position company logo to the left of bird logo
                    if bird_logo_width > 0:
                        # Bird logo exists, position company logo to its left
                        company_x = scaled_width - bird_logo_width - logo_spacing - company_logo_width - right_margin
                    else:
                        # No bird logo, position company logo at original position
                        company_x = scaled_width - company_logo_width - right_margin
                    
                    company_y = scaled_height - max_logo_height - bottom_margin
                    company_logo_label.setGeometry(company_x, company_y, company_logo_width, max_logo_height)
            except Exception:
                pass
        
        # Add copyright text from Rialto configuration
        try:
            # Check for copyright text from config (purely user-driven)
            copyright_text = ""
            try:
                config_path = os.path.join(os.path.dirname(__file__), "menu_config.json")
                if getattr(sys, 'frozen', False):
                    config_path = os.path.join(os.path.dirname(sys.executable), "menu_config.json")
                
                if os.path.exists(config_path):
                    import json
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        copyright_text = config.get("copyright_text", "")
            except (json.JSONDecodeError, OSError):
                pass
            
            # Show copyright only if explicitly configured (no defaults)
            if copyright_text:
                copyright_label = QtWidgets.QLabel(copyright_text, ui_container)
                copyright_label.setStyleSheet("""
                    color: #666666;
                    font-size: """ + str(int(10 * self.scale_factor)) + """px;
                    background: transparent;
                    letter-spacing: """ + str(int(1 * self.scale_factor)) + """px;
                """)
                copyright_label.setWordWrap(True)
                copyright_label.setAlignment(QtCore.Qt.AlignLeft)
                # Position at bottom-left UNDER language selector (aligned with menu buttons)
                copyright_label.setGeometry(int(60 * self.scale_factor), int(650 * self.scale_factor), int(320 * self.scale_factor), int(40 * self.scale_factor))
        except Exception:
            pass
            
        # Initialize controller support
        self.init_controller_support()
    
    def handle_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.media_player.setPosition(0)
            self.media_player.play()
    
    def change_language(self, lang):
        self.current_lang = lang
        trans = self.translations[lang]
        
        # Update UI text - keep label text as "Menu Language:" 
        # self.lang_label.setText("Menu Language:")  # Keep this fixed
        self.play_btn.setText(trans["play"].upper())
        if hasattr(self, 'bonus_btn'):
            self.bonus_btn.setText(trans["bonus"].upper())
        self.uninstall_btn.setText(trans["uninstall"].upper())
        self.exit_btn.setText(trans["exit"].upper())
    
    def launch_game(self):
        # Find the main game executable dynamically
        game_exe = None
        exclude_exes = ['setup.exe', 'unins000.exe', 'unins001.exe', 'menu.exe',
                        'unitycrashhandler64.exe', 'unitycrashhandler32.exe',
                        'createdump.exe', 'crashpad_handler.exe',
                        'vcredist_x64.exe', 'vcredist_x86.exe', 'dotnet.exe']
        
        try:
            files = os.listdir(self.game_dir)
            # Prefer the standard 'game.exe' entry point when present
            for file in files:
                if file.lower() == 'game.exe':
                    game_exe = os.path.join(self.game_dir, file)
                    break
            # Otherwise take the first real .exe, skipping runtime/helper exes
            if not game_exe:
                for file in files:
                    low = file.lower()
                    if not low.endswith('.exe'):
                        continue
                    if low in exclude_exes:
                        continue
                    # CefSharp/Chromium render + GPU subprocess helpers exit instantly
                    if 'browsersubprocess' in low or low.startswith('cefsharp'):
                        continue
                    game_exe = os.path.join(self.game_dir, file)
                    break
        except OSError:
            pass
        
        if game_exe and os.path.exists(game_exe):
            subprocess.Popen([game_exe], cwd=self.game_dir)
            QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle(trans["error"])
            msg.setText(trans["game_not_found"])
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #2a2a2a;
                    color: white;
                }
                QMessageBox QPushButton {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #666666;
                    padding: 5px 15px;
                    min-width: 60px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #555555;
                }
            """)
            msg.exec_()
    
    def open_bonus(self):
        bonus_dir = os.path.join(self.game_dir, "bonus")
        if os.path.exists(bonus_dir):
            os.startfile(bonus_dir)
        else:
            trans = self.translations[self.current_lang]
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle(trans["warning"])
            msg.setText(trans["bonus_not_found"])
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #2a2a2a;
                    color: white;
                }
                QMessageBox QPushButton {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #666666;
                    padding: 5px 15px;
                    min-width: 60px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #555555;
                }
            """)
            msg.exec_()
    
    def uninstall_game(self):
        uninstaller = os.path.join(self.game_dir, "unins000.exe")
        if os.path.exists(uninstaller):
            trans = self.translations[self.current_lang]
            reply = QtWidgets.QMessageBox.question(
                self, 
                trans["warning"], 
                trans["confirm_uninstall"],
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                subprocess.Popen([uninstaller])
                QtWidgets.QApplication.instance().quit()
        else:
            trans = self.translations[self.current_lang]
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle(trans["warning"])
            msg.setText(trans["uninstaller_not_found"])
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #2a2a2a;
                    color: white;
                }
                QMessageBox QPushButton {
                    background-color: #444444;
                    color: white;
                    border: 1px solid #666666;
                    padding: 5px 15px;
                    min-width: 60px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #555555;
                }
            """)
            msg.exec_()
    
    def init_controller_support(self):
        """Initialize gamepad/controller support"""
        # Initialize gamepad support
        self.current_button_index = 0
        self.controller_states = {}
        self.gamepad_timer = QtCore.QTimer()
        self.gamepad_timer.timeout.connect(self.check_gamepad_input)
        
        # Try to initialize pygame for gamepad support
        try:
            import pygame
            pygame.init()
            pygame.joystick.init()
            
            controller_count = pygame.joystick.get_count()
            
            self.pygame_available = True
            self.joysticks = []
            
            # Initialize all connected joysticks/controllers
            for i in range(controller_count):
                try:
                    joystick = pygame.joystick.Joystick(i)
                    joystick.init()
                    self.joysticks.append(joystick)
                    self.controller_states[i] = {
                        'last_hat': (0, 0),
                        'last_axis': 0,
                        'last_buttons': [False] * joystick.get_numbuttons(),
                        'nav_cooldown': 0
                    }
                except Exception:
                    pass
            
            if self.joysticks:
                self.gamepad_timer.start(16)  # ~60fps polling

        except ImportError:
            self.pygame_available = False
        except Exception:
            self.pygame_available = False
    
    def check_gamepad_input(self):
        """Check for gamepad/controller input"""
        if not self.pygame_available or not self.joysticks:
            return
            
        try:
            import pygame
            pygame.event.pump()
            
            # Get list of buttons for navigation
            buttons = [self.play_btn]
            if hasattr(self, 'bonus_btn'):
                buttons.append(self.bonus_btn)
            buttons.extend([self.uninstall_btn, self.exit_btn])
            
            for i, joystick in enumerate(self.joysticks):
                if i not in self.controller_states:
                    continue
                    
                state = self.controller_states[i]
                
                # Reduce cooldown
                if state['nav_cooldown'] > 0:
                    state['nav_cooldown'] -= 1
                    continue
                
                # D-pad navigation (hat 0)
                if joystick.get_numhats() > 0:
                    hat = joystick.get_hat(0)
                    if hat != state['last_hat']:
                        if hat[1] == 1:  # D-pad up
                            self.navigate_up(buttons)
                            state['nav_cooldown'] = 10  # Cooldown frames
                        elif hat[1] == -1:  # D-pad down
                            self.navigate_down(buttons)
                            state['nav_cooldown'] = 10
                        state['last_hat'] = hat
                
                # Left analog stick (Y-axis for up/down)
                if joystick.get_numaxes() >= 2:
                    y_axis = joystick.get_axis(1)
                    current_direction = 0
                    
                    if y_axis < -0.5:  # Up
                        current_direction = -1
                    elif y_axis > 0.5:  # Down
                        current_direction = 1
                    
                    if current_direction != state['last_axis'] and current_direction != 0:
                        if current_direction == -1:
                            self.navigate_up(buttons)
                        elif current_direction == 1:
                            self.navigate_down(buttons)
                        state['nav_cooldown'] = 15  # Longer cooldown for analog
                    
                    state['last_axis'] = current_direction
                
                # Button presses
                for btn_idx in range(min(joystick.get_numbuttons(), len(state['last_buttons']))):
                    current_pressed = joystick.get_button(btn_idx)
                    was_pressed = state['last_buttons'][btn_idx]
                    
                    # Button just pressed (rising edge)
                    if current_pressed and not was_pressed:
                        if btn_idx == 0:  # A/X button - activate
                            if 0 <= self.current_button_index < len(buttons):
                                buttons[self.current_button_index].click()
                        elif btn_idx == 1:  # B/Circle button - exit
                            self.close()
                    
                    state['last_buttons'][btn_idx] = current_pressed
                        
        except Exception:
            pass

    def navigate_up(self, buttons):
        """Navigate up in menu"""
        if self.current_button_index > 0:
            self.current_button_index -= 1
        else:
            self.current_button_index = len(buttons) - 1  # Wrap to last
        buttons[self.current_button_index].setFocus()
    
    def navigate_down(self, buttons):
        """Navigate down in menu"""
        if self.current_button_index < len(buttons) - 1:
            self.current_button_index += 1
        else:
            self.current_button_index = 0  # Wrap to first
        buttons[self.current_button_index].setFocus()

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        # Get list of buttons for navigation
        buttons = [self.play_btn]
        if hasattr(self, 'bonus_btn'):
            buttons.append(self.bonus_btn)
        buttons.extend([self.uninstall_btn, self.exit_btn])
        
        # Find currently focused button and update index
        current_index = -1
        for i, btn in enumerate(buttons):
            if btn.hasFocus():
                current_index = i
                self.current_button_index = i
                break
        
        # Handle navigation
        if event.key() == QtCore.Qt.Key_Up:
            self.navigate_up(buttons)
        elif event.key() == QtCore.Qt.Key_Down:
            self.navigate_down(buttons)
        elif event.key() in [QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space]:
            if current_index >= 0:
                buttons[current_index].click()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging"""
        if event.button() == QtCore.Qt.LeftButton:
            self.offset = event.pos()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging"""
        if self.offset is not None and event.buttons() == QtCore.Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release for window dragging"""
        self.offset = None

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = GameMenu()
    window.show()
    sys.exit(app.exec_())
'''
        
        # Write the PyQt5 menu launcher
        launcher_path = os.path.join(menu_dir, "menu_launcher.pyw")
        try:
            with open(launcher_path, "w", encoding="utf-8") as f:
                f.write(pyqt5_menu_code)
            self.update_status("✅ Created professional PyQt5 menu launcher")
        except Exception as e:
            self.update_status(f"❌ Failed to create PyQt5 menu: {e}")





if __name__ == '__main__':
    ensure_structure()
    root = tk.Tk()
    app = RialtoApp(root)
    root.mainloop()
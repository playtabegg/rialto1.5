import os
import subprocess
import sys
# ✅ Redirect stderr/stdout to temp location or disable for production
try:
    import tempfile
    temp_dir = tempfile.gettempdir()
    log_path = os.path.join(temp_dir, "menu_error_log.txt")
    sys.stderr = open(log_path, "w")
    sys.stdout = sys.stderr
except Exception:
    # If we can't create log, just disable it
    pass
# Import Qt - UPDATED TO INCLUDE QApplication and QMessageBox
from PyQt5 import QtWidgets, QtGui, QtCore, QtMultimedia
from PyQt5.QtWidgets import QApplication, QMessageBox, QLabel
# Controller support (optional)
try:
    from PyQt5.QtGamepad import QGamepad, QGamepadManager
    GAMEPAD_AVAILABLE = True
except ImportError:
    GAMEPAD_AVAILABLE = False
import json


class MenuWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        
        # SIMPLIFIED: Determine base directory for onefile
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            self.exe_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            self.exe_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if we're in MENU subfolder and adjust paths
        if os.path.basename(self.exe_dir).upper() == 'MENU':
            self.root_dir = os.path.dirname(self.exe_dir)
        else:
            self.root_dir = self.exe_dir
            
        # Change working directory to root for relative paths
        os.chdir(self.root_dir)
        
        self.offset = None
        self.click_sound = QtMultimedia.QSoundEffect()
        
        # Look for hover.wav in multiple locations
        hover_paths = [
            os.path.join(self.exe_dir, "hover.wav"),
            os.path.join(self.root_dir, "hover.wav"),
            "hover.wav"
        ]
        
        for hover_path in hover_paths:
            if os.path.exists(hover_path):
                self.click_sound.setSource(QtCore.QUrl.fromLocalFile(hover_path))
                self.click_sound.setVolume(0.3)
                break
        else:
            self.click_sound = None  # disable sound if file not found
            
        self.bonus_viewer = None  # Not using web viewer anymore
        
        # Load menu configuration for new features
        self.config = self.load_menu_config()
        
        # Controller support
        self.selected_button_index = 0
        self.buttons = []
        self.setup_gamepad()
        
        self.init_ui()



    def load_menu_config(self):
        """Load configuration for company logo and copyright text"""
        config_path = os.path.join(self.exe_dir, "menu_config.json")
        default_config = {
            "company_logo": "",
            "publisher_text": "",
            "language": "English"
        }
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)
            return default_config
        except Exception:
            return default_config
    
    def setup_gamepad(self):
        """Setup gamepad/controller support"""
        if not GAMEPAD_AVAILABLE:
            return
            
        try:
            self.gamepad_manager = QGamepadManager()
            gamepads = self.gamepad_manager.connectedGamepads()
            
            if gamepads:
                self.gamepad = QGamepad(gamepads[0])
                self.gamepad.buttonAPressed.connect(self.gamepad_select)
                self.gamepad.buttonBPressed.connect(self.close)
                self.gamepad.buttonDownPressed.connect(lambda: self.gamepad_navigate(1))
                self.gamepad.buttonUpPressed.connect(lambda: self.gamepad_navigate(-1))
        except Exception:
            pass
    
    def gamepad_navigate(self, direction):
        """Navigate menu with gamepad"""
        if not self.buttons:
            return
            
        self.selected_button_index = (self.selected_button_index + direction) % len(self.buttons)
        self.update_button_selection()
    
    def gamepad_select(self):
        """Select current button with gamepad"""
        if self.buttons and 0 <= self.selected_button_index < len(self.buttons):
            self.buttons[self.selected_button_index].click()
    
    def update_button_selection(self):
        """Update visual selection of buttons"""
        for i, btn in enumerate(self.buttons):
            if i == self.selected_button_index:
                btn.setStyleSheet(btn.styleSheet() + "border: 2px solid #00ff00;")
            else:
                style = btn.styleSheet().replace("border: 2px solid #00ff00;", "")
                btn.setStyleSheet(style)
    
    def init_ui(self):
        self.setWindowTitle("Game Menu")
        
        # Get screen size for 4K scaling
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        screen_dpi = screen.logicalDotsPerInch()
        
        # Calculate scale factor for 4K support
        base_dpi = 96
        scale_factor = max(1.0, screen_dpi / base_dpi)
        
        # Scale window size
        base_width, base_height = 1280, 720
        scaled_width = int(base_width * scale_factor)
        scaled_height = int(base_height * scale_factor)
        
        self.setFixedSize(scaled_width, scaled_height)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.scale_factor = scale_factor


        # MODIFIED: Look for background in multiple locations with better detection
        background_paths = [
            os.path.join(self.exe_dir, "background.jpg"),
            os.path.join(self.root_dir, "background.jpg"),
            os.path.join(self.root_dir, "MENU", "background.jpg"),
            os.path.join(self.root_dir, "menu", "background.jpg"),
            "background.jpg"
        ]

        print(f"DEBUG: Checking background paths: {background_paths}")

        # Set background image
        self.background = QtWidgets.QLabel(self)
        background_found = False

        for bg_path in background_paths:
            print(f"DEBUG: Checking background at {bg_path} - exists: {os.path.exists(bg_path)}")
            if os.path.exists(bg_path):
                pixmap = QtGui.QPixmap(bg_path).scaled(int(1280 * self.scale_factor), int(720 * self.scale_factor), QtCore.Qt.KeepAspectRatioByExpanding)
                self.background.setPixmap(pixmap)
                background_found = True
                print(f"DEBUG: Background loaded from: {bg_path}")
                break

                
        if not background_found:
            # Set a dark background if no image found
            self.background.setStyleSheet("background-color: #1a1a1a;")
            
        self.background.setGeometry(0, 0, int(1280 * self.scale_factor), int(720 * self.scale_factor))
        self.background.lower()  # Keep background at the bottom




        # MODIFIED: Look for hover.wav in multiple locations
        hover_paths = [
            os.path.join(self.exe_dir, "hover.wav"),
            os.path.join(self.root_dir, "hover.wav"),
            os.path.join(self.root_dir, "MENU", "hover.wav"),
            os.path.join(self.root_dir, "menu", "hover.wav"),
            "hover.wav"
        ]

        print(f"DEBUG: Checking hover sound paths: {hover_paths}")

        for hover_path in hover_paths:
            print(f"DEBUG: Checking hover sound at {hover_path} - exists: {os.path.exists(hover_path)}")
            if os.path.exists(hover_path):
                self.click_sound.setSource(QtCore.QUrl.fromLocalFile(hover_path))
                self.click_sound.setVolume(0.3)
                print(f"DEBUG: Hover sound loaded from: {hover_path}")
                break
        else:
            self.click_sound = None  # disable sound if file not found
            print("DEBUG: No hover sound file found")



        # Add just one clean dark tint layer (optional)
        self.tint = QtWidgets.QLabel(self)
        self.tint.setGeometry(0, 0, int(1280 * self.scale_factor), int(720 * self.scale_factor))
        self.tint.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        self.tint.lower()  # Make sure it stays behind all other widgets

        # Layout for buttons inside panel
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        self.play_btn = self.make_button("Play Game", self.launch_game)
        
        # Only show bonus button if bonus folder exists
        bonus_exists = os.path.exists(os.path.join(self.root_dir, "bonus"))
        if bonus_exists:
            self.bonus_btn = self.make_button("Bonus Content", self.open_bonus)
        
        self.uninstall_btn = self.make_button("Uninstall Game", self.uninstall_game)
        self.exit_btn = self.make_button("Exit", self.close)

        # Build button list for controller navigation
        self.buttons = [self.play_btn]
        if bonus_exists:
            self.buttons.append(self.bonus_btn)
        self.buttons.extend([self.uninstall_btn, self.exit_btn])
        
        # Add buttons to layout
        for btn in self.buttons:
            layout.addWidget(btn)

        # Panel with style
        self.panel = QtWidgets.QFrame(self)
        self.panel.setFixedSize(400, 280)
        self.panel.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 200);
                border-radius: 15px;
                border: 2px solid #555;
            }
        """)
        self.panel.setLayout(layout)

        # Wrap panel inside fade_wrapper
        fade_wrapper = QtWidgets.QWidget(self)
        fade_wrapper.setGeometry(0, 0, int(1280 * self.scale_factor), int(720 * self.scale_factor))
        
        # Add company logo (bottom right)
        self.add_company_logo()
        
        # Add language selector and copyright (bottom left)
        self.add_bottom_left_elements()
        fade_layout = QtWidgets.QVBoxLayout(fade_wrapper)
        fade_layout.addStretch()
        fade_layout.addWidget(self.panel, alignment=QtCore.Qt.AlignHCenter)
        fade_layout.addStretch()
        fade_layout.setContentsMargins(0, 200, 0, 0)

        # Apply fade to the button panel only
        self.fade_effect = QtWidgets.QGraphicsOpacityEffect(self.panel)
        self.panel.setGraphicsEffect(self.fade_effect)

        self.fade_animation = QtCore.QPropertyAnimation(self.fade_effect, b"opacity")
        self.fade_animation.setDuration(1000)
        self.fade_animation.setStartValue(0)
        self.fade_animation.setEndValue(1)
        self.fade_animation.start()
        
        # Set first button as selected for controller navigation
        if self.buttons:
            self.update_button_selection()

        # Global style with hover animation polish
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
                font-family: 'Segoe UI';
                font-size: 16px;
            }
            QPushButton {
                background-color: #2c2c2c;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 10px;
                min-width: 200px;
                qproperty-iconSize: 24px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                outline: 2px solid rgba(255, 255, 255, 0.2);
                cursor: pointer;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QPushButton:focus {
                outline: none;
            }
        """)

    def add_company_logo(self):
        """Add company logo to bottom right"""
        company_logo_path = self.config.get("company_logo", "")
        if not company_logo_path:
            # Try to find company logo in menu directory
            logo_paths = [
                os.path.join(self.exe_dir, "company_logo.png"),
                os.path.join(self.root_dir, "company_logo.png")
            ]
            for path in logo_paths:
                if os.path.exists(path):
                    company_logo_path = path
                    break
        
        if company_logo_path and os.path.exists(company_logo_path):
            self.company_logo = QLabel(self)
            logo_pixmap = QtGui.QPixmap(company_logo_path)
            
            # Scale logo appropriately
            max_width = int(150 * self.scale_factor)
            max_height = int(75 * self.scale_factor)
            scaled_logo = logo_pixmap.scaled(max_width, max_height, 
                                           QtCore.Qt.KeepAspectRatio, 
                                           QtCore.Qt.SmoothTransformation)
            
            self.company_logo.setPixmap(scaled_logo)
            
            # Position at bottom right
            logo_x = self.width() - max_width - int(20 * self.scale_factor)
            logo_y = self.height() - int(140 * self.scale_factor)
            self.company_logo.setGeometry(logo_x, logo_y, max_width, max_height)
    
    def add_bottom_left_elements(self):
        """Add language selector and copyright text to bottom left"""
        # Language selector (moved up and changed text)
        self.language_label = QLabel("Menu Language:", self)
        self.language_label.setStyleSheet(f"color: white; font-size: {int(12 * self.scale_factor)}px;")
        
        # Position language elements
        lang_x = int(20 * self.scale_factor)
        lang_y = self.height() - int(100 * self.scale_factor)
        self.language_label.setGeometry(lang_x, lang_y, int(100 * self.scale_factor), int(20 * self.scale_factor))
        
        # Copyright text
        publisher_text = self.config.get("publisher_text", "")
        if publisher_text:
            # Create full copyright text
            current_year = "2023 – 2025"  # You can make this dynamic
            copyright_text = f"{publisher_text} {current_year}. All rights reserved.\nDistributed by We the Indies."
            
            self.copyright_label = QLabel(copyright_text, self)
            self.copyright_label.setStyleSheet(f"""
                color: #cccccc; 
                font-size: {int(10 * self.scale_factor)}px;
                background-color: transparent;
            """)
            self.copyright_label.setAlignment(QtCore.Qt.AlignLeft)
            self.copyright_label.setWordWrap(True)
            
            # Position at very bottom left
            copyright_x = int(20 * self.scale_factor)
            copyright_y = self.height() - int(50 * self.scale_factor)
            copyright_width = int(400 * self.scale_factor)
            copyright_height = int(40 * self.scale_factor)
            self.copyright_label.setGeometry(copyright_x, copyright_y, copyright_width, copyright_height)
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == QtCore.Qt.Key_Up:
            self.selected_button_index = (self.selected_button_index - 1) % len(self.buttons)
            self.update_button_selection()
        elif event.key() == QtCore.Qt.Key_Down:
            self.selected_button_index = (self.selected_button_index + 1) % len(self.buttons)
            self.update_button_selection()
        elif event.key() in [QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space]:
            if self.buttons and 0 <= self.selected_button_index < len(self.buttons):
                self.buttons[self.selected_button_index].click()
        elif event.key() == QtCore.Qt.Key_Escape:
            self.close()
    
    def make_button(self, label, callback):
        """Create a styled button with sound effect"""
        btn = QtWidgets.QPushButton(label)
        btn.setFixedSize(int(300 * self.scale_factor), int(50 * self.scale_factor))
        btn.setStyleSheet("")  # style will be handled globally
        btn.setFocusPolicy(QtCore.Qt.NoFocus)  # prevents dotted box on click

        def play_click_and_run(action):
            if self.click_sound and not self.click_sound.isPlaying():
                self.click_sound.play()
            action()

        btn.clicked.connect(lambda: play_click_and_run(callback))
        return btn

    def fade_in_animation(self):
        self.fade_effect.setOpacity(0)
        self.anim = QtCore.QPropertyAnimation(self.fade_effect, b"opacity")
        self.anim.setDuration(800)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == QtCore.Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None


    def launch_game(self):
        """Launch the game executable and close the menu"""
        # DEBUG: Show what's in the directories
        print(f"DEBUG: exe_dir contents: {os.listdir(self.exe_dir) if os.path.exists(self.exe_dir) else 'Not found'}")
        print(f"DEBUG: root_dir contents: {os.listdir(self.root_dir) if os.path.exists(self.root_dir) else 'Not found'}")
    
        # Look for game.exe in multiple locations
        game_paths = [
            os.path.join(self.root_dir, "game.exe"),
            os.path.join(self.root_dir, "GAME.EXE"),
            os.path.join(self.root_dir, "Game.exe"),
            os.path.join(self.exe_dir, "game.exe"),
            os.path.join(self.exe_dir, "..", "game.exe")
        ]
    
        print(f"DEBUG: Checking game paths: {game_paths}")
    
        game_found = False
        for game_path in game_paths:
            print(f"DEBUG: Checking {game_path} - exists: {os.path.exists(game_path)}")
            if os.path.exists(game_path):
                try:
                    # Launch game as a completely separate process
                    game_dir = os.path.dirname(os.path.abspath(game_path))
                    
                    # Use CREATE_NEW_PROCESS_GROUP to detach from parent
                    if sys.platform == "win32":
                        subprocess.Popen(
                            [game_path],
                            cwd=game_dir,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                            close_fds=True
                        )
                    else:
                        subprocess.Popen([game_path], cwd=game_dir)
                    
                    game_found = True
                    
                    # Close the menu application after launching
                    QApplication.instance().quit()
                    sys.exit(0)
                    
                except Exception as e:
                    self.show_message("Launch Error", f"Failed to launch game: {str(e)}", "error")
                    break
                
        if not game_found:
            # Check if any .exe files exist to give better error message
            exe_files = [f for f in os.listdir(self.root_dir) if f.lower().endswith('.exe')] if os.path.exists(self.root_dir) else []
            
            self.show_message("Game Not Found", 
                            f"game.exe not found!\n\n"
                            f"Searched in: {self.root_dir}\n"
                            f"Found executables: {', '.join(exe_files) if exe_files else 'None'}", "warning")


    def open_bonus(self):
        # MODIFIED: Look for bonus folder in root directory
        possible_paths = [
            os.path.join(self.root_dir, "BONUS"),
            os.path.join(self.root_dir, "bonus"),
            os.path.join(self.root_dir, "Bonus"),
            os.path.join(self.root_dir, "templates", "_temp", "bonus"),
            os.path.join(self.root_dir, "_temp", "bonus")
        ]
        
        bonus_dir = None
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(path):
                bonus_dir = path
                break
        
        print(f"Looking for bonus content directory: {bonus_dir}")
        
        if not bonus_dir:
            print(f"Bonus content folder not found in any of these locations:")
            for path in possible_paths:
                print(f"  - {path}")
            
            # MODIFIED: Show actual paths checked
            checked_paths = []
            for path in possible_paths:
                # Convert to display format
                if path.startswith(self.root_dir):
                    rel_path = path[len(self.root_dir):].lstrip(os.sep)
                    checked_paths.append(f"E:\\MENU\\{rel_path}")
                else:
                    checked_paths.append(path)
            
            self.show_message("Bonus Content Missing", 
                            "Bonus content folder not found!\n\n"
                            "Checked locations:\n" + "\n".join(checked_paths), 
                            "warning")
            return

        # Open the bonus folder in file explorer
        try:
            if os.name == 'nt':  # Windows
                os.startfile(bonus_dir)
            elif os.name == 'posix':  # macOS and Linux
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', bonus_dir])
            
            print(f"Opened bonus folder: {bonus_dir}")
            
        except Exception as e:
            print(f"Failed to open bonus folder: {e}")
            self.show_message("Error", f"Could not open bonus folder.\n\nLocation: {bonus_dir}\nError: {str(e)}", "error")


    def uninstall_game(self):
        """Launch the uninstaller"""
        # Look for unins000.exe (Inno Setup default uninstaller)
        uninstall_paths = [
            os.path.join(self.root_dir, "unins000.exe"),
            os.path.join(self.exe_dir, "unins000.exe"),
            os.path.join(self.exe_dir, "..", "unins000.exe")
        ]
        
        uninstall_found = False
        for uninstall_path in uninstall_paths:
            if os.path.exists(uninstall_path):
                try:
                    subprocess.Popen([uninstall_path])
                    uninstall_found = True
                    # Close menu after launching uninstaller
                    QApplication.instance().quit()
                    sys.exit(0)
                except Exception as e:
                    self.show_message("Uninstall Error", f"Failed to launch uninstaller: {str(e)}", "error")
                break
                
        if not uninstall_found:
            self.show_message("Uninstaller Not Found", 
                            "No uninstaller found.\n\n"
                            "To manually uninstall, delete the game folder:\n"
                            f"{self.root_dir}", "warning")


    def show_message(self, title, text, msg_type="info"):
        """Show a clean, styled message dialog"""
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        
        # Set icon based on type
        if msg_type == "warning":
            msg.setIcon(QtWidgets.QMessageBox.Warning)
        elif msg_type == "error":
            msg.setIcon(QtWidgets.QMessageBox.Critical)
        else:
            msg.setIcon(QtWidgets.QMessageBox.Information)
        
        # Style the message box to match the launcher
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2c2c2c;
                color: white;
                border-radius: 10px;
            }
            QMessageBox QLabel {
                color: white;
                font-family: 'Segoe UI';
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #404040;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-family: 'Segoe UI';
                font-size: 12px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #4a4a4a;
            }
            QMessageBox QPushButton:pressed {
                background-color: #303030;
            }
        """)
        
        msg.exec_()

    def show_question(self, title, text):
        """Show a clean, styled question dialog"""
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QtWidgets.QMessageBox.Question)
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg.setDefaultButton(QtWidgets.QMessageBox.No)
        
        # Style the question box to match the launcher
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2c2c2c;
                color: white;
                border-radius: 10px;
            }
            QMessageBox QLabel {
                color: white;
                font-family: 'Segoe UI';
                font-size: 14px;
                padding: 10px;
            }
            QMessageBox QPushButton {
                background-color: #404040;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-family: 'Segoe UI';
                font-size: 12px;
                min-width: 80px;
                margin: 5px;
            }
            QMessageBox QPushButton:hover {
                background-color: #4a4a4a;
            }
            QMessageBox QPushButton:pressed {
                background-color: #303030;
            }
            QMessageBox QPushButton[text="Yes"] {
                background-color: #0078d4;
            }
            QMessageBox QPushButton[text="Yes"]:hover {
                background-color: #106ebe;
            }
        """)
        
        reply = msg.exec_()
        return reply == QtWidgets.QMessageBox.Yes


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    
    # Enable high DPI scaling for 4K support
    app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    
    window = MenuWindow()
    window.show()
    sys.exit(app.exec_())
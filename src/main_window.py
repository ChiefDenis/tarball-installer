from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFileDialog, QTextEdit,
                              QProgressBar, QMessageBox, QGroupBox, QTabWidget,
                              QListWidget, QListWidgetItem, QFrame, QStackedWidget,
                              QFormLayout, QLineEdit, QCheckBox, QComboBox,
                              QSizePolicy, QSpacerItem, QSplitter, QToolBar,
                              QStatusBar, QMenu, QMenuBar, QDialog, QDialogButtonBox,
                              QRadioButton, QButtonGroup, QTreeWidget, QTreeWidgetItem,
                              QHeaderView, QScrollArea, QListWidget)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QPropertyAnimation, QEasingCurve, QFile, QTextStream
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QPainter, QLinearGradient, QAction, QFontDatabase
import subprocess
import tarfile
import os
import json
import shutil
from pathlib import Path
import tempfile
import mimetypes
import hashlib
from datetime import datetime
import configparser

class WelcomeDialog(QDialog):
    """Welcome dialog shown on first launch"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Welcome to Tarball Installer")
        self.setFixedSize(600, 500)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Header
        header = QLabel("Welcome to Tarball Installer")
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Information text
        info_text = QLabel("""
        <div style='line-height: 1.6;'>
        <h3>Important Information About Tarballs</h3>
        
        <p><b>You don't always need to install tarballs!</b></p>
        
        <p>Most applications in tarball format can be run directly from their extracted folder. 
        Simply extract the tarball to a location of your choice (like ~/Applications) and run 
        the executable from there.</p>
        
        <h4>Why use this installer then?</h4>
        
        <p>This installer provides several conveniences:</p>
        
        <ul>
        <li><b>Application Menu Integration:</b> Adds entries to your system application menu</li>
        <li><b>Desktop Launcher:</b> Creates desktop shortcuts for quick access</li>
        <li><b>System Integration:</b> Properly installs icons and file associations</li>
        <li><b>Easy Updates:</b> Track and update installed applications</li>
        <li><b>Clean Removal:</b> Easily uninstall applications when no longer needed</li>
        </ul>
        
        <h4>Recommendation:</h4>
        
        <p>• <b>Try running from folder first</b> to test the application<br>
        • <b>Use this installer</b> when you want full system integration</p>
        </div>
        """)
        info_text.setWordWrap(True)
        info_text.setOpenExternalLinks(True)
        
        scroll = QScrollArea()
        scroll.setWidget(info_text)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(300)
        layout.addWidget(scroll)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        self.show_welcome = QCheckBox("Show this welcome message on startup")
        self.show_welcome.setChecked(True)
        
        options_layout.addWidget(self.show_welcome)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

class InstallerThread(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished = Signal(bool, str, dict)  # Added installation data
    
    def __init__(self, tarball_path, install_path, options):
        super().__init__()
        self.tarball_path = tarball_path
        self.install_path = install_path
        self.options = options
        self.temp_dir = None
        self.installation_data = {}
        
    def run(self):
        try:
            self.installation_data = {
                'app_id': f"user_{hashlib.md5(self.tarball_path.encode()).hexdigest()[:8]}",
                'source_file': self.tarball_path,
                'install_time': datetime.now().isoformat(),
                'install_type': self.options.get('install_type', 'user'),
                'files_installed': [],
                'desktop_entries': [],
                'binaries': []
            }
            
            self.log.emit(f"Starting installation of {os.path.basename(self.tarball_path)}")
            
            # Create temp directory
            self.temp_dir = tempfile.mkdtemp(prefix="tarball_installer_")
            self.progress.emit("Preparing installation...", 10)
            
            # Extract tarball
            self.log.emit(f"Extracting to temporary directory: {self.temp_dir}")
            with tarfile.open(self.tarball_path, 'r:*') as tar:
                members = tar.getmembers()
                total_members = len(members)
                for i, member in enumerate(members):
                    tar.extract(member, self.temp_dir)
                    if i % 10 == 0:
                        progress = 10 + int((i / total_members) * 60)
                        self.progress.emit(f"Extracting files...", progress)
            
            self.progress.emit("Analyzing package contents...", 70)
            
            # Analyze extracted contents
            desktop_files = self.find_desktop_files()
            binaries = self.find_binaries()
            icons = self.find_icons()
            
            self.log.emit(f"Found: {len(desktop_files)} desktop files, {len(binaries)} binaries, {len(icons)} icons")
            
            # Store in installation data
            self.installation_data['desktop_files'] = [os.path.basename(f) for f in desktop_files]
            self.installation_data['binaries'] = [os.path.basename(f) for f in binaries]
            
            if self.options.get('install_type') == 'user':
                install_data = self.install_to_user(desktop_files, binaries, icons)
            else:
                install_data = self.install_system_wide(desktop_files, binaries, icons)
            
            # Merge installation data
            self.installation_data.update(install_data)
            
            self.progress.emit("Cleaning up...", 95)
            
            # Clean temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            self.progress.emit("Installation complete!", 100)
            self.finished.emit(True, "Application installed successfully!", self.installation_data)
            
        except Exception as e:
            self.log.emit(f"Error: {str(e)}")
            self.finished.emit(False, str(e), {})
    
    def find_desktop_files(self):
        """Find .desktop files in extracted tarball"""
        desktop_files = []
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if file.endswith('.desktop'):
                    desktop_files.append(os.path.join(root, file))
        return desktop_files
    
    def find_binaries(self):
        """Find executable binaries"""
        binaries = []
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                filepath = os.path.join(root, file)
                if os.access(filepath, os.X_OK):
                    with open(filepath, 'rb') as f:
                        magic = f.read(4)
                        if magic.startswith(b'#!') or magic.startswith(b'\x7fELF'):
                            binaries.append(filepath)
        return binaries
    
    def find_icons(self):
        """Find icon files"""
        icons = []
        icon_extensions = ['.png', '.svg', '.xpm', '.ico']
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if any(file.lower().endswith(ext) for ext in icon_extensions):
                    # Check if it's in an icons directory or has a meaningful name
                    if 'icon' in file.lower() or 'icons' in root.lower():
                        icons.append(os.path.join(root, file))
        return icons
    
    def parse_desktop_file(self, desktop_path):
        """Parse .desktop file for app info"""
        config = configparser.ConfigParser()
        try:
            config.read(desktop_path)
            if 'Desktop Entry' in config:
                return {
                    'name': config['Desktop Entry'].get('Name', 'Unknown'),
                    'comment': config['Desktop Entry'].get('Comment', ''),
                    'exec': config['Desktop Entry'].get('Exec', ''),
                    'icon': config['Desktop Entry'].get('Icon', ''),
                    'categories': config['Desktop Entry'].get('Categories', '').split(';')
                }
        except:
            pass
        return {}
    
    def install_to_user(self, desktop_files, binaries, icons):
        """Install to user's home directory"""
        home = Path.home()
        local_bin = home / '.local' / 'bin'
        local_apps = home / '.local' / 'share' / 'applications'
        local_icons = home / '.local' / 'share' / 'icons'
        
        # Create directories if they don't exist
        local_bin.mkdir(parents=True, exist_ok=True)
        local_apps.mkdir(parents=True, exist_ok=True)
        local_icons.mkdir(parents=True, exist_ok=True)
        
        install_data = {
            'install_path': str(local_bin),
            'desktop_path': str(local_apps),
            'installed_files': []
        }
        
        # Parse first desktop file for app info
        app_info = {}
        if desktop_files:
            app_info = self.parse_desktop_file(desktop_files[0])
            if app_info.get('name'):
                self.installation_data['app_name'] = app_info['name']
                self.installation_data['app_comment'] = app_info.get('comment', '')
        
        # Install binaries
        for binary in binaries:
            dest = local_bin / os.path.basename(binary)
            shutil.copy2(binary, dest)
            dest.chmod(0o755)
            install_data['installed_files'].append(str(dest))
            self.log.emit(f"Installed binary: {dest}")
        
        # Install desktop files
        for desktop in desktop_files:
            dest = local_apps / os.path.basename(desktop)
            shutil.copy2(desktop, dest)
            install_data['installed_files'].append(str(dest))
            self.log.emit(f"Installed desktop entry: {dest}")
        
        # Install icons
        for icon in icons:
            dest_dir = local_icons / 'hicolor' / 'scalable' / 'apps'
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / os.path.basename(icon)
            shutil.copy2(icon, dest)
            install_data['installed_files'].append(str(dest))
            self.log.emit(f"Installed icon: {dest}")
        
        # Update desktop database
        try:
            subprocess.run(['update-desktop-database', str(local_apps)], check=True)
            self.log.emit("Updated desktop database")
        except subprocess.CalledProcessError as e:
            self.log.emit(f"Warning: Failed to update desktop database: {e}")
        
        return install_data

class InstallationTracker:
    """Track installed applications"""
    
    def __init__(self):
        self.db_path = Path.home() / '.local' / 'share' / 'tarball-installer' / 'installations.json'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.installations = self.load_installations()
    
    def load_installations(self):
        """Load installation database"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_installations(self):
        """Save installation database"""
        with open(self.db_path, 'w') as f:
            json.dump(self.installations, f, indent=2)
    
    def add_installation(self, data):
        """Add a new installation to database"""
        self.installations.append(data)
        self.save_installations()
    
    def remove_installation(self, app_id):
        """Remove an installation from database"""
        self.installations = [inst for inst in self.installations if inst.get('app_id') != app_id]
        self.save_installations()
    
    def get_installations(self):
        """Get all installations"""
        return self.installations

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tracker = InstallationTracker()
        self.setup_ui()
        self.setup_style()
        self.current_file = None
        self.install_history = []
        
        # Show welcome dialog on first run
        self.show_welcome_dialog()
        
    def show_welcome_dialog(self):
        """Show welcome dialog based on user preference"""
        settings_path = Path.home() / '.config' / 'tarball-installer' / 'settings.json'
        show_welcome = True
        
        if settings_path.exists():
            try:
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                    show_welcome = settings.get('show_welcome', True)
            except:
                pass
        
        if show_welcome:
            dialog = WelcomeDialog(self)
            if dialog.exec():
                # Save preference
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_path, 'w') as f:
                    json.dump({'show_welcome': dialog.show_welcome.isChecked()}, f)
        
    def setup_style(self):
        """Apply KDE Breeze-inspired styling"""
        self.setStyleSheet("""
            /* Main Window */
            QMainWindow {
                background-color: #fcfcfc;
            }
            
            /* Global font settings */
            QWidget {
                font-family: 'Noto Sans', 'Roboto', sans-serif;
                font-size: 10pt;
                color: #232629;
            }
            
            /* Group Boxes - KDE style */
            QGroupBox {
                font-weight: bold;
                border: 1px solid #c2c7cb;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: #fcfcfc;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #232629;
            }
            
            /* Buttons - Breeze style */
            QPushButton {
                background-color: #3daee9;
                border: none;
                border-radius: 4px;
                color: white;
                padding: 6px 16px;
                font-weight: bold;
                min-height: 24px;
                min-width: 80px;
            }
            
            QPushButton:hover {
                background-color: #1d99e3;
            }
            
            QPushButton:pressed {
                background-color: #0d8add;
            }
            
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
            
            QPushButton#secondary {
                background-color: transparent;
                border: 1px solid #c2c7cb;
                color: #232629;
            }
            
            QPushButton#secondary:hover {
                background-color: #eff0f1;
                border-color: #93cee9;
            }
            
            /* Labels */
            QLabel {
                color: #232629;
            }
            
            QLabel#title {
                font-size: 18pt;
                font-weight: bold;
                color: #232629;
            }
            
            QLabel#subtitle {
                font-size: 10pt;
                color: #5e646b;
            }
            
            /* Progress Bar - Breeze style */
            QProgressBar {
                border: 1px solid #c2c7cb;
                border-radius: 2px;
                background-color: #fcfcfc;
                text-align: center;
                height: 16px;
            }
            
            QProgressBar::chunk {
                background-color: #3daee9;
                border-radius: 2px;
            }
            
            /* Text Edit / Log Display */
            QTextEdit {
                border: 1px solid #c2c7cb;
                border-radius: 4px;
                background-color: white;
                font-family: 'Monospace', 'Consolas', 'Courier New';
                font-size: 9pt;
                padding: 8px;
                selection-background-color: #3daee9;
                selection-color: white;
            }
            
            /* Tree Widget */
            QTreeWidget {
                border: 1px solid #c2c7cb;
                border-radius: 4px;
                background-color: white;
            }
            
            QTreeWidget::item {
                padding: 4px;
            }
            
            QTreeWidget::item:selected {
                background-color: #3daee9;
                color: white;
            }
            
            /* Tab Widget - KDE style */
            QTabWidget::pane {
                border: 1px solid #c2c7cb;
                border-radius: 4px;
                background-color: #fcfcfc;
                top: -1px;
            }
            
            QTabBar::tab {
                background-color: #eff0f1;
                color: #5e646b;
                padding: 8px 16px;
                margin-right: 1px;
                border: 1px solid #c2c7cb;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: #fcfcfc;
                color: #232629;
                border-bottom: 1px solid #fcfcfc;
                margin-bottom: -1px;
            }
        """)
        
        self.setWindowIcon(QIcon.fromTheme("application-x-tar"))
        
    def setup_ui(self):
        self.setWindowTitle("Tarball Installer")
        self.setGeometry(100, 100, 1000, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        self.setup_menu_bar()
        
        # Header
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 8)
        
        title = QLabel("Tarball Installer")
        title.setObjectName("title")
        
        subtitle = QLabel("Install and manage applications from tarball archives")
        subtitle.setObjectName("subtitle")
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addWidget(header_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.setup_install_tab()
        self.setup_manage_tab()
        self.setup_help_tab()
        
        main_layout.addWidget(self.tab_widget, 1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
    def setup_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("&Open Tarball...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.browse_file)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        welcome_action = QAction("Show &Welcome Message", self)
        welcome_action.triggered.connect(self.show_welcome_dialog)
        view_menu.addAction(welcome_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        refresh_action = QAction("&Refresh Application List", self)
        refresh_action.triggered.connect(self.refresh_apps_list)
        tools_menu.addAction(refresh_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        
    def setup_install_tab(self):
        install_tab = QWidget()
        layout = QVBoxLayout(install_tab)
        layout.setSpacing(12)
        
        # File selection
        file_group = QGroupBox("Package Selection")
        file_layout = QVBoxLayout()
        
        self.file_label = QLabel("No package selected")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("""
            padding: 8px;
            background-color: #eff0f1;
            border-radius: 4px;
            min-height: 40px;
        """)
        
        file_button_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse for Tarball...")
        browse_btn.clicked.connect(self.browse_file)
        
        self.analyze_btn = QPushButton("Analyze Package")
        self.analyze_btn.clicked.connect(self.analyze_package)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setObjectName("secondary")
        
        file_button_layout.addWidget(browse_btn)
        file_button_layout.addWidget(self.analyze_btn)
        file_button_layout.addStretch()
        
        file_layout.addWidget(self.file_label)
        file_layout.addLayout(file_button_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Package analysis results
        self.analysis_group = QGroupBox("Package Analysis")
        analysis_layout = QVBoxLayout()
        
        # Tree widget for showing package contents
        self.contents_tree = QTreeWidget()
        self.contents_tree.setHeaderLabels(["Name", "Type", "Size"])
        self.contents_tree.setColumnWidth(0, 300)
        self.contents_tree.setMaximumHeight(200)
        
        analysis_layout.addWidget(self.contents_tree)
        self.analysis_group.setLayout(analysis_layout)
        self.analysis_group.setVisible(False)
        layout.addWidget(self.analysis_group)
        
        # Installation options
        options_group = QGroupBox("Installation Options")
        options_layout = QVBoxLayout()
        
        # Install type
        install_type_layout = QHBoxLayout()
        install_type_layout.addWidget(QLabel("Install for:"))
        
        self.user_radio = QRadioButton("Current User (Recommended)")
        self.user_radio.setChecked(True)
        
        self.system_radio = QRadioButton("All Users (Requires root)")
        
        install_type_layout.addWidget(self.user_radio)
        install_type_layout.addWidget(self.system_radio)
        install_type_layout.addStretch()
        options_layout.addLayout(install_type_layout)
        
        # Options checkboxes
        self.create_desktop_entry = QCheckBox("Create application menu entry")
        self.create_desktop_entry.setChecked(True)
        
        self.create_launcher = QCheckBox("Add to application launcher")
        self.create_launcher.setChecked(True)
        
        self.update_path = QCheckBox("Add to system PATH")
        self.update_path.setChecked(True)
        
        self.track_installation = QCheckBox("Track installation for easy removal")
        self.track_installation.setChecked(True)
        
        options_layout.addWidget(self.create_desktop_entry)
        options_layout.addWidget(self.create_launcher)
        options_layout.addWidget(self.update_path)
        options_layout.addWidget(self.track_installation)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Progress section
        self.progress_group = QGroupBox("Installation Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(120)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(QLabel("Log:"))
        progress_layout.addWidget(self.log_display)
        
        self.progress_group.setLayout(progress_layout)
        self.progress_group.setVisible(False)
        layout.addWidget(self.progress_group)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_installation)
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.setVisible(False)
        
        self.install_btn = QPushButton("Install Application")
        self.install_btn.clicked.connect(self.start_installation)
        self.install_btn.setEnabled(False)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.install_btn)
        
        layout.addLayout(button_layout)
        
        self.tab_widget.addTab(install_tab, "Install")
        
    def setup_manage_tab(self):
        manage_tab = QWidget()
        layout = QVBoxLayout(manage_tab)
        
        manage_group = QGroupBox("Installed Applications")
        manage_layout = QVBoxLayout()
        
        # Toolbar
        manage_toolbar = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_apps_list)
        refresh_btn.setObjectName("secondary")
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_application)
        self.remove_btn.setEnabled(False)
        
        manage_toolbar.addWidget(refresh_btn)
        manage_toolbar.addStretch()
        manage_toolbar.addWidget(self.remove_btn)
        manage_layout.addLayout(manage_toolbar)
        
        # List of installed applications
        self.apps_list = QTreeWidget()
        self.apps_list.setHeaderLabels(["Application", "Version", "Install Date", "Type", "Status"])
        self.apps_list.setColumnWidth(0, 200)
        self.apps_list.setColumnWidth(1, 100)
        self.apps_list.setColumnWidth(2, 120)
        self.apps_list.setColumnWidth(3, 80)
        self.apps_list.itemSelectionChanged.connect(self.on_app_selection_changed)
        
        manage_layout.addWidget(self.apps_list)
        manage_group.setLayout(manage_layout)
        layout.addWidget(manage_group)
        
        # Load tracked installations
        self.load_tracked_installations()
        
        self.tab_widget.addTab(manage_tab, "Manage")
        
    def setup_help_tab(self):
        help_tab = QWidget()
        layout = QVBoxLayout(help_tab)
        
        help_group = QGroupBox("Help & Information")
        help_layout = QVBoxLayout()
        
        help_text = QLabel("""
        <div style='line-height: 1.6;'>
        <h3>Tarball Installer Help</h3>
        
        <h4>Quick Start:</h4>
        <ol>
        <li>Click <b>Browse for Tarball</b> and select your downloaded .tar.gz, .tar.bz2, or .tar.xz file</li>
        <li>Click <b>Analyze Package</b> to see what will be installed</li>
        <li>Choose installation options</li>
        <li>Click <b>Install Application</b></li>
        </ol>
        
        <h4>Features:</h4>
        <ul>
        <li><b>Package Analysis:</b> Preview tarball contents before installation</li>
        <li><b>System Integration:</b> Creates proper desktop entries and menu items</li>
        <li><b>Installation Tracking:</b> Keeps track of installed applications for easy removal</li>
        <li><b>User & System Installation:</b> Install for current user or all users</li>
        </ul>
        
        <h4>Important Notes:</h4>
        <ul>
        <li>Most tarballs can be run directly without installation</li>
        <li>Use this installer for better system integration</li>
        <li>Tracked installations can be easily removed later</li>
        <li>System-wide installation requires administrator privileges</li>
        </ul>
        
        <h4>Supported Formats:</h4>
        <p>• .tar.gz (tgz)<br>
        • .tar.bz2 (tbz2)<br>
        • .tar.xz (txz)<br>
        • Standard tar archives (.tar)</p>
        </div>
        """)
        help_text.setWordWrap(True)
        help_text.setOpenExternalLinks(True)
        
        scroll = QScrollArea()
        scroll.setWidget(help_text)
        scroll.setWidgetResizable(True)
        
        help_layout.addWidget(scroll)
        help_group.setLayout(help_layout)
        layout.addWidget(help_group)
        
        self.tab_widget.addTab(help_tab, "Help")
        
    def load_tracked_installations(self):
        """Load tracked installations into the list"""
        self.apps_list.clear()
        installations = self.tracker.get_installations()
        
        for install in installations:
            app_name = install.get('app_name', os.path.basename(install.get('source_file', 'Unknown')))
            install_time = install.get('install_time', '')
            if install_time:
                try:
                    dt = datetime.fromisoformat(install_time)
                    install_time = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            item = QTreeWidgetItem([
                app_name,
                install.get('app_version', 'Unknown'),
                install_time,
                'User' if install.get('install_type') == 'user' else 'System',
                '✓ Installed'
            ])
            item.setData(0, Qt.UserRole, install.get('app_id'))
            self.apps_list.addTopLevelItem(item)
        
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Tarball",
            str(Path.home() / "Downloads"),
            "Tarball files (*.tar.gz *.tar.bz2 *.tgz *.tar.xz *.txz *.tar);;All files (*.*)"
        )
        
        if file_path:
            self.current_file = file_path
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            
            self.file_label.setText(f"📦 <b>{file_name}</b>\n"
                                   f"Size: {file_size:.2f} MB")
            self.analyze_btn.setEnabled(True)
            self.install_btn.setEnabled(True)
            self.status_bar.showMessage(f"Selected: {file_name}")
            
    def analyze_package(self):
        if not self.current_file:
            return
            
        try:
            self.contents_tree.clear()
            
            with tarfile.open(self.current_file, 'r:*') as tar:
                # Build tree structure
                root_items = {}
                
                for member in tar.getmembers()[:100]:  # Limit to first 100 for performance
                    path_parts = member.name.split('/')
                    
                    # Create parent items as needed
                    parent = None
                    current_path = ""
                    
                    for i, part in enumerate(path_parts):
                        if not part:  # Skip empty parts
                            continue
                            
                        current_path = current_path + "/" + part if current_path else part
                        
                        if current_path not in root_items:
                            item = QTreeWidgetItem([part])
                            
                            if i == len(path_parts) - 1:  # Last part (file)
                                item.setText(1, "File")
                                if member.size:
                                    size_kb = member.size / 1024
                                    item.setText(2, f"{size_kb:.1f} KB")
                            else:  # Directory
                                item.setText(1, "Directory")
                            
                            if parent:
                                parent.addChild(item)
                            else:
                                self.contents_tree.addTopLevelItem(item)
                            
                            root_items[current_path] = item
                            parent = item
                        else:
                            parent = root_items[current_path]
                
                # Show package info
                self.analysis_group.setVisible(True)
                self.status_bar.showMessage(f"Analyzed: {len(tar.getmembers())} files/folders found")
                
        except Exception as e:
            QMessageBox.warning(self, "Analysis Error", 
                              f"Could not analyze package:\n{str(e)}")
            
    def start_installation(self):
        if not self.current_file:
            QMessageBox.warning(self, "No Package Selected",
                              "Please select a tarball file first.")
            return
        
        # Show progress section
        self.progress_group.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_display.clear()
        
        # Disable install button, enable cancel button
        self.install_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        
        # Prepare installation options
        install_type = "user" if self.user_radio.isChecked() else "system"
        options = {
            'install_type': install_type,
            'create_desktop_entry': self.create_desktop_entry.isChecked(),
            'create_launcher': self.create_launcher.isChecked(),
            'update_path': self.update_path.isChecked(),
            'track_installation': self.track_installation.isChecked()
        }
        
        # Start installation thread
        self.installer_thread = InstallerThread(
            self.current_file,
            "",  # Path will be determined in thread
            options
        )
        self.installer_thread.progress.connect(self.update_progress)
        self.installer_thread.log.connect(self.update_log)
        self.installer_thread.finished.connect(self.installation_finished)
        self.installer_thread.start()
        
        self.status_bar.showMessage("Installing...")
        
    def update_progress(self, message, value):
        self.progress_bar.setValue(value)
        self.update_log(f"[{value}%] {message}")
        
    def update_log(self, message):
        self.log_display.append(message)
        # Scroll to bottom
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_display.setTextCursor(cursor)
        
    def installation_finished(self, success, message, install_data):
        self.progress_bar.setValue(100)
        
        if success:
            self.update_log("✓ Installation completed successfully!")
            
            # Track installation if requested
            if self.track_installation.isChecked():
                self.tracker.add_installation(install_data)
                self.load_tracked_installations()  # Refresh list
            
            QMessageBox.information(self, "Installation Complete",
                                  "Application installed successfully!\n\n"
                                  "You can now find it in your application menu.")
            self.status_bar.showMessage("Installation completed successfully")
        else:
            self.update_log(f"✗ Error: {message}")
            QMessageBox.critical(self, "Installation Failed",
                               f"Installation failed:\n{message}")
            self.status_bar.showMessage("Installation failed")
        
        # Reset UI
        self.install_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        
    def cancel_installation(self):
        if hasattr(self, 'installer_thread') and self.installer_thread.isRunning():
            self.installer_thread.terminate()
            self.update_log("⏹ Installation cancelled")
            self.install_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
            self.status_bar.showMessage("Installation cancelled")
            
    def on_app_selection_changed(self):
        """Enable remove button when an app is selected"""
        self.remove_btn.setEnabled(len(self.apps_list.selectedItems()) > 0)
        
    def refresh_apps_list(self):
        """Refresh list of installed applications"""
        self.load_tracked_installations()
        self.status_bar.showMessage("Refreshed application list")
        
    def remove_application(self):
        """Remove selected application"""
        selected_items = self.apps_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        app_id = item.data(0, Qt.UserRole)
        app_name = item.text(0)
        
        reply = QMessageBox.question(self, "Remove Application",
                                   f"Are you sure you want to remove '{app_name}'?\n\n"
                                   "This will remove the application from the tracking database "
                                   "but won't uninstall files. To fully uninstall, please use "
                                   "your system's package manager or manually remove the files.",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.tracker.remove_installation(app_id)
            self.load_tracked_installations()
            self.status_bar.showMessage(f"Removed from tracking: {app_name}")
            
    def show_about_dialog(self):
        about_text = """
        <h3>Tarball Installer</h3>
        <p>Version 1.0.0</p>
        <p>A graphical tool for installing software from tarball archives.</p>
        
        <p><b>Features:</b></p>
        <ul>
        <li>Package analysis and preview</li>
        <li>System integration (desktop entries, icons)</li>
        <li>Installation tracking for easy removal</li>
        <li>User or system-wide installation</li>
        </ul>
        
        <p><b>Note:</b> Most tarballs can be run directly without installation.<br>
        This tool provides system integration for better user experience.</p>
        
        <p>© 2025 Chief Denis</p>
        """
        
        QMessageBox.about(self, "About Tarball Installer", about_text)
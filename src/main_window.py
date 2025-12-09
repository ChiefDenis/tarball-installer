from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFileDialog, QTextEdit,
                              QProgressBar, QMessageBox, QGroupBox, QTabWidget,
                              QListWidget, QListWidgetItem, QFrame,
                              QFormLayout, QCheckBox, QComboBox,
                              QSizePolicy, QSpacerItem, QSplitter, QToolBar,
                              QStatusBar, QMenu, QMenuBar, QDialog, QDialogButtonBox,
                              QRadioButton, QButtonGroup, QTreeWidget, QTreeWidgetItem,
                              QHeaderView, QScrollArea, QTableWidget,
                              QTableWidgetItem, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QAction
import subprocess
import tarfile
import os
import json
import shutil
from pathlib import Path
import tempfile
import hashlib
from datetime import datetime
import configparser
import re

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
        
        header = QLabel("Welcome to Tarball Installer")
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
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
        
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        self.show_welcome = QCheckBox("Show this welcome message on startup")
        self.show_welcome.setChecked(True)
        options_layout.addWidget(self.show_welcome)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

class BinarySelectionDialog(QDialog):
    """Dialog for manually selecting the main binary"""
    def __init__(self, binaries, parent=None):
        super().__init__(parent)
        self.binaries = binaries
        self.selected_binary = None
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Select Main Executable")
        self.setFixedSize(500, 400)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        info_label = QLabel("Multiple executables found. Please select the main application:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.binary_list = QListWidget()
        for binary in self.binaries:
            item = QListWidgetItem(os.path.basename(binary))
            item.setToolTip(binary)
            self.binary_list.addItem(item)
        
        self.binary_list.itemDoubleClicked.connect(self.accept_selection)
        layout.addWidget(self.binary_list)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_selection)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def accept_selection(self):
        selected = self.binary_list.currentItem()
        if selected:
            index = self.binary_list.row(selected)
            self.selected_binary = self.binaries[index]
            self.accept()

class InstallerThread(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished = Signal(bool, str, dict)
    
    def __init__(self, tarball_path, options, selected_binary=None):
        super().__init__()
        self.tarball_path = tarball_path
        self.options = options
        self.selected_binary = selected_binary
        self.temp_dir = None
        self.installation_data = {}
        
    def run(self):
        try:
            file_hash = hashlib.md5(self.tarball_path.encode()).hexdigest()[:12]
            self.installation_data = {
                'app_id': f"tarball_installer_{file_hash}",
                'source_file': self.tarball_path,
                'source_filename': os.path.basename(self.tarball_path),
                'install_time': datetime.now().isoformat(),
                'install_type': self.options.get('install_type', 'user'),
                'files_installed': [],
                'desktop_entries': [],
                'binaries': [],
                'marker_files': []
            }
            
            self.log.emit(f"Starting installation of {os.path.basename(self.tarball_path)}")
            
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
            
            desktop_files = self.find_desktop_files()
            binaries = self.find_binaries()
            icons = self.find_icons()
            
            # Use selected binary if provided, otherwise auto-detect
            main_binary = self.selected_binary or self.identify_main_binary(binaries, desktop_files)
            self.installation_data['main_binary'] = main_binary
            
            self.log.emit(f"Found: {len(desktop_files)} desktop files, {len(binaries)} binaries, {len(icons)} icons")
            if main_binary:
                self.log.emit(f"Using binary: {os.path.basename(main_binary)}")
            
            self.installation_data['desktop_files'] = [os.path.basename(f) for f in desktop_files]
            self.installation_data['binaries'] = [os.path.basename(f) for f in binaries]
            
            if self.options.get('install_type') == 'user':
                install_data = self.install_to_user(desktop_files, binaries, icons, main_binary)
            else:
                install_data = self.install_system_wide(desktop_files, binaries, icons, main_binary)
            
            self.installation_data.update(install_data)
            
            self.progress.emit("Cleaning up...", 95)
            
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            self.progress.emit("Installation complete!", 100)
            self.finished.emit(True, "Application installed successfully!", self.installation_data)
            
        except Exception as e:
            self.log.emit(f"Error: {str(e)}")
            self.finished.emit(False, str(e), {})
    
    def find_desktop_files(self):
        desktop_files = []
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if file.endswith('.desktop'):
                    desktop_files.append(os.path.join(root, file))
        return desktop_files
    
    def find_binaries(self):
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
        icons = []
        icon_extensions = ['.png', '.svg', '.xpm', '.ico']
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if any(file.lower().endswith(ext) for ext in icon_extensions):
                    if 'icon' in file.lower() or 'icons' in root.lower():
                        icons.append(os.path.join(root, file))
        return icons
    
    def identify_main_binary(self, binaries, desktop_files):
        if not binaries:
            return None
        
        # Check desktop file first
        if desktop_files:
            desktop_info = self.parse_desktop_file(desktop_files[0])
            exec_cmd = desktop_info.get('exec', '')
            if exec_cmd:
                exec_binary = exec_cmd.split()[0] if ' ' in exec_cmd else exec_cmd
                exec_binary = os.path.basename(exec_binary)
                for binary in binaries:
                    if os.path.basename(binary) == exec_binary:
                        return binary
        
        # Simple scoring - prefer binaries in bin directories
        scored_binaries = []
        for binary in binaries:
            score = 0
            bin_name = os.path.basename(binary)
            
            if 'bin' in binary:
                score += 10
            
            if '.' not in bin_name:
                score += 5
            elif bin_name.endswith(('.sh', '.py', '.pl')):
                score += 3
            
            # Common patterns
            main_patterns = ['app', 'main', 'run', 'start']
            if any(pattern in bin_name.lower() for pattern in main_patterns):
                score += 8
            
            # Avoid clear uninstallers if we have alternatives
            if 'uninstall' in bin_name.lower() or 'remove' in bin_name.lower():
                score -= 5
            
            scored_binaries.append((binary, score))
        
        scored_binaries.sort(key=lambda x: x[1], reverse=True)
        return scored_binaries[0][0] if scored_binaries else binaries[0]
    
    def parse_desktop_file(self, desktop_path):
        config = configparser.ConfigParser()
        try:
            config.read(desktop_path)
            if 'Desktop Entry' in config:
                return {
                    'name': config['Desktop Entry'].get('Name', 'Unknown'),
                    'comment': config['Desktop Entry'].get('Comment', ''),
                    'exec': config['Desktop Entry'].get('Exec', ''),
                    'icon': config['Desktop Entry'].get('Icon', ''),
                    'categories': config['Desktop Entry'].get('Categories', '').split(';'),
                    'version': config['Desktop Entry'].get('Version', '1.0')
                }
        except:
            pass
        return {}
    
    def create_marker_file(self, directory, app_info):
        marker_data = {
            'installed_by': 'Tarball Installer',
            'installer_version': '0.13.0',
            'app_id': self.installation_data['app_id'],
            'app_name': app_info.get('name', os.path.basename(self.tarball_path)),
            'app_version': app_info.get('version', '1.0'),
            'install_time': datetime.now().isoformat(),
            'install_type': self.options.get('install_type', 'user'),
            'tarball_source': os.path.basename(self.tarball_path)
        }
        
        marker_path = directory / '.tarball-installer-marker.json'
        with open(marker_path, 'w') as f:
            json.dump(marker_data, f, indent=2)
        
        return str(marker_path)
    
    def install_to_user(self, desktop_files, binaries, icons, main_binary):
        home = Path.home()
        local_bin = home / '.local' / 'bin'
        local_apps = home / '.local' / 'share' / 'applications'
        local_icons = home / '.local' / 'share' / 'icons'
        
        local_bin.mkdir(parents=True, exist_ok=True)
        local_apps.mkdir(parents=True, exist_ok=True)
        local_icons.mkdir(parents=True, exist_ok=True)
        
        install_data = {
            'install_path': str(local_bin),
            'desktop_path': str(local_apps),
            'installed_files': [],
            'marker_files': []
        }
        
        # Get app info
        app_info = {}
        if desktop_files:
            app_info = self.parse_desktop_file(desktop_files[0])
            if app_info.get('name'):
                self.installation_data['app_name'] = app_info['name']
                self.installation_data['app_version'] = app_info.get('version', '1.0')
        else:
            # Create app name from filename
            app_name = os.path.basename(self.tarball_path)
            app_name = re.sub(r'\.(tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|txz)$', '', app_name)
            app_name = re.sub(r'[-_]', ' ', app_name).title()
            self.installation_data['app_name'] = app_name
            self.installation_data['app_version'] = '1.0'
            
            # Create desktop file
            if main_binary:
                desktop_content = f"""[Desktop Entry]
Name={app_name}
Exec={os.path.basename(main_binary)}
Type=Application
Categories=Utility;
Comment=Installed via Tarball Installer
"""
                desktop_path = Path(self.temp_dir) / f"{app_name.lower().replace(' ', '-')}.desktop"
                desktop_path.write_text(desktop_content)
                desktop_files = [str(desktop_path)]
                app_info = {'name': app_name, 'version': '1.0'}
        
        # Create marker file
        marker_path = self.create_marker_file(local_bin, app_info)
        install_data['marker_files'].append(marker_path)
        self.log.emit(f"Created marker file: {marker_path}")
        
        # Install binaries
        for binary in binaries:
            dest = local_bin / os.path.basename(binary)
            shutil.copy2(binary, dest)
            dest.chmod(0o755)
            install_data['installed_files'].append(str(dest))
        
        # Fix desktop file paths for installed binaries
        for desktop in desktop_files:
            desktop_content = Path(desktop).read_text()
            # Replace relative paths with absolute paths to installed location
            desktop_content = desktop_content.replace('./', '')
            desktop_content = desktop_content.replace('Exec=', f'Exec={local_bin}/')
            
            dest = local_apps / os.path.basename(desktop)
            dest.write_text(desktop_content)
            install_data['installed_files'].append(str(dest))
            self.log.emit(f"Installed desktop entry: {dest}")
        
        # Install icons
        for icon in icons:
            dest_dir = local_icons / 'hicolor' / 'scalable' / 'apps'
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / os.path.basename(icon)
            shutil.copy2(icon, dest)
            install_data['installed_files'].append(str(dest))
        
        # Update desktop database
        try:
            subprocess.run(['update-desktop-database', str(local_apps)], check=True)
            self.log.emit("Updated desktop database")
        except subprocess.CalledProcessError as e:
            self.log.emit(f"Warning: Failed to update desktop database: {e}")
        
        return install_data

class UninstallThread(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, installation_data):
        super().__init__()
        self.installation_data = installation_data
        
    def run(self):
        try:
            app_name = self.installation_data.get('app_name', 'Unknown')
            self.log.emit(f"Starting uninstallation of {app_name}")
            self.progress.emit("Preparing uninstallation...", 10)
            
            installed_files = self.installation_data.get('installed_files', [])
            marker_files = self.installation_data.get('marker_files', [])
            
            removed_count = 0
            total_files = len(installed_files) + len(marker_files)
            
            # Remove installed files
            for i, file_path in enumerate(installed_files):
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        removed_count += 1
                    except Exception as e:
                        self.log.emit(f"Warning: Could not remove {file_path}: {e}")
                
                progress = 10 + int((i / total_files) * 70)
                self.progress.emit("Removing files...", progress)
            
            # Remove marker files
            for i, marker_path in enumerate(marker_files):
                if os.path.exists(marker_path):
                    try:
                        os.remove(marker_path)
                        removed_count += 1
                    except:
                        pass
                
                progress = 80 + int((i / len(marker_files)) * 10)
                self.progress.emit("Cleaning up...", progress)
            
            # Update desktop database
            if any('.desktop' in f for f in installed_files):
                try:
                    home = Path.home()
                    local_apps = home / '.local' / 'share' / 'applications'
                    subprocess.run(['update-desktop-database', str(local_apps)], check=True)
                    self.log.emit("Updated desktop database")
                except:
                    self.log.emit("Warning: Could not update desktop database")
            
            self.progress.emit("Uninstallation complete!", 100)
            self.finished.emit(True, f"Successfully removed {removed_count} files")
            
        except Exception as e:
            self.log.emit(f"Error during uninstallation: {str(e)}")
            self.finished.emit(False, str(e))

class InstallationTracker:
    """Track installed applications"""
    
    def __init__(self):
        self.db_path = Path.home() / '.local' / 'share' / 'tarball-installer' / 'installations.json'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.installations = self.load_installations()
        self.scan_existing_installations()
    
    def load_installations(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def save_installations(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.installations, f, indent=2)
    
    def add_installation(self, data):
        for inst in self.installations:
            if inst.get('app_id') == data.get('app_id'):
                inst.update(data)
                self.save_installations()
                return
        
        self.installations.append(data)
        self.save_installations()
    
    def remove_installation(self, app_id):
        self.installations = [inst for inst in self.installations if inst.get('app_id') != app_id]
        self.save_installations()
    
    def get_installations(self):
        return self.installations
    
    def get_installation_by_id(self, app_id):
        for inst in self.installations:
            if inst.get('app_id') == app_id:
                return inst
        return None
    
    def scan_existing_installations(self):
        home = Path.home()
        scan_paths = [
            home / '.local' / 'bin',
            home / '.local' / 'share' / 'applications',
            home / '.local' / 'share' / 'icons',
            home / 'Applications',
            home / 'bin'
        ]
        
        found_markers = []
        for scan_path in scan_paths:
            if scan_path.exists():
                for marker_file in scan_path.rglob('.tarball-installer-marker.json'):
                    try:
                        with open(marker_file, 'r') as f:
                            marker_data = json.load(f)
                        
                        app_id = marker_data.get('app_id')
                        already_tracked = any(inst.get('app_id') == app_id for inst in self.installations)
                        
                        if not already_tracked:
                            installation_data = {
                                'app_id': app_id,
                                'app_name': marker_data.get('app_name', 'Unknown'),
                                'app_version': marker_data.get('app_version', '1.0'),
                                'install_time': marker_data.get('install_time', ''),
                                'install_type': marker_data.get('install_type', 'user'),
                                'source_filename': marker_data.get('tarball_source', ''),
                                'discovered': True,
                                'marker_file': str(marker_file),
                                'installed_files': []
                            }
                            self.installations.append(installation_data)
                            found_markers.append(marker_data.get('app_name', 'Unknown'))
                    except:
                        pass
        
        if found_markers:
            self.save_installations()
    
    def cleanup_orphaned_markers(self):
        home = Path.home()
        orphaned_markers = []
        
        for marker_file in home.rglob('.tarball-installer-marker.json'):
            try:
                with open(marker_file, 'r') as f:
                    marker_data = json.load(f)
                
                app_id = marker_data.get('app_id')
                is_tracked = any(inst.get('app_id') == app_id for inst in self.installations)
                
                if not is_tracked:
                    orphaned_markers.append(marker_file)
            except:
                continue
        
        removed_count = 0
        for marker_file in orphaned_markers:
            try:
                marker_file.unlink()
                removed_count += 1
            except:
                pass
        
        return len(orphaned_markers), removed_count

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tracker = InstallationTracker()
        self.current_file = None
        self.detected_binaries = []
        self.user_selected_binary = None
        
        self.setup_ui()
        self.setup_style()
        self.show_welcome_dialog()
        
    def show_welcome_dialog(self):
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
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_path, 'w') as f:
                    json.dump({'show_welcome': dialog.show_welcome.isChecked()}, f)
        
    def setup_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #fcfcfc; }
            QWidget { font-family: 'Noto Sans', 'Roboto', sans-serif; font-size: 10pt; color: #232629; }
            QGroupBox { font-weight: bold; border: 1px solid #c2c7cb; border-radius: 4px; 
                       margin-top: 12px; padding-top: 12px; background-color: #fcfcfc; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px; color: #232629; }
            QPushButton { background-color: #3daee9; border: none; border-radius: 4px; color: white; 
                         padding: 6px 16px; font-weight: bold; min-height: 24px; min-width: 80px; }
            QPushButton:hover { background-color: #1d99e3; }
            QPushButton:pressed { background-color: #0d8add; }
            QPushButton:disabled { background-color: #bdc3c7; color: #7f8c8d; }
            QPushButton#secondary { background-color: transparent; border: 1px solid #c2c7cb; color: #232629; }
            QPushButton#secondary:hover { background-color: #eff0f1; border-color: #93cee9; }
            QPushButton#danger { background-color: #da4453; color: white; }
            QPushButton#danger:hover { background-color: #c03d4a; }
            QLabel { color: #232629; }
            QLabel#title { font-size: 18pt; font-weight: bold; color: #232629; }
            QLabel#subtitle { font-size: 10pt; color: #5e646b; }
            QProgressBar { border: 1px solid #c2c7cb; border-radius: 2px; background-color: #fcfcfc; 
                          text-align: center; height: 16px; }
            QProgressBar::chunk { background-color: #3daee9; border-radius: 2px; }
            QTextEdit { border: 1px solid #c2c7cb; border-radius: 4px; background-color: white; 
                       font-family: 'Monospace', 'Consolas', 'Courier New'; font-size: 9pt; 
                       padding: 8px; selection-background-color: #3daee9; selection-color: white; }
            QTreeWidget, QTableWidget { border: 1px solid #c2c7cb; border-radius: 4px; background-color: white; }
            QTreeWidget::item, QTableWidget::item { padding: 4px; }
            QTreeWidget::item:selected, QTableWidget::item:selected { background-color: #3daee9; color: white; }
            QHeaderView::section { background-color: #eff0f1; padding: 6px; border: 1px solid #c2c7cb; }
            QSplitter::handle { background-color: #c2c7cb; width: 4px; }
            QSplitter::handle:hover { background-color: #93cee9; }
            QTabWidget::pane { border: 1px solid #c2c7cb; border-radius: 4px; background-color: #fcfcfc; top: -1px; }
            QTabBar::tab { background-color: #eff0f1; color: #5e646b; padding: 8px 16px; margin-right: 1px; 
                          border: 1px solid #c2c7cb; border-bottom: none; border-top-left-radius: 4px; 
                          border-top-right-radius: 4px; }
            QTabBar::tab:selected { background-color: #fcfcfc; color: #232629; border-bottom: 1px solid #fcfcfc; 
                                   margin-bottom: -1px; }
        """)
        
        self.setWindowIcon(QIcon.fromTheme("application-x-tar"))
        
    def setup_ui(self):
        self.setWindowTitle("Tarball Installer")
        self.setGeometry(100, 100, 900, 650)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        self.setup_menu_bar()
        
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
        
        self.tab_widget = QTabWidget()
        self.setup_install_tab()
        self.setup_manage_tab()
        self.setup_help_tab()
        
        main_layout.addWidget(self.tab_widget, 1)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Auto-scanned for existing installations")
        
    def setup_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("&File")
        open_action = QAction("&Open Tarball...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.browse_file)
        file_menu.addAction(open_action)
        
        scan_action = QAction("&Scan for Existing Installations", self)
        scan_action.triggered.connect(self.scan_installations)
        file_menu.addAction(scan_action)
        
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        view_menu = menubar.addMenu("&View")
        welcome_action = QAction("Show &Welcome Message", self)
        welcome_action.triggered.connect(self.show_welcome_dialog)
        view_menu.addAction(welcome_action)
        
        tools_menu = menubar.addMenu("&Tools")
        refresh_action = QAction("&Refresh Application List", self)
        refresh_action.triggered.connect(self.refresh_apps_list)
        tools_menu.addAction(refresh_action)
        
        cleanup_action = QAction("&Cleanup Orphaned Markers", self)
        cleanup_action.triggered.connect(self.cleanup_markers)
        tools_menu.addAction(cleanup_action)
        
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        
    def setup_install_tab(self):
        install_tab = QWidget()
        main_layout = QHBoxLayout(install_tab)
        main_layout.setSpacing(12)
        
        # Left panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)
        
        file_group = QGroupBox("Package Selection")
        file_layout = QVBoxLayout()
        
        self.file_label = QLabel("No package selected")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("padding: 8px; background-color: #eff0f1; border-radius: 4px; min-height: 40px;")
        
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
        left_layout.addWidget(file_group)
        
        # Binary selection
        self.binary_selection_group = QGroupBox("Executable Selection")
        binary_layout = QVBoxLayout()
        
        self.binary_label = QLabel("Automatic selection will be used")
        self.binary_label.setWordWrap(True)
        self.binary_label.setStyleSheet("padding: 8px; background-color: #eff0f1; border-radius: 4px; min-height: 40px;")
        
        binary_button_layout = QHBoxLayout()
        self.select_binary_btn = QPushButton("Select Manually...")
        self.select_binary_btn.clicked.connect(self.select_binary_manually)
        self.select_binary_btn.setEnabled(False)
        self.select_binary_btn.setObjectName("secondary")
        
        self.clear_selection_btn = QPushButton("Clear Selection")
        self.clear_selection_btn.clicked.connect(self.clear_binary_selection)
        self.clear_selection_btn.setEnabled(False)
        self.clear_selection_btn.setObjectName("secondary")
        
        binary_button_layout.addWidget(self.select_binary_btn)
        binary_button_layout.addWidget(self.clear_selection_btn)
        binary_button_layout.addStretch()
        
        binary_layout.addWidget(self.binary_label)
        binary_layout.addLayout(binary_button_layout)
        self.binary_selection_group.setLayout(binary_layout)
        self.binary_selection_group.setVisible(False)
        left_layout.addWidget(self.binary_selection_group)
        
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #5e646b; font-size: 9pt; padding: 4px;")
        left_layout.addWidget(self.stats_label)
        
        options_group = QGroupBox("Installation Options")
        options_layout = QVBoxLayout()
        
        install_type_layout = QHBoxLayout()
        install_type_layout.addWidget(QLabel("Install for:"))
        self.user_radio = QRadioButton("Current User")
        self.user_radio.setChecked(True)
        self.system_radio = QRadioButton("All Users (Requires root)")
        install_type_layout.addWidget(self.user_radio)
        install_type_layout.addWidget(self.system_radio)
        install_type_layout.addStretch()
        options_layout.addLayout(install_type_layout)
        
        self.create_desktop_entry = QCheckBox("Create application menu entry")
        self.create_desktop_entry.setChecked(True)
        options_layout.addWidget(self.create_desktop_entry)
        options_group.setLayout(options_layout)
        left_layout.addWidget(options_group)
        
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
        left_layout.addWidget(self.progress_group)
        
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
        left_layout.addLayout(button_layout)
        left_layout.addStretch()
        
        # Right panel - Analysis
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)
        
        analysis_group = QGroupBox("Package Analysis")
        analysis_layout = QVBoxLayout()
        
        self.analysis_info_label = QLabel("No package analyzed yet.\nClick 'Analyze Package' to view contents.")
        self.analysis_info_label.setWordWrap(True)
        self.analysis_info_label.setStyleSheet("padding: 8px; background-color: #eff0f1; border-radius: 4px; min-height: 60px;")
        analysis_layout.addWidget(self.analysis_info_label)
        
        self.contents_table = QTableWidget()
        self.contents_table.setColumnCount(3)
        self.contents_table.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.contents_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.contents_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.contents_table.horizontalHeader().setStretchLastSection(True)
        self.contents_table.verticalHeader().setVisible(False)
        analysis_layout.addWidget(self.contents_table, 1)
        analysis_group.setLayout(analysis_layout)
        right_layout.addWidget(analysis_group, 1)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 400])
        main_layout.addWidget(splitter)
        
        self.tab_widget.addTab(install_tab, "Install")
        
    def setup_manage_tab(self):
        manage_tab = QWidget()
        layout = QVBoxLayout(manage_tab)
        
        manage_group = QGroupBox("Installed Applications")
        manage_layout = QVBoxLayout()
        
        manage_toolbar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_apps_list)
        refresh_btn.setObjectName("secondary")
        scan_btn = QPushButton("Scan for Markers")
        scan_btn.clicked.connect(self.scan_installations)
        scan_btn.setObjectName("secondary")
        self.uninstall_btn = QPushButton("Uninstall Selected")
        self.uninstall_btn.clicked.connect(self.uninstall_application)
        self.uninstall_btn.setEnabled(False)
        self.uninstall_btn.setObjectName("danger")
        self.remove_tracking_btn = QPushButton("Remove from Tracking")
        self.remove_tracking_btn.clicked.connect(self.remove_from_tracking)
        self.remove_tracking_btn.setEnabled(False)
        self.remove_tracking_btn.setObjectName("secondary")
        
        manage_toolbar.addWidget(refresh_btn)
        manage_toolbar.addWidget(scan_btn)
        manage_toolbar.addStretch()
        manage_toolbar.addWidget(self.remove_tracking_btn)
        manage_toolbar.addWidget(self.uninstall_btn)
        manage_layout.addLayout(manage_toolbar)
        
        self.apps_list = QTreeWidget()
        self.apps_list.setHeaderLabels(["Application", "Version", "Install Date", "Type", "Status"])
        self.apps_list.setColumnWidth(0, 180)
        self.apps_list.setColumnWidth(1, 80)
        self.apps_list.setColumnWidth(2, 120)
        self.apps_list.setColumnWidth(3, 60)
        self.apps_list.itemSelectionChanged.connect(self.on_app_selection_changed)
        manage_layout.addWidget(self.apps_list)
        manage_group.setLayout(manage_layout)
        layout.addWidget(manage_group)
        
        self.load_tracked_installations()
        self.tab_widget.addTab(manage_tab, "Manage")
        
    def setup_help_tab(self):
        help_tab = QWidget()
        layout = QVBoxLayout(help_tab)
        
        help_group = QGroupBox("Help & Information")
        help_layout = QVBoxLayout()
        
        help_text = QLabel("""
        <div style='line-height: 1.6;'>
        <h3>Tarball Installer v0.13.0</h3>
        
        <h4>Quick Start:</h4>
        <ol>
        <li>Go to <b>Install</b> tab and click <b>Browse for Tarball</b></li>
        <li>Select your downloaded .tar.gz, .tar.bz2, or .tar.xz file</li>
        <li>Click <b>Analyze Package</b> to see detailed contents in the sidebar</li>
        <li>If automatic detection fails, use <b>Select Manually</b> to choose the main executable</li>
        <li>Choose installation options</li>
        <li>Click <b>Install Application</b></li>
        </ol>
        
        <h4>Key Features:</h4>
        <ul>
        <li><b>Manual Binary Selection:</b> Override automatic detection when needed</li>
        <li><b>Smart Analysis:</b> Preview tarball contents with visual indicators</li>
        <li><b>System Integration:</b> Creates proper desktop entries</li>
        <li><b>Mandatory Tracking:</b> Always creates marker files for uninstallation</li>
        <li><b>Complete Uninstallation:</b> Removes all files and markers</li>
        <li><b>Auto-detection:</b> Finds existing installations on startup</li>
        </ul>
        
        <h4>For Complex Applications (like Blender):</h4>
        <p>Some applications have complex launch scripts or wrappers. If automatic selection
        doesn't work, use the <b>Select Manually</b> button to choose the correct executable.</p>
        
        <h4>Marker Files:</h4>
        <p>Marker files (<code>.tarball-installer-marker.json</code>) are always created
        for tracking and are only removed during full uninstallation.</p>
        </div>
        """)
        help_text.setWordWrap(True)
        
        scroll = QScrollArea()
        scroll.setWidget(help_text)
        scroll.setWidgetResizable(True)
        help_layout.addWidget(scroll)
        help_group.setLayout(help_layout)
        layout.addWidget(help_group)
        
        self.tab_widget.addTab(help_tab, "Help")
        
    def load_tracked_installations(self):
        self.apps_list.clear()
        for install in self.tracker.get_installations():
            app_name = install.get('app_name', os.path.basename(install.get('source_file', 'Unknown')))
            install_time = install.get('install_time', '')
            if install_time:
                try:
                    dt = datetime.fromisoformat(install_time)
                    install_time = dt.strftime("%Y-%m-%d")
                except:
                    pass
            
            status = '✓ Installed'
            if install.get('discovered'):
                status = '🔍 Discovered'
            
            item = QTreeWidgetItem([
                app_name,
                install.get('app_version', 'Unknown'),
                install_time,
                'User' if install.get('install_type') == 'user' else 'System',
                status
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
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            
            self.file_label.setText(f"📦 <b>{file_name}</b><br>Size: {file_size:.2f} MB")
            self.analyze_btn.setEnabled(True)
            self.install_btn.setEnabled(True)
            self.status_bar.showMessage(f"Selected: {file_name}")
            
    def analyze_package(self):
        if not self.current_file:
            return
            
        try:
            self.contents_table.setRowCount(0)
            self.detected_binaries = []
            
            with tarfile.open(self.current_file, 'r:*') as tar:
                members = tar.getmembers()
                
                file_name = os.path.basename(self.current_file)
                file_size = os.path.getsize(self.current_file) / (1024 * 1024)
                self.analysis_info_label.setText(f"📦 <b>{file_name}</b><br>Size: {file_size:.2f} MB<br>Total items: {len(members)}")
                
                # Find binaries
                for m in members:
                    if not m.isdir() and ('/bin/' in m.name or m.name.endswith(('.sh', '.bin', '.run', '.py', '.pl'))):
                        self.detected_binaries.append(m.name)
                
                desktop_files = [m for m in members if m.name.endswith('.desktop')]
                icons = [m for m in members if m.name.endswith(('.png', '.svg', '.xpm', '.ico'))]
                
                # Show binary selection if multiple found
                if len(self.detected_binaries) > 1:
                    self.binary_selection_group.setVisible(True)
                    self.select_binary_btn.setEnabled(True)
                    self.binary_label.setText(f"Multiple executables detected ({len(self.detected_binaries)} found).\nAutomatic selection will be used, or select manually.")
                else:
                    self.binary_selection_group.setVisible(False)
                    self.user_selected_binary = None
                
                self.stats_label.setText(f"📊 Found: {len(desktop_files)} desktop entries, {len(self.detected_binaries)} binaries, {len(icons)} icons")
                
                # Display contents
                display_members = members[:100] if len(members) > 100 else members
                self.contents_table.setRowCount(len(display_members))
                
                for row, member in enumerate(display_members):
                    name = os.path.basename(member.name)
                    if member.name.endswith('.desktop'):
                        display_name = f"📄 {name}"
                    elif member.name in self.detected_binaries:
                        display_name = f"⚙️ {name}"
                    elif member.name.endswith(('.png', '.svg', '.ico')):
                        display_name = f"🎨 {name}"
                    else:
                        display_name = name
                    
                    name_item = QTableWidgetItem(display_name)
                    
                    if member.isdir():
                        type_item = QTableWidgetItem("📁 Directory")
                    elif member.isfile():
                        type_item = QTableWidgetItem("📄 File")
                    elif member.issym():
                        type_item = QTableWidgetItem("🔗 Symlink")
                    else:
                        type_item = QTableWidgetItem("❓ Other")
                    
                    if member.isfile():
                        size_kb = member.size / 1024
                        size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                        size_item = QTableWidgetItem(size_text)
                    else:
                        size_item = QTableWidgetItem("")
                    
                    self.contents_table.setItem(row, 0, name_item)
                    self.contents_table.setItem(row, 1, type_item)
                    self.contents_table.setItem(row, 2, size_item)
                
                self.contents_table.resizeColumnsToContents()
                self.status_bar.showMessage(f"Analyzed: {len(members)} items found")
                
        except Exception as e:
            QMessageBox.warning(self, "Analysis Error", f"Could not analyze package:\n{str(e)}")
    
    def select_binary_manually(self):
        if not self.detected_binaries:
            return
        
        # Extract actual binary paths from tarball
        temp_dir = tempfile.mkdtemp(prefix="tarball_analyze_")
        try:
            with tarfile.open(self.current_file, 'r:*') as tar:
                # Extract only binaries for the dialog
                binary_paths = []
                for member in tar.getmembers():
                    if member.name in self.detected_binaries:
                        tar.extract(member, temp_dir)
                        binary_paths.append(os.path.join(temp_dir, member.name))
            
            if binary_paths:
                dialog = BinarySelectionDialog(binary_paths, self)
                if dialog.exec() and dialog.selected_binary:
                    self.user_selected_binary = dialog.selected_binary
                    bin_name = os.path.basename(self.user_selected_binary)
                    self.binary_label.setText(f"✅ Manual selection: <b>{bin_name}</b>")
                    self.clear_selection_btn.setEnabled(True)
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def clear_binary_selection(self):
        self.user_selected_binary = None
        self.binary_label.setText("Automatic selection will be used")
        self.clear_selection_btn.setEnabled(False)
    
    def start_installation(self):
        if not self.current_file:
            QMessageBox.warning(self, "No Package Selected", "Please select a tarball file first.")
            return
        
        self.progress_group.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_display.clear()
        self.install_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        
        install_type = "user" if self.user_radio.isChecked() else "system"
        options = {
            'install_type': install_type,
            'create_desktop_entry': self.create_desktop_entry.isChecked()
        }
        
        self.installer_thread = InstallerThread(
            self.current_file,
            options,
            self.user_selected_binary
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
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_display.setTextCursor(cursor)
        
    def installation_finished(self, success, message, install_data):
        self.progress_bar.setValue(100)
        
        if success:
            self.update_log("✓ Installation completed successfully!")
            self.update_log("✓ Marker file created for tracking")
            
            self.tracker.add_installation(install_data)
            self.load_tracked_installations()
            
            main_binary = install_data.get('main_binary')
            binary_info = f"\nExecutable: {os.path.basename(main_binary)}" if main_binary else ""
            
            QMessageBox.information(self, "Installation Complete",
                                  f"Application installed successfully!{binary_info}\n\n"
                                  "You can now find it in your application menu.")
            self.status_bar.showMessage("Installation completed successfully")
        else:
            self.update_log(f"✗ Error: {message}")
            QMessageBox.critical(self, "Installation Failed", f"Installation failed:\n{message}")
            self.status_bar.showMessage("Installation failed")
        
        self.install_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)
        
    def cancel_installation(self):
        if hasattr(self, 'installer_thread') and self.installer_thread.isRunning():
            self.installer_thread.terminate()
            self.update_log("⏹ Installation cancelled")
            self.install_btn.setEnabled(True)
            self.cancel_btn.setVisible(False)
            self.status_bar.showMessage("Installation cancelled")
            
    def scan_installations(self):
        self.tracker.scan_existing_installations()
        self.load_tracked_installations()
        count = len(self.tracker.get_installations())
        self.status_bar.showMessage(f"Found {count} tracked installations")
        QMessageBox.information(self, "Scan Complete", f"Found {count} installations.")
    
    def cleanup_markers(self):
        total_found, removed_count = self.tracker.cleanup_orphaned_markers()
        if total_found > 0:
            self.status_bar.showMessage(f"Cleaned up {removed_count}/{total_found} orphaned markers")
            QMessageBox.information(self, "Cleanup Complete", f"Removed {removed_count} orphaned markers.")
        else:
            self.status_bar.showMessage("No orphaned markers found")
            QMessageBox.information(self, "Cleanup Complete", "No orphaned markers found.")
    
    def on_app_selection_changed(self):
        has_selection = len(self.apps_list.selectedItems()) > 0
        self.uninstall_btn.setEnabled(has_selection)
        self.remove_tracking_btn.setEnabled(has_selection)
        
    def uninstall_application(self):
        selected_items = self.apps_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        app_id = item.data(0, Qt.UserRole)
        app_name = item.text(0)
        
        install_data = self.tracker.get_installation_by_id(app_id)
        if not install_data:
            QMessageBox.warning(self, "Cannot Uninstall", f"No installation data found for '{app_name}'.")
            return
        
        reply = QMessageBox.warning(self, "Confirm Uninstallation",
                                   f"Are you sure you want to completely uninstall '{app_name}'?\n\n"
                                   "This will remove all files, markers, and desktop entries.\n"
                                   "This action cannot be undone!",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.uninstall_thread = UninstallThread(install_data)
            self.uninstall_thread.progress.connect(self.update_uninstall_progress)
            self.uninstall_thread.log.connect(self.update_uninstall_log)
            self.uninstall_thread.finished.connect(self.uninstallation_finished)
            
            self.uninstall_dialog = QDialog(self)
            self.uninstall_dialog.setWindowTitle(f"Uninstalling {app_name}")
            self.uninstall_dialog.setFixedSize(500, 300)
            layout = QVBoxLayout(self.uninstall_dialog)
            layout.addWidget(QLabel(f"Uninstalling {app_name}..."))
            self.uninstall_progress = QProgressBar()
            layout.addWidget(self.uninstall_progress)
            self.uninstall_log_display = QTextEdit()
            self.uninstall_log_display.setReadOnly(True)
            layout.addWidget(self.uninstall_log_display)
            self.uninstall_dialog.show()
            self.uninstall_thread.start()
    
    def update_uninstall_progress(self, message, value):
        if hasattr(self, 'uninstall_progress'):
            self.uninstall_progress.setValue(value)
            self.update_uninstall_log(f"[{value}%] {message}")
    
    def update_uninstall_log(self, message):
        if hasattr(self, 'uninstall_log_display'):
            self.uninstall_log_display.append(message)
            cursor = self.uninstall_log_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.uninstall_log_display.setTextCursor(cursor)
    
    def uninstallation_finished(self, success, message):
        if hasattr(self, 'uninstall_dialog'):
            self.uninstall_dialog.accept()
        
        if success:
            selected_items = self.apps_list.selectedItems()
            if selected_items:
                app_id = selected_items[0].data(0, Qt.UserRole)
                self.tracker.remove_installation(app_id)
                self.load_tracked_installations()
            
            QMessageBox.information(self, "Uninstallation Complete", message)
            self.status_bar.showMessage("Application uninstalled successfully")
        else:
            QMessageBox.critical(self, "Uninstallation Failed", message)
            self.status_bar.showMessage("Uninstallation failed")
            
    def remove_from_tracking(self):
        selected_items = self.apps_list.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        app_id = item.data(0, Qt.UserRole)
        app_name = item.text(0)
        
        reply = QMessageBox.question(self, "Remove from Tracking",
                                   f"Remove '{app_name}' from tracking?\n\n"
                                   "This will remove from database but keep files.\n"
                                   "Will be redetected on scan.",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.tracker.remove_installation(app_id)
            self.load_tracked_installations()
            self.status_bar.showMessage(f"Removed from tracking: {app_name}")
        
    def refresh_apps_list(self):
        self.load_tracked_installations()
        self.status_bar.showMessage("Refreshed application list")
        
    def show_about_dialog(self):
        about_text = """
        <h3>Tarball Installer v0.13.0</h3>
        <p>A graphical tool for installing software from tarball archives.</p>
        
        <p><b>Key Features:</b></p>
        <ul>
        <li>Manual binary selection for complex applications</li>
        <li>Smart package analysis with sidebar preview</li>
        <li>System integration (desktop entries, icons)</li>
        <li>Mandatory marker files for installation tracking</li>
        <li>Complete uninstallation with file removal</li>
        <li>Auto-detection of existing installations</li>
        </ul>
        
        <p><b>Note:</b> Most tarballs can be run directly without installation.
        This tool provides system integration for better user experience.</p>
        
        <p>© 2025 Chief Denis</p>
        """
        
        QMessageBox.about(self, "About Tarball Installer", about_text)
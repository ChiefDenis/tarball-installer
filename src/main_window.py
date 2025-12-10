# Version constant at the top
__version__ = "0.23.6"

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFileDialog, QTextEdit,
                              QProgressBar, QMessageBox, QGroupBox, QTabWidget,
                              QListWidget, QListWidgetItem,
                              QFormLayout, QCheckBox,
                              QSizePolicy, QSpacerItem, QSplitter, QToolBar,
                              QStatusBar, QMenu, QMenuBar, QDialog, QDialogButtonBox,
                              QRadioButton, QButtonGroup, QTreeWidget, QTreeWidgetItem,
                              QHeaderView, QScrollArea, QTableWidget,
                              QTableWidgetItem, QAbstractItemView)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon, QAction
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
        
        info_text = QLabel(f"""
        <div style='line-height: 1.6;'>
        <h3>Tarball Installer v{__version__}</h3>
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

class InstallerThread(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished = Signal(bool, str, dict)
    
    def __init__(self, tarball_path, options, selected_binary=None, extracted_dir=None):
        super().__init__()
        self.tarball_path = tarball_path
        self.options = options
        self.selected_binary = selected_binary
        self.extracted_dir = extracted_dir  # NEW: Reuse existing extraction
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
                'marker_files': [],
                'installer_version': __version__
            }
            
            self.log.emit(f"Starting installation of {os.path.basename(self.tarball_path)}")
            
            # If we have an extracted directory, reuse it
            if self.extracted_dir and os.path.exists(self.extracted_dir):
                self.temp_dir = self.extracted_dir
                self.progress.emit("Using existing extraction...", 30)
            else:
                # Otherwise extract fresh
                self.temp_dir = tempfile.mkdtemp(prefix="tarball_installer_")
                self.progress.emit("Preparing installation...", 10)
                
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
            
            # Only clean up if we created a new temp dir (not if we reused one)
            if self.temp_dir and not self.extracted_dir:
                if os.path.exists(self.temp_dir):
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
        """Find executable binaries - FIXED to include executables without extensions"""
        binaries = []
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                filepath = os.path.join(root, file)
                if os.access(filepath, os.X_OK):
                    # Check if it's likely an executable
                    try:
                        with open(filepath, 'rb') as f:
                            magic = f.read(4)
                            # ELF binary or script with shebang
                            if magic.startswith(b'#!') or magic.startswith(b'\x7fELF'):
                                binaries.append(filepath)
                            # Also include files without extensions that are executable
                            # (common for many Linux applications)
                            elif '.' not in file and os.path.getsize(filepath) > 100:
                                # Check if it contains non-text data (likely binary)
                                with open(filepath, 'rb') as f:
                                    sample = f.read(1024)
                                    # If mostly non-ASCII, likely a binary
                                    if any(b > 127 for b in sample):
                                        binaries.append(filepath)
                    except:
                        pass
        return binaries
    
    def find_extraction_root(self, temp_dir):
        """Find the actual root directory where tarball contents were extracted"""
        # List contents of temp_dir
        items = os.listdir(temp_dir)
        
        # If there's only one item and it's a directory, that's likely the root
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            return os.path.join(temp_dir, items[0])
        
        # Otherwise, return the temp_dir itself
        return temp_dir
    
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
        
        # Simple scoring
        scored_binaries = []
        for binary in binaries:
            score = 0
            bin_name = os.path.basename(binary)
            bin_path = binary.lower()
            
            # Prefer files in bin directories
            if 'bin' in bin_path:
                score += 10
            
            # Prefer files without extensions (most Linux executables)
            if '.' not in bin_name:
                score += 8
            elif bin_name.endswith(('.sh', '.py', '.pl')):
                score += 3
            
            # Common main executable names
            main_names = ['app', 'main', 'run', 'start', 'launch']
            for name in main_names:
                if name in bin_name.lower():
                    score += 5
                    break
            
            # Avoid clear uninstallers if we have alternatives
            if 'uninstall' in bin_name.lower() or 'remove' in bin_name.lower():
                score -= 3
            
            scored_binaries.append((binary, score, bin_name))
        
        scored_binaries.sort(key=lambda x: x[1], reverse=True)
        
        # Log scoring results for debugging
        self.log.emit("Binary scoring results:")
        for binary, score, name in scored_binaries[:3]:  # Top 3
            self.log.emit(f"  {name}: {score} points")
        
        return scored_binaries[0][0] if scored_binaries else binaries[0]
    
    def parse_desktop_file(self, desktop_path):
        try:
            with open(desktop_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Simple parsing of key=value pairs in [Desktop Entry] section
            lines = content.split('\n')
            in_desktop_entry = False
            result = {}
            
            for line in lines:
                line = line.strip()
                if line == '[Desktop Entry]':
                    in_desktop_entry = True
                elif line.startswith('[') and line.endswith(']'):
                    in_desktop_entry = False
                elif in_desktop_entry and '=' in line:
                    key, value = line.split('=', 1)
                    result[key] = value
            
            return {
                'name': result.get('Name', 'Unknown'),
                'comment': result.get('Comment', ''),
                'exec': result.get('Exec', ''),
                'icon': result.get('Icon', ''),
                'categories': result.get('Categories', '').split(';'),
                'version': result.get('Version', '1.0')
            }
        except:
            pass
        return {}    
    
    def create_marker_file(self, directory, app_info):
        marker_data = {
            'installed_by': 'Tarball Installer',
            'installer_version': __version__,
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
        
        # Get app info from existing desktop file
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
            app_info = {'name': app_name, 'version': '1.0'}
        
        # ==== FIXED PART: Install ENTIRE app to ~/Applications/ ====
        applications_dir = home / 'Applications'
        applications_dir.mkdir(parents=True, exist_ok=True)
        
        # Find where the app was actually extracted in temp_dir
        extracted_root = self.find_extraction_root(self.temp_dir)
        app_base_name = os.path.basename(extracted_root)
        permanent_install_dir = applications_dir / app_base_name
        
        # Copy ENTIRE app directory to ~/Applications/
        if permanent_install_dir.exists():
            shutil.rmtree(permanent_install_dir)
        shutil.copytree(extracted_root, permanent_install_dir)
        
        # Update install_data to track this
        install_data['app_install_dir'] = str(permanent_install_dir)
        
        # Create marker file in the app directory
        marker_path = self.create_marker_file(permanent_install_dir, app_info)
        install_data['marker_files'].append(marker_path)
        self.log.emit(f"Created marker file: {marker_path}")
        
        # ==== Create launchers in ~/.local/bin/ ====
        for binary in binaries:
            binary_name = os.path.basename(binary)
            launcher_path = local_bin / binary_name
            
            # Find binary relative to extracted_root
            binary_rel_path = os.path.relpath(binary, extracted_root)
            
            # Create launcher script that cd's to app directory
            with open(launcher_path, 'w') as f:
                f.write(f'''#!/bin/bash
cd "{permanent_install_dir}"
exec "./{binary_rel_path}" "$@"
''')
            launcher_path.chmod(0o755)
            install_data['installed_files'].append(str(launcher_path))
            self.log.emit(f"Created launcher: {launcher_path}")
        
        # ==== Install desktop files (update Exec paths) ====
        for desktop in desktop_files:
            dest = local_apps / os.path.basename(desktop)
            
            try:
                with open(desktop, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Update Exec lines to use our launchers
                for i, line in enumerate(lines):
                    if line.startswith('Exec='):
                        exec_line = line[5:].strip()
                        exec_parts = exec_line.split()
                        if exec_parts:
                            binary_name = os.path.basename(exec_parts[0])
                            # Keep arguments (%f, %u, etc.)
                            args = ' ' + ' '.join(exec_parts[1:]) if len(exec_parts) > 1 else ''
                            lines[i] = f'Exec={local_bin}/{binary_name}{args}\n'
                
                with open(dest, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                install_data['installed_files'].append(str(dest))
                self.log.emit(f"Installed desktop entry: {dest}")
                
            except Exception as e:
                self.log.emit(f"Warning: Could not update desktop file: {e}")
                shutil.copy2(desktop, dest)
                install_data['installed_files'].append(str(dest))
        
        # ==== Install icons ====
        for icon in icons:
            icon_name = os.path.basename(icon)
            icon_ext = os.path.splitext(icon_name)[1].lower()
            
            # Default to scalable
            size_dir = 'scalable'
            if icon_ext == '.png':
                # Try to detect size
                for size in ['16x16', '32x32', '48x48', '64x64', '128x128', '256x256', '512x512']:
                    if size in icon or size.replace('x', '') in icon_name:
                        size_dir = size
                        break
            
            dest_dir = local_icons / 'hicolor' / size_dir / 'apps'
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / icon_name
            shutil.copy2(icon, dest)
            install_data['installed_files'].append(str(dest))
        
        # Update desktop database
        try:
            subprocess.run(['update-desktop-database', str(local_apps)], check=True)
            self.log.emit("Updated desktop database")
        except subprocess.CalledProcessError as e:
            self.log.emit(f"Warning: Failed to update desktop database: {e}")
        
        return install_data    
    
    def install_system_wide(self, desktop_files, binaries, icons, main_binary):
        # For now, just call install_to_user since system-wide requires root
        # In a real implementation, this would install to /usr/local/bin, /usr/share/applications, etc.
        self.log.emit("System-wide installation not yet implemented. Falling back to user installation.")
        return self.install_to_user(desktop_files, binaries, icons, main_binary)               

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
                                'installed_files': [],
                                'installer_version': marker_data.get('installer_version', __version__)
                            }
                            self.installations.append(installation_data)
                    except:
                        pass
        
        if self.installations:
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
        self.setWindowTitle(f"Tarball Installer v{__version__}")
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
        
        title = QLabel(f"Tarball Installer v{__version__}")
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
        
        # Manual binary selection - ALWAYS VISIBLE NOW
        self.binary_selection_group = QGroupBox("Manual Binary Selection")
        binary_layout = QVBoxLayout()
        
        self.binary_label = QLabel("If automatic detection fails or you prefer a different executable, select it manually:")
        self.binary_label.setWordWrap(True)
        
        binary_button_layout = QHBoxLayout()
        self.select_binary_btn = QPushButton("Select Executable...")
        self.select_binary_btn.clicked.connect(self.select_binary_manually)
        self.select_binary_btn.setEnabled(False)
        self.select_binary_btn.setObjectName("secondary")
        
        self.clear_selection_btn = QPushButton("Clear")
        self.clear_selection_btn.clicked.connect(self.clear_binary_selection)
        self.clear_selection_btn.setEnabled(False)
        self.clear_selection_btn.setObjectName("secondary")
        
        binary_button_layout.addWidget(self.select_binary_btn)
        binary_button_layout.addWidget(self.clear_selection_btn)
        binary_button_layout.addStretch()
        
        self.selected_binary_label = QLabel("")
        self.selected_binary_label.setStyleSheet("padding: 4px; color: #1c71d8;")
        
        binary_layout.addWidget(self.binary_label)
        binary_layout.addLayout(binary_button_layout)
        binary_layout.addWidget(self.selected_binary_label)
        self.binary_selection_group.setLayout(binary_layout)
        self.binary_selection_group.setVisible(True)  # Always visible now
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
        
        help_text = QLabel(f"""
        <div style='line-height: 1.6;'>
        <h3>Tarball Installer v{__version__}</h3>
        
        <h4>Quick Start:</h4>
        <ol>
        <li>Go to <b>Install</b> tab and click <b>Browse for Tarball</b></li>
        <li>Select your downloaded .tar.gz, .tar.bz2, or .tar.xz file</li>
        <li>Click <b>Analyze Package</b> to see detailed contents</li>
        <li>If no .desktop file exists, you can manually select the main executable</li>
        <li>Choose installation options</li>
        <li>Click <b>Install Application</b></li>
        </ol>
        
        <h4>Key Features:</h4>
        <ul>
        <li><b>Manual Binary Selection:</b> Use file picker to select main executable when needed</li>
        <li><b>Smart Analysis:</b> Shows all executables (with or without extensions)</li>
        <li><b>System Integration:</b> Creates proper desktop entries</li>
        <li><b>Mandatory Tracking:</b> Always creates marker files for uninstallation</li>
        <li><b>Complete Uninstallation:</b> Removes all files and markers</li>
        <li><b>Auto-detection:</b> Finds existing installations on startup</li>
        </ul>
        
        <h4>Manual Binary Selection:</h4>
        <p>If a package doesn't have a .desktop file, you'll need to manually select
        the main executable. Since you've already tested the app from the extracted
        tarball, you should know which file to run.</p>
        
        <p>Click <b>Select Executable</b> and navigate to the extracted folder to
        choose the correct binary.</p>
        
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
            self.select_binary_btn.setEnabled(True)  # Enable manual selection
            self.status_bar.showMessage(f"Selected: {file_name}")
            
    def analyze_package(self):
        if not self.current_file:
            return
        
        # Clean up any previous temp directories (in case user selected a different file)
        self.cleanup_temp_dirs()
        
        try:
            self.contents_table.setRowCount(0)
            self.detected_binaries = []
            self.user_selected_binary = None
            self.selected_binary_label.setText("")
            
            # Extract to temp directory for analysis AND future installation
            self.temp_analysis_dir = tempfile.mkdtemp(prefix="tarball_install_")
            
            file_name = os.path.basename(self.current_file)
            file_size = os.path.getsize(self.current_file) / (1024 * 1024)
            
            # Show extraction progress in the UI
            self.analysis_info_label.setText(f"📦 <b>{file_name}</b><br>Size: {file_size:.2f} MB<br>Extracting for analysis...")
            self.status_bar.showMessage("Extracting package for analysis...")
            
            with tarfile.open(self.current_file, 'r:*') as tar:
                members = tar.getmembers()
                total_members = len(members)
                
                # Update the file count as we extract
                self.analysis_info_label.setText(f"📦 <b>{file_name}</b><br>Size: {file_size:.2f} MB<br>Extracting {total_members} items...")
                
                # Extract all files - this is necessary for both analysis AND installation
                for i, member in enumerate(members):
                    tar.extract(member, self.temp_analysis_dir)
                    if i % 100 == 0:  # Update progress every 100 files
                        progress = int((i / total_members) * 100)
                        self.status_bar.showMessage(f"Extracting: {progress}%")
            
            # Now analyze the extracted contents
            self.status_bar.showMessage("Analyzing extracted package...")
            
            # Find executables using the same logic as InstallerThread
            binaries = []
            for root, dirs, files in os.walk(self.temp_analysis_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    if os.access(filepath, os.X_OK):
                        try:
                            with open(filepath, 'rb') as f:
                                magic = f.read(4)
                                if magic.startswith(b'#!') or magic.startswith(b'\x7fELF'):
                                    binaries.append(filepath)
                                elif '.' not in file and os.path.getsize(filepath) > 100:
                                    with open(filepath, 'rb') as f2:
                                        sample = f2.read(1024)
                                        if any(b > 127 for b in sample):
                                            binaries.append(filepath)
                        except:
                            pass
            
            self.detected_binaries = binaries
            
            desktop_files = []
            icons = []
            for root, dirs, files in os.walk(self.temp_analysis_dir):
                for file in files:
                    if file.endswith('.desktop'):
                        desktop_files.append(os.path.join(root, file))
                    if any(file.lower().endswith(ext) for ext in ['.png', '.svg', '.xpm', '.ico']):
                        if 'icon' in file.lower() or 'icons' in root.lower():
                            icons.append(os.path.join(root, file))
            
            # ALWAYS show manual selection section, but update text based on findings
            if not desktop_files and binaries:
                self.binary_label.setText("No .desktop file found. Please select the main executable manually.")
            elif desktop_files and binaries:
                self.binary_label.setText("Auto-detection found a .desktop file, but you can override the main executable manually if needed:")
            else:
                self.binary_label.setText("Select the main executable manually:")
            
            self.stats_label.setText(f"📊 Found: {len(desktop_files)} desktop entries, {len(binaries)} executables, {len(icons)} icons")
            
            # Display first 100 items
            display_items = []
            for root, dirs, files in os.walk(self.temp_analysis_dir):
                for file in files:
                    display_items.append(os.path.join(root, file))
                if len(display_items) >= 100:
                    break
            
            self.contents_table.setRowCount(len(display_items[:100]))
            
            for row, filepath in enumerate(display_items[:100]):
                name = os.path.basename(filepath)
                
                # Check file type
                is_desktop = filepath in desktop_files
                is_binary = filepath in binaries
                is_icon = filepath in icons
                
                if is_desktop:
                    display_name = f"📄 {name}"
                elif is_binary:
                    display_name = f"⚙️ {name}"
                elif is_icon:
                    display_name = f"🎨 {name}"
                else:
                    display_name = name
                
                name_item = QTableWidgetItem(display_name)
                
                if os.path.isdir(filepath):
                    type_item = QTableWidgetItem("📁 Directory")
                elif os.path.isfile(filepath):
                    type_item = QTableWidgetItem("📄 File")
                elif os.path.islink(filepath):
                    type_item = QTableWidgetItem("🔗 Symlink")
                else:
                    type_item = QTableWidgetItem("❓ Other")
                
                if os.path.isfile(filepath):
                    size_kb = os.path.getsize(filepath) / 1024
                    size_text = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                    size_item = QTableWidgetItem(size_text)
                else:
                    size_item = QTableWidgetItem("")
                
                self.contents_table.setItem(row, 0, name_item)
                self.contents_table.setItem(row, 1, type_item)
                self.contents_table.setItem(row, 2, size_item)
            
            self.contents_table.resizeColumnsToContents()
            self.analysis_info_label.setText(f"📦 <b>{file_name}</b><br>Size: {file_size:.2f} MB<br>Total items: {len(members)}")
            self.status_bar.showMessage(f"Analyzed: {len(members)} items, {len(binaries)} executables")
            
        except Exception as e:
            # Clean up on error
            self.cleanup_temp_dirs()
            QMessageBox.warning(self, "Analysis Error", f"Could not analyze package:\n{str(e)}")    

    def select_binary_manually(self):
        """Simple file picker for manual binary selection - extracts only when needed"""
        if not self.current_file:
            QMessageBox.warning(self, "No File Selected", "Please select a tarball file first.")
            return
        
        # Ask user if they want to extract for manual selection
        file_name = os.path.basename(self.current_file)
        file_size = os.path.getsize(self.current_file) / (1024 * 1024)
        
        reply = QMessageBox.question(
            self,
            "Extract for Manual Selection",
            f"To select a binary manually, the tarball needs to be extracted.\n\n"
            f"File: {file_name}\n"
            f"Size: {file_size:.1f} MB\n\n"
            f"This will extract to a temporary location.\n"
            f"Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Clean up any previous temp dirs
        self.cleanup_temp_dirs()
        
        # Create temp directory for extraction
        self.temp_analysis_dir = tempfile.mkdtemp(prefix="tarball_select_")
        try:
            self.status_bar.showMessage(f"Extracting {file_name}...")
            
            # Extract with progress
            with tarfile.open(self.current_file, 'r:*') as tar:
                members = tar.getmembers()
                total_members = len(members)
                
                # Extract all files
                for i, member in enumerate(members):
                    tar.extract(member, self.temp_analysis_dir)
                    if i % 100 == 0:  # Update progress every 100 files
                        progress = int((i / total_members) * 100)
                        self.status_bar.showMessage(f"Extracting: {progress}%")
            
            # Use the extracted directory
            extracted_root = self.find_extraction_root(self.temp_analysis_dir)
            binary_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Main Executable",
                extracted_root,
                "Executable files (*);;All files (*.*)"
            )
            
            if binary_path and os.path.exists(binary_path):
                # Make it relative to the extraction root
                try:
                    rel_path = os.path.relpath(binary_path, extracted_root)
                    self.user_selected_binary = rel_path
                    self.selected_binary_label.setText(f"Selected: {os.path.basename(binary_path)}")
                    self.clear_selection_btn.setEnabled(True)
                    self.status_bar.showMessage(f"Selected: {os.path.basename(binary_path)}")
                except ValueError as e:
                    QMessageBox.warning(self, "Selection Error", f"Could not determine relative path: {str(e)}")
            else:
                self.status_bar.showMessage("No binary selected")
                
        except Exception as e:
            QMessageBox.warning(self, "Extraction Error", f"Could not extract package for manual selection:\n{str(e)}")
            # Clean up on error
            self.cleanup_temp_dirs()

    def find_extraction_root(self, temp_dir):
        """Find the actual root directory where tarball contents were extracted"""
        # List contents of temp_dir
        items = os.listdir(temp_dir)
        
        # If there's only one item and it's a directory, that's likely the root
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            return os.path.join(temp_dir, items[0])
        
        # Otherwise, return the temp_dir itself
        return temp_dir
    
    def cleanup_temp_dirs(self):
        """Clean up temporary directories"""
        if hasattr(self, 'temp_analysis_dir') and self.temp_analysis_dir:
            if os.path.exists(self.temp_analysis_dir):
                try:
                    shutil.rmtree(self.temp_analysis_dir)
                except:
                    pass
            self.temp_analysis_dir = None

    def clear_binary_selection(self):
        self.user_selected_binary = None
        self.selected_binary_label.setText("")
        self.clear_selection_btn.setEnabled(False)
    
    def start_installation(self):
        if not self.current_file:
            QMessageBox.warning(self, "No Package Selected", "Please select a tarball file first.")
            return
        
        # If we don't have an extracted directory yet, we need to extract first
        if not hasattr(self, 'temp_analysis_dir') or not self.temp_analysis_dir:
            QMessageBox.warning(self, "Package Not Analyzed", "Please analyze the package first before installing.")
            return
        
        selected_binary_for_installer = None
        if self.user_selected_binary:
            # Convert relative path to absolute path in the extracted directory
            extracted_root = self.find_extraction_root(self.temp_analysis_dir)
            selected_binary_for_installer = os.path.join(extracted_root, self.user_selected_binary)
        
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
            selected_binary_for_installer,
            self.temp_analysis_dir  # Pass the already-extracted directory
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
        
        # Clean up temp directory after installation (success or failure)
        self.cleanup_temp_dirs()
        
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
        about_text = f"""
        <h3>Tarball Installer v{__version__}</h3>
        <p>A graphical tool for installing software from tarball archives.</p>
        
        <p><b>Key Features:</b></p>
        <ul>
        <li>Manual binary selection via system file picker</li>
        <li>Smart package analysis showing all executables</li>
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

    def closeEvent(self, event):
        """Clean up when window closes"""
        self.cleanup_temp_dirs()
        event.accept()        
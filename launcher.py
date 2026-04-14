import sys, json, os, subprocess, threading, webbrowser, shutil
import urllib.request, urllib.parse
import minecraft_launcher_lib
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QPushButton, QFrame, QLineEdit,
    QInputDialog, QMessageBox, QGridLayout, QToolBar, QSizePolicy,
    QSpacerItem, QDialog, QListWidget, QListWidgetItem, QSpinBox, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QIcon


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

QSS = """
QMainWindow, QDialog { background-color: #1a1a2e; }
QWidget { font-family: 'Segoe UI', Arial; color: #ffffff; }
QToolBar { background-color: #151525; border: none; padding: 5px; }

QLineEdit, QSpinBox { 
    background-color: #2d2d44; border: 1px solid #e94560; 
    border-radius: 4px; padding: 5px; color: white; 
}

QSpinBox::up-button, QSpinBox::down-button {
    background-color: #383855; border: 1px solid #e94560; width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #e94560; }

QListWidget { background-color: #151525; border: 1px solid #2d2d44; border-radius: 5px; outline: none; }
QListWidget::item { padding: 10px; border-bottom: 1px solid #2d2d44; }
QListWidget::item:selected { background-color: #383855; border-left: 3px solid #e94560; }

QProgressBar { border: 1px solid #2d2d44; border-radius: 5px; text-align: center; background-color: #151525; }
QProgressBar::chunk { background-color: #e94560; }

QFrame#InstanceCard { background-color: #2d2d44; border-radius: 8px; border: 2px solid transparent; }
QFrame#InstanceCard[selected="true"] { border: 2px solid #e94560; background-color: #383855; }

QFrame#Sidebar { background-color: #151525; border-left: 1px solid #2d2d44; min-width: 230px; }

QPushButton { background-color: #2d2d44; color: white; padding: 8px; border-radius: 4px; border: none; }
QPushButton:hover { background-color: #383855; }
QPushButton#SideMenuBtn { background-color: transparent; text-align: left; padding: 10px; font-size: 13px; }
QPushButton#SideMenuBtn:hover { background-color: #2d2d44; color: #e94560; }

QPushButton#LaunchBtn, QPushButton#ActionBtn { background-color: #e94560; font-weight: bold; font-size: 14px; padding: 12px; margin: 5px; }
QPushButton#LaunchBtn:hover, QPushButton#ActionBtn:hover { background-color: #ff5e78; }
"""

class ModrinthDialog(QDialog):
    def __init__(self, instance_data, mods_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Download Mods - {instance_data['name']}")
        self.resize(600, 500)
        self.instance_version = instance_data.get('version', '1.20.1')
        self.mods_dir = mods_dir
        layout = QVBoxLayout(self)
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Search Modrinth...")
        self.search_btn = QPushButton("Search"); self.search_btn.setObjectName("ActionBtn"); self.search_btn.clicked.connect(self.search_mods)
        search_layout.addWidget(self.search_input); search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)
        self.list_widget = QListWidget(); layout.addWidget(self.list_widget)
        self.dl_btn = QPushButton("Download Selected Mod"); self.dl_btn.setObjectName("ActionBtn"); self.dl_btn.clicked.connect(self.download_mod)
        layout.addWidget(self.dl_btn)
        self.status_lbl = QLabel("Ready"); layout.addWidget(self.status_lbl)

    def req(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': 'MudakLauncher/1.0'})
        return json.loads(urllib.request.urlopen(req).read())

    def search_mods(self):
        query = urllib.parse.quote(self.search_input.text())
        if not query: return
        self.status_lbl.setText("Searching..."); QApplication.processEvents()
        try:
            data = self.req(f"https://api.modrinth.com/v2/search?query={query}&limit=15")
            self.list_widget.clear()
            for hit in data.get('hits', []):
                item = QListWidgetItem(f"{hit['title']}\n{hit['description']}")
                item.setData(Qt.ItemDataRole.UserRole, hit['project_id']); self.list_widget.addItem(item)
            self.status_lbl.setText(f"Found {len(data.get('hits', []))} mods.")
        except Exception as e: self.status_lbl.setText(f"Search failed: {e}")

    def download_mod(self):
        selected = self.list_widget.currentItem()
        if not selected: return
        self.status_lbl.setText("Finding compatible version..."); self.dl_btn.setEnabled(False); QApplication.processEvents()
        try:
            versions = self.req(f"https://api.modrinth.com/v2/project/{selected.data(Qt.ItemDataRole.UserRole)}/version")
            valid = next((v for v in versions if self.instance_version in v['game_versions']), None)
            if not valid:
                self.status_lbl.setText(f"No compatible version found for MC {self.instance_version}")
            else:
                finfo = valid['files'][0]
                self.status_lbl.setText(f"Downloading {finfo['filename']}..."); QApplication.processEvents()
                with urllib.request.urlopen(urllib.request.Request(finfo['url'], headers={'User-Agent': 'MudakLauncher/1.0'})) as resp, open(os.path.join(self.mods_dir, finfo['filename']), 'wb') as out:
                    out.write(resp.read())
                self.status_lbl.setText(f"Downloaded {finfo['filename']}!")
        except Exception as e: self.status_lbl.setText(f"Download error: {e}")
        self.dl_btn.setEnabled(True)

class LauncherSignals(QObject):
    selected = pyqtSignal(dict)
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    max_progress = pyqtSignal(int)
    status = pyqtSignal(str)

class InstanceCard(QFrame):
    def __init__(self, data, signals):
        super().__init__()
        self.setObjectName("InstanceCard")
        self.setFixedSize(110, 130)
        self.data = data
        self.signals = signals
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", "false")
        layout = QVBoxLayout(self)
        self.icon_lbl = QLabel()


        icon_path = resource_path("box_icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_lbl.setPixmap(pixmap)
        else:
            self.icon_lbl.setText("📦")
            self.icon_lbl.setStyleSheet("font-size: 35px;")

        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_lbl)
        self.name_lbl = QLabel(data['name']); self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); self.name_lbl.setWordWrap(True)
        layout.addWidget(self.name_lbl)

    def mousePressEvent(self, event):
        for card in self.parent().findChildren(InstanceCard):
            card.setProperty("selected", "false")
            card.style().unpolish(card); card.style().polish(card)
        self.setProperty("selected", "true"); self.style().unpolish(self); self.style().polish(self)
        self.signals.selected.emit(self.data)

class MudakLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mudak Launcher")


        self.setWindowIcon(QIcon(resource_path("app_icon.ico")))

        self.resize(1100, 700)
        # Замість os.getcwd() краще використовувати шлях до виконуваного файлу
        base_exe_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
        self.mc_dir = os.path.join(base_exe_path, "MudakInstances")
 
        os.makedirs(self.mc_dir, exist_ok=True)
        self.config_file = "config.json"
        self.load_config()
        self.sig = LauncherSignals()
        self.current_instance = None
        self.init_ui()
        self.sig.selected.connect(self.update_sidebar)
        self.sig.finished.connect(self.on_fin)
        self.sig.progress.connect(self.progress_bar.setValue)
        self.sig.max_progress.connect(self.progress_bar.setMaximum)
        self.sig.status.connect(self.status_lbl.setText)

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f: self.config = json.load(f)
            except: self.config = {"profiles": [], "ram": 2}
        else:
            self.config = {"profiles": [{"name": "Vanilla", "version": "1.20.1", "loader": "vanilla"}], "ram": 2}
        if "ram" not in self.config: self.config["ram"] = 2

    def save_config(self):
        self.config["ram"] = self.ram_spin.value()
        with open(self.config_file, 'w') as f: json.dump(self.config, f, indent=4)

    def init_ui(self):
        self.setStyleSheet(QSS)
        tbar = QToolBar(); self.addToolBar(tbar)
        add_btn = QPushButton("✚ Add Instance"); add_btn.clicked.connect(self.add_profile); tbar.addWidget(add_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tbar.addWidget(spacer)

        tbar.addWidget(QLabel("Nickname: "))
        self.nick_input = QLineEdit(); self.nick_input.setText("uebok")
        tbar.addWidget(self.nick_input)

        central = QWidget(); self.setCentralWidget(central)
        main_layout = QHBoxLayout(central); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.grid_widget = QWidget(); self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_widget); main_layout.addWidget(scroll)

        self.sidebar = QFrame(); self.sidebar.setObjectName("Sidebar"); side_layout = QVBoxLayout(self.sidebar)
        self.sidebar.hide()
        self.side_name = QLabel(""); self.side_name.setStyleSheet("font-size: 18px; font-weight: bold; color: #e94560;"); self.side_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(self.side_name)
        self.side_loader = QLabel(""); self.side_loader.setStyleSheet("font-size: 12px; color: #aaaaaa;"); self.side_loader.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(self.side_loader)

        side_layout.addWidget(QLabel("RAM Allocation:"))
        self.ram_spin = QSpinBox(); self.ram_spin.setRange(1, 16); self.ram_spin.setSuffix(" GB")
        try:
            self.ram_spin.setValue(int(self.config.get("ram", 2)))
        except:
            self.ram_spin.setValue(2)
        side_layout.addWidget(self.ram_spin)

        self.btn_launch = QPushButton("▶ Launch"); self.btn_launch.setObjectName("LaunchBtn"); self.btn_launch.clicked.connect(self.launch_game)
        side_layout.addWidget(self.btn_launch)

        self.progress_bar = QProgressBar(); self.progress_bar.setFixedHeight(12); self.progress_bar.hide()
        side_layout.addWidget(self.progress_bar)

        btns = [("📁 Folder", self.open_folder), ("🧩 Download Mods", self.open_mod_downloader), ("📜 Version/Loader", self.change_version), ("🗑 Delete", self.delete_instance)]
        for text, func in btns:
            btn = QPushButton(text); btn.setObjectName("SideMenuBtn"); btn.clicked.connect(func); side_layout.addWidget(btn)


        self.artwork_lbl = QLabel()
        self.artwork_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_path = resource_path("sidebar_artwork.webp")
        if os.path.exists(art_path):
            pix = QPixmap(art_path).scaled(210, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.artwork_lbl.setPixmap(pix)
        side_layout.addWidget(self.artwork_lbl)

        side_layout.addStretch()
        self.status_lbl = QLabel("Ready"); self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); side_layout.addWidget(self.status_lbl)
        main_layout.addWidget(self.sidebar)
        self.refresh_grid()

    def update_sidebar(self, data):
        self.current_instance = data
        self.side_name.setText(f"{data['name']} ({data.get('version', '1.20.1')})")
        self.side_loader.setText(f"Loader: {data.get('loader', 'vanilla').title()}")
        self.sidebar.show()

    def change_version(self):
        if not self.current_instance: return
        current_v = self.current_instance.get('version', '1.20.1')
        loader, ok1 = QInputDialog.getItem(self, "Loader", "Select Modloader:", ["vanilla", "fabric", "forge"], 0, False)
        if ok1:
            new_v, ok2 = QInputDialog.getText(self, "Version", "Minecraft Version:", text=current_v)
            if ok2 and new_v.strip():
                self.current_instance['loader'] = loader
                self.current_instance['version'] = new_v.strip()
                self.save_config()
                self.update_sidebar(self.current_instance)

    def open_mod_downloader(self):
        if not self.current_instance: return
        mods_dir = os.path.join(self.mc_dir, self.current_instance['name'], "mods")
        os.makedirs(mods_dir, exist_ok=True)
        ModrinthDialog(self.current_instance, mods_dir, self).exec()

    def open_folder(self):
        path = os.path.join(self.mc_dir, self.current_instance['name'])
        os.makedirs(path, exist_ok=True); subprocess.Popen(f'explorer "{path}"')

    def delete_instance(self):
        if not self.current_instance: return
        reply = QMessageBox.question(self, "Delete", f"Delete {self.current_instance['name']}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            path = os.path.join(self.mc_dir, self.current_instance['name'])
            if os.path.exists(path):
                try: shutil.rmtree(path)
                except Exception as e: QMessageBox.warning(self, "Error", f"Failed to delete files: {e}")

            if self.current_instance in self.config["profiles"]:
                self.config["profiles"].remove(self.current_instance)
            self.save_config(); self.sidebar.hide(); self.refresh_grid()

    def launch_game(self):
        self.btn_launch.setEnabled(False); self.progress_bar.show()
        threading.Thread(target=self.run_mc, daemon=True).start()

    def run_mc(self):
        v = self.current_instance.get('version', '1.20.1')
        loader = self.current_instance.get('loader', 'vanilla')
        inst_dir = os.path.join(self.mc_dir, self.current_instance['name'])
        cbs = {"setStatus": lambda t: self.sig.status.emit(t), "setProgress": lambda v: self.sig.progress.emit(int(v)), "setMax": lambda v: self.sig.max_progress.emit(int(v))}

        try:
            if loader == 'fabric': minecraft_launcher_lib.fabric.install_fabric(v, inst_dir, callback=cbs)
            elif loader == 'forge': minecraft_launcher_lib.forge.install_forge_version(minecraft_launcher_lib.forge.find_forge_version(v), inst_dir, callback=cbs)
            else: minecraft_launcher_lib.install.install_minecraft_version(v, inst_dir, callback=cbs)

            launch_v = v
            if loader != 'vanilla':
                for installed in minecraft_launcher_lib.utils.get_installed_versions(inst_dir):
                    if loader in installed['id'].lower() and v in installed['id']:
                        launch_v = installed['id']; break

            options = {"username": self.nick_input.text(), "jvmArguments": [f"-Xmx{self.ram_spin.value()}G"]}
            subprocess.run(minecraft_launcher_lib.command.get_minecraft_command(launch_v, inst_dir, options))
        except Exception as e: self.sig.status.emit(f"Error: {e}")
        self.sig.finished.emit()

    def add_profile(self):
        name, ok = QInputDialog.getText(self, "New", "Instance Name:")
        if ok and name:
            self.config["profiles"].append({"name": name, "version": "1.20.1", "loader": "vanilla"})
            self.save_config(); self.refresh_grid()

    def refresh_grid(self):
        while self.grid_layout.count(): self.grid_layout.takeAt(0).widget().deleteLater()
        for idx, p in enumerate(self.config["profiles"]):
            card = InstanceCard(p, self.sig); self.grid_layout.addWidget(card, idx // 6, idx % 6)

    def on_fin(self):
        self.btn_launch.setEnabled(True); self.progress_bar.hide(); self.status_lbl.setText("Ready")

    def closeEvent(self, event):
        self.save_config(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); w = MudakLauncher(); w.show(); sys.exit(app.exec())
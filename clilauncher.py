#!/usr/bin/env python3
"""CLILauncher v1.1.0 — PySide6 GUI to list, manage and relaunch Claude Code sessions."""

import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QComboBox,
    QAbstractItemView,
)

from platform_utils import (
    get_running_sessions,
    find_and_focus_session_window,
    launch_in_terminal,
    launch_new_session_in_terminal,
    get_available_terminals,
)
from sync_manager import SyncManager

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
CONFIG_DIR = Path.home() / ".config" / "clilauncher"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Defaults — overridden by config.json if present
DEFAULT_CLAUDE_CMD = "claude"
DEFAULT_CLAUDE_FLAGS = "--dangerously-skip-permissions --chrome"
DEFAULT_TERMINAL = ""  # auto-detect

# Colors
BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
BG_TABLE = "#0f3460"
BG_ROW_ALT = "#1a1a3e"
BG_ROW = "#12122a"
ACCENT = "#e94560"
ACCENT_HOVER = "#ff6b81"
TEXT = "#eee"
TEXT_DIM = "#999"
BORDER = "#2a2a4a"
GREEN = "#2ecc71"
BLUE = "#3498db"
ORANGE = "#f39c12"
RED = "#e74c3c"


def load_config():
    defaults = {
        "hidden_sessions": [],
        "claude_cmd": DEFAULT_CLAUDE_CMD,
        "claude_flags": DEFAULT_CLAUDE_FLAGS,
        "terminal": DEFAULT_TERMINAL,
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            # Merge: config file values override defaults
            defaults.update(data)
        except (json.JSONDecodeError, IOError):
            pass
    return defaults


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def delete_session_files(session_id):
    """Delete .jsonl file and subagent directory for a session."""
    deleted = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        jsonl = proj_dir / f"{session_id}.jsonl"
        if jsonl.exists():
            jsonl.unlink()
            deleted.append(str(jsonl))
        sub_dir = proj_dir / session_id
        if sub_dir.is_dir():
            import shutil
            shutil.rmtree(sub_dir)
            deleted.append(str(sub_dir))
    return deleted


def get_rename_map():
    """Parse history.jsonl to get session names from /rename commands."""
    names = {}
    if not HISTORY_FILE.exists():
        return names
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                try:
                    d = json.loads(line.strip())
                    display = d.get("display", "")
                    sid = d.get("sessionId", "")
                    if display.startswith("/rename") and sid:
                        name = display[len("/rename"):].strip()
                        if name:
                            names[sid] = name
                except (json.JSONDecodeError, KeyError):
                    continue
    except IOError:
        pass
    return names


def get_index_data():
    """Load sessions-index.json data keyed by sessionId."""
    indexed = {}
    if not PROJECTS_DIR.exists():
        return indexed
    for idx_file in PROJECTS_DIR.glob("*/sessions-index.json"):
        try:
            with open(idx_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        for entry in data.get("entries", []):
            if entry.get("isSidechain"):
                continue
            sid = entry.get("sessionId", "")
            if sid:
                indexed[sid] = entry
    return indexed


def load_all_sessions():
    """Load sessions by scanning .jsonl files + enriching with index + rename data."""
    rename_map = get_rename_map()
    index_data = get_index_data()
    sessions = []

    if not PROJECTS_DIR.exists():
        return sessions

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue

        # Determine project path
        project_path = ""
        idx_file = proj_dir / "sessions-index.json"
        if idx_file.exists():
            try:
                with open(idx_file) as f:
                    project_path = json.load(f).get("originalPath", "")
            except (json.JSONDecodeError, IOError):
                pass
        if not project_path:
            project_path = "/" + proj_dir.name.lstrip("-").replace("-", "/")

        project_name = os.path.basename(project_path)

        for jsonl_file in proj_dir.glob("*.jsonl"):
            sid = jsonl_file.stem

            if len(sid) < 30:
                continue

            try:
                stat = jsonl_file.stat()
                size_bytes = stat.st_size
                file_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except OSError:
                size_bytes = 0
                file_mtime = ""

            idx = index_data.get(sid, {})
            summary = idx.get("summary", "")
            first_prompt = idx.get("firstPrompt", "")
            messages = idx.get("messageCount", 0)
            created = idx.get("created", "")
            modified = idx.get("modified", file_mtime)
            custom_title = idx.get("customTitle", "")

            if not summary and not first_prompt:
                try:
                    with open(jsonl_file) as f:
                        for line in f:
                            try:
                                entry = json.loads(line.strip())
                                if entry.get("type") == "human":
                                    msg = entry.get("message", {})
                                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                                    if isinstance(content, str) and len(content) > 3:
                                        first_prompt = content[:100]
                                        break
                            except json.JSONDecodeError:
                                continue
                except IOError:
                    pass

            session_name = rename_map.get(sid, "") or custom_title
            resume_name = session_name

            summary_display = summary if summary else first_prompt
            if len(summary_display) > 80:
                summary_display = summary_display[:77] + "..."

            if not created:
                created = modified

            sessions.append({
                "sessionId": sid,
                "sessionName": session_name,
                "resumeName": resume_name,
                "summary": summary_display,
                "project": project_name,
                "projectPath": project_path,
                "messages": messages,
                "created": created,
                "modified": modified,
                "size": size_bytes,
            })

    sessions.sort(key=lambda s: s.get("modified", ""), reverse=True)
    return sessions


def format_size(size_bytes):
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f}M"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}K"
    return f"{size_bytes}B"


def format_date(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m %H:%M")
    except (ValueError, AttributeError):
        return iso_str[:16]


SUMMARY_PROMPT = (
    "Analyse cette session de dev en français comme un tech lead intelligent.\n\n"
    "RÈGLES D'ANALYSE :\n"
    "- Ignore les bugs qui ont été corrigés pendant la session (ne les mentionne pas)\n"
    "- Si du code a été refait/refactoré, ne garde que la version finale\n"
    "- Ignore les tentatives échouées et les fausses pistes\n"
    "- Concentre-toi sur ce qui EXISTE à la fin de la session\n\n"
    "FORMAT DE SORTIE :\n"
    "## Titre (1 ligne descriptive)\n\n"
    "## Résultat final\n"
    "- Ce qui a été livré/implémenté (bullet points, version finale uniquement)\n\n"
    "## Fichiers clés\n"
    "- Liste des fichiers créés ou modifiés qui comptent\n\n"
    "## État\n"
    "- TERMINÉ / EN COURS / BLOQUÉ + détail si en cours ou bloqué\n\n"
    "## Recommandation\n"
    "- REPRENDRE : si du travail en cours mérite d'être continué\n"
    "- ARCHIVER : si tout est terminé, rien à reprendre\n"
    "- SUPPRIMER : si la session n'a produit rien d'utile ou tout a été refait ailleurs\n"
    "- Indique la date du dernier échange utile si tu penses que la session est obsolète\n\n"
    "Sois concis et direct, max 25 lignes."
)


class SummaryWorker(QThread):
    """Background thread to run claude -p for session summary."""
    finished = Signal(str, str)  # sessionId, result

    def __init__(self, session_id, project_path, claude_cmd=DEFAULT_CLAUDE_CMD):
        super().__init__()
        self.session_id = session_id
        self.project_path = project_path
        self.claude_cmd = claude_cmd

    def run(self):
        try:
            result = subprocess.run(
                [self.claude_cmd, "-p", SUMMARY_PROMPT, "--resume", self.session_id],
                capture_output=True, text=True, timeout=120,
                cwd=self.project_path,
            )
            output = result.stdout.strip() if result.stdout else result.stderr.strip()
            self.finished.emit(self.session_id, output or "Aucun résumé généré.")
        except subprocess.TimeoutExpired:
            self.finished.emit(self.session_id, "Timeout : la session est trop grosse pour être résumée en 2 min.")
        except OSError as e:
            self.finished.emit(self.session_id, f"Erreur : {e}")


class SummaryDialog(QDialog):
    """Dialog to display session summary with refresh option."""
    refresh_requested = Signal()

    def __init__(self, parent, title, content, summary_date=None):
        super().__init__(parent)
        self.setWindowTitle(f"Résumé — {title}")
        self.setMinimumSize(600, 400)
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        # Date label
        if summary_date:
            date_label = QLabel(f"Dernier résumé : {summary_date}")
            date_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            layout.addWidget(date_label)

        self.text = QPlainTextEdit()
        self.text.setPlainText(content)
        self.text.setReadOnly(True)
        self.text.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {BG_ROW};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 12px;
                font-family: "Noto Sans Mono", monospace;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_refresh = QPushButton("Relancer le résumé")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(btn_refresh)
        btn_close = QPushButton("Fermer")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DARK};
            }}
            QLabel {{
                color: {TEXT};
            }}
            QPushButton#secondaryBtn {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton#secondaryBtn:hover {{
                background-color: {BG_TABLE};
            }}
        """)

    def _on_refresh(self):
        self.refresh_requested.emit()
        self.close()

    def update_content(self, content, summary_date=None):
        self.text.setPlainText(content)


class SyncWorker(QThread):
    """Background thread for push/pull operations."""
    progress = Signal(int, int, str)   # current, total, filename
    finished = Signal(dict)            # result dict

    def __init__(self, sync_manager: SyncManager, operation: str):
        super().__init__()
        self.sync_manager = sync_manager
        self.operation = operation  # "push" or "pull"

    def run(self):
        try:
            if self.operation == "push":
                result = self.sync_manager.push(callback=self._on_progress)
            else:
                result = self.sync_manager.pull(callback=self._on_progress)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"pushed": 0, "pulled": 0, "skipped": 0, "errors": [str(e)]})

    def _on_progress(self, current, total, filename):
        self.progress.emit(current, total, filename)


class DiffWorker(QThread):
    """Background thread to compute push/pull diff."""
    finished = Signal(dict)  # diff_summary dict

    def __init__(self, sync_manager: SyncManager):
        super().__init__()
        self.sync_manager = sync_manager

    def run(self):
        try:
            result = self.sync_manager.diff_summary()
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({
                "push_count": 0, "pull_count": 0, "up_to_date": 0,
                "details": f"Erreur : {e}",
            })


class SetupDialog(QDialog):
    """First-launch wizard / settings dialog for server config."""

    def __init__(self, parent, config: dict, first_launch: bool = False):
        super().__init__(parent)
        self.config = dict(config)  # work on a copy
        self.result_config = None

        title = "Bienvenue dans CLILauncher !" if first_launch else "Configuration serveur"
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        if first_launch:
            welcome = QLabel(
                "Configure cette machine pour pouvoir sauvegarder\n"
                "et restaurer tes sessions Claude sur un serveur central."
            )
            welcome.setStyleSheet(f"color: {TEXT}; font-size: 14px;")
            layout.addWidget(welcome)

        # Machine name
        layout.addWidget(QLabel("Nom de cette machine :"))
        self.machine_input = QLineEdit()
        self.machine_input.setPlaceholderText("ex: libria1, portable-win")
        self.machine_input.setText(config.get("machine_id", ""))
        layout.addWidget(self.machine_input)

        # Separator
        sep = QLabel("Serveur central (optionnel) :")
        sep.setStyleSheet(f"color: {ACCENT}; font-size: 14px; font-weight: bold; margin-top: 8px;")
        layout.addWidget(sep)

        # SSH Host
        layout.addWidget(QLabel("Host SSH :"))
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("user@host")
        self.host_input.setText(config.get("central_host", "claudedeployer@37.187.156.119"))
        layout.addWidget(self.host_input)

        # Remote path
        layout.addWidget(QLabel("Chemin distant :"))
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("/srv/shared/clilauncher")
        self.path_input.setText(config.get("central_path", "/srv/shared/clilauncher"))
        layout.addWidget(self.path_input)

        # SSH key
        layout.addWidget(QLabel("Cle SSH :"))
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("~/.ssh/id_ed25519")
        self.key_input.setText(config.get("ssh_key", "~/.ssh/id_ed25519"))
        layout.addWidget(self.key_input)

        # Status label for test result
        self.test_status = QLabel("")
        self.test_status.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(self.test_status)

        # Buttons
        btn_row = QHBoxLayout()

        btn_test = QPushButton("Tester la connexion")
        btn_test.setObjectName("secondaryBtn")
        btn_test.clicked.connect(self._test_connection)
        btn_row.addWidget(btn_test)

        btn_row.addStretch()

        if first_launch:
            btn_skip = QPushButton("Passer")
            btn_skip.setObjectName("secondaryBtn")
            btn_skip.clicked.connect(self._on_skip)
            btn_row.addWidget(btn_skip)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Enregistrer")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DARK};
            }}
            QLabel {{
                color: {TEXT};
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT};
            }}
            QPushButton#primaryBtn {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton#primaryBtn:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton#secondaryBtn {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton#secondaryBtn:hover {{
                background-color: {BG_TABLE};
            }}
        """)

    def _test_connection(self):
        """Test SSH connection to the configured server."""
        self.test_status.setText("Test en cours...")
        self.test_status.setStyleSheet(f"color: {BLUE}; font-size: 12px;")
        QApplication.processEvents()

        profile = {
            "central_host": self.host_input.text().strip(),
            "central_path": self.path_input.text().strip(),
            "ssh_key": self.key_input.text().strip(),
        }
        sm = SyncManager(profile)
        ok, msg = sm.test_connection()
        if ok:
            self.test_status.setText(f"OK : {msg}")
            self.test_status.setStyleSheet(f"color: {GREEN}; font-size: 12px;")
        else:
            self.test_status.setText(f"Echec : {msg}")
            self.test_status.setStyleSheet(f"color: {RED}; font-size: 12px;")

    def _on_skip(self):
        """Skip server config but save machine name."""
        name = self.machine_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Donne un nom a cette machine.")
            return
        self.result_config = dict(self.config)
        self.result_config["machine_id"] = name
        # Clear server config so push/pull stay hidden
        self.result_config.pop("central_host", None)
        self.result_config.pop("central_path", None)
        self.result_config.pop("ssh_key", None)
        self.accept()

    def _on_save(self):
        """Validate and save configuration."""
        name = self.machine_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Donne un nom a cette machine.")
            return

        self.result_config = dict(self.config)
        self.result_config["machine_id"] = name
        host = self.host_input.text().strip()
        if host:
            self.result_config["central_host"] = host
            self.result_config["central_path"] = self.path_input.text().strip() or "/srv/shared/clilauncher"
            self.result_config["ssh_key"] = self.key_input.text().strip() or "~/.ssh/id_ed25519"
        else:
            self.result_config.pop("central_host", None)
            self.result_config.pop("central_path", None)
            self.result_config.pop("ssh_key", None)

        self.accept()


# Columns
COL_ID = 0
COL_STATUS = 1
COL_LAUNCH = 2
COL_CHECK = 3
COL_NAME = 4
COL_SUMMARY = 5
COL_PROJECT = 6
COL_MSGS = 7
COL_CREATED = 8
COL_MODIFIED = 9
COL_SIZE = 10
COL_SUMMARIZE = 11
COL_HIDE = 12
COL_DELETE = 13
NUM_COLS = 14


class NewSessionDialog(QDialog):
    """Dialog to create a new Claude session."""
    def __init__(self, parent, projects):
        super().__init__(parent)
        self.setWindowTitle("Nouvelle session")
        self.setMinimumWidth(450)
        self.result_data = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Project
        layout.addWidget(QLabel("Répertoire projet :"))
        self.project_combo = QComboBox()
        for p in projects:
            self.project_combo.addItem(p)
        layout.addWidget(self.project_combo)

        # Session name
        layout.addWidget(QLabel("Nom de la session :"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("ex: dogfir-bgfi dev RUBA")
        layout.addWidget(self.name_input)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_launch = QPushButton("Lancer")
        btn_launch.setObjectName("primaryBtn")
        btn_launch.clicked.connect(self.on_launch)
        btn_row.addWidget(btn_launch)
        layout.addLayout(btn_row)

        # Enter key launches
        self.name_input.returnPressed.connect(self.on_launch)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DARK};
            }}
            QLabel {{
                color: {TEXT};
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT};
            }}
            QComboBox {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 8px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                selection-background-color: {ACCENT};
                color: {TEXT};
            }}
            QPushButton#primaryBtn {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton#primaryBtn:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton#secondaryBtn {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton#secondaryBtn:hover {{
                background-color: {BG_TABLE};
            }}
        """)

    def on_launch(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Donne un nom à la session.")
            return
        self.result_data = {
            "project_path": self.project_combo.currentText(),
            "name": name,
        }
        self.accept()


class SessionLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sessions = []
        self.filtered_sessions = []
        self.running_sessions = {}  # {sessionId: pid}
        self.config = load_config()
        self.show_hidden = False
        self.summary_workers = []  # keep refs to prevent GC
        self.setWindowTitle("CLILauncher")
        self.setMinimumSize(1200, 600)
        self.resize(1400, 700)
        self.sync_workers = []  # keep refs to prevent GC
        self.setup_ui()
        self.refresh_sessions()

        # First-launch wizard: if no machine_id in config
        if not self.config.get("machine_id"):
            QTimer.singleShot(200, self._show_first_launch_wizard)

        # Auto-refresh running status every 5 seconds
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_running_status)
        self.status_timer.start(5000)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("CLILauncher")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        header.addWidget(title)
        header.addStretch()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Rechercher...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(200)
        self.search_box.textChanged.connect(self.apply_filter)
        header.addWidget(self.search_box)

        # Project filter
        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(200)
        self.project_filter.addItem("Tous les projets")
        self.project_filter.currentTextChanged.connect(self.apply_filter)
        header.addWidget(QLabel("Projet :"))
        header.addWidget(self.project_filter)

        # Terminal selector
        self.terminal_selector = QComboBox()
        self.terminal_selector.setMinimumWidth(150)
        terminals = get_available_terminals()
        for name in terminals:
            self.terminal_selector.addItem(name)
        saved_terminal = self.config.get("terminal", "")
        idx = self.terminal_selector.findText(saved_terminal)
        if idx >= 0:
            self.terminal_selector.setCurrentIndex(idx)
        self.terminal_selector.currentTextChanged.connect(self._on_terminal_changed)
        header.addWidget(QLabel("Terminal :"))
        header.addWidget(self.terminal_selector)

        # Gear button (config)
        btn_gear = QPushButton("\u2699")
        btn_gear.setObjectName("gearBtn")
        btn_gear.setToolTip("Configuration serveur")
        btn_gear.setFixedSize(32, 32)
        btn_gear.clicked.connect(self.open_setup_dialog)
        header.addWidget(btn_gear)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(NUM_COLS)
        self.table.setHorizontalHeaderLabels(
            ["#", "", "", "", "Nom session", "Résumé", "Projet", "Msgs", "Créée", "Modifiée", "Taille", "", "", ""]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self.on_double_click)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_right_click)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(COL_ID, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_LAUNCH, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        h.setSectionResizeMode(COL_SUMMARY, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_PROJECT, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MSGS, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_CREATED, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MODIFIED, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_SIZE, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_SUMMARIZE, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_HIDE, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_DELETE, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_ID, 35)
        self.table.setColumnWidth(COL_STATUS, 28)
        self.table.setColumnWidth(COL_LAUNCH, 36)
        self.table.setColumnWidth(COL_CHECK, 36)
        self.table.setColumnWidth(COL_NAME, 200)
        self.table.setColumnWidth(COL_MSGS, 50)
        self.table.setColumnWidth(COL_SIZE, 70)
        self.table.setColumnWidth(COL_SUMMARIZE, 36)
        self.table.setColumnWidth(COL_HIDE, 36)
        self.table.setColumnWidth(COL_DELETE, 36)

        h.setSortIndicatorShown(True)
        self.table.setSortingEnabled(True)

        layout.addWidget(self.table)

        # Bottom bar
        bottom = QHBoxLayout()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
        bottom.addWidget(self.status_label)

        bottom.addStretch()

        btn_new = QPushButton("  + Nouvelle session  ")
        btn_new.setObjectName("primaryBtn")
        btn_new.clicked.connect(self.new_session)
        bottom.addWidget(btn_new)

        # Push/Pull buttons (visible only if central_host configured)
        self.btn_push = QPushButton("\u2191 Push")
        self.btn_push.setObjectName("secondaryBtn")
        self.btn_push.setToolTip("Envoyer les sessions sur le serveur")
        self.btn_push.clicked.connect(self.on_push)
        bottom.addWidget(self.btn_push)

        self.btn_pull = QPushButton("\u2193 Pull")
        self.btn_pull.setObjectName("secondaryBtn")
        self.btn_pull.setToolTip("Recevoir les sessions depuis le serveur")
        self.btn_pull.clicked.connect(self.on_pull)
        bottom.addWidget(self.btn_pull)

        self._update_sync_buttons_visibility()

        self.btn_toggle_hidden = QPushButton("Afficher masquées")
        self.btn_toggle_hidden.setObjectName("secondaryBtn")
        self.btn_toggle_hidden.clicked.connect(self.toggle_hidden)
        bottom.addWidget(self.btn_toggle_hidden)

        btn_select_all = QPushButton("Tout cocher")
        btn_select_all.setObjectName("secondaryBtn")
        btn_select_all.clicked.connect(self.select_all)
        bottom.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Tout décocher")
        btn_deselect_all.setObjectName("secondaryBtn")
        btn_deselect_all.clicked.connect(self.deselect_all)
        bottom.addWidget(btn_deselect_all)

        btn_refresh = QPushButton("Rafraîchir")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.clicked.connect(self.refresh_sessions)
        bottom.addWidget(btn_refresh)

        btn_launch = QPushButton("  Relancer sélection  ")
        btn_launch.setObjectName("primaryBtn")
        btn_launch.clicked.connect(self.launch_selected)
        bottom.addWidget(btn_launch)

        layout.addLayout(bottom)

        self.apply_stylesheet()

    def apply_stylesheet(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG_DARK};
            }}
            QWidget {{
                color: {TEXT};
                font-family: "Segoe UI", "Noto Sans", sans-serif;
                font-size: 13px;
            }}
            QTableWidget {{
                background-color: {BG_ROW};
                alternate-background-color: {BG_ROW_ALT};
                border: 1px solid {BORDER};
                border-radius: 8px;
                gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border: none;
            }}
            QHeaderView::section {{
                background-color: {BG_TABLE};
                color: {TEXT};
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid {ACCENT};
            }}
            QLineEdit {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT};
            }}
            QComboBox {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 180px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER};
                selection-background-color: {ACCENT};
            }}
            QPushButton#primaryBtn {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton#primaryBtn:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton#secondaryBtn {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton#secondaryBtn:hover {{
                background-color: {BG_TABLE};
            }}
            QPushButton#launchRowBtn {{
                background-color: {GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 15px;
                font-weight: bold;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#launchRowBtn:hover {{
                background-color: #27ae60;
            }}
            QPushButton#focusRowBtn {{
                background-color: {BLUE};
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#focusRowBtn:hover {{
                background-color: #2980b9;
            }}
            QPushButton#hideRowBtn {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#hideRowBtn:hover {{
                background-color: {ORANGE};
                color: white;
            }}
            QPushButton#summarizeRowBtn {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#summarizeRowBtn:hover {{
                background-color: {BLUE};
                color: white;
            }}
            QPushButton#deleteRowBtn {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                padding: 2px;
                min-width: 28px;
                max-width: 28px;
                min-height: 24px;
                max-height: 24px;
            }}
            QPushButton#deleteRowBtn:hover {{
                background-color: {RED};
                color: white;
            }}
            QPushButton#gearBtn {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 18px;
                padding: 0px;
            }}
            QPushButton#gearBtn:hover {{
                background-color: {BG_TABLE};
                color: {TEXT};
            }}
            QCheckBox {{
                spacing: 0px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QLabel {{
                background: transparent;
            }}
            QMessageBox {{
                background-color: {BG_DARK};
                color: {TEXT};
            }}
            QMessageBox QLabel {{
                color: {TEXT};
                font-size: 13px;
            }}
            QMessageBox QPushButton {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }}
            QMessageBox QPushButton:hover {{
                background-color: {BG_TABLE};
            }}
        """)

    def refresh_sessions(self):
        self.sessions = load_all_sessions()
        self.running_sessions = get_running_sessions()

        # Update project filter
        projects = sorted(set(s["project"] for s in self.sessions))
        current = self.project_filter.currentText()
        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem("Tous les projets")
        for p in projects:
            self.project_filter.addItem(p)
        idx = self.project_filter.findText(current)
        if idx >= 0:
            self.project_filter.setCurrentIndex(idx)
        self.project_filter.blockSignals(False)

        self.apply_filter()

    def refresh_running_status(self):
        """Update running status without full reload."""
        self.running_sessions = get_running_sessions()
        self.update_status_indicators()

    def apply_filter(self):
        proj = self.project_filter.currentText()
        search = self.search_box.text().strip().lower()
        hidden = set(self.config.get("hidden_sessions", []))
        filtered = []
        for s in self.sessions:
            if proj != "Tous les projets" and s["project"] != proj:
                continue
            if s["sessionId"] in hidden and not self.show_hidden:
                continue
            if search:
                haystack = " ".join([
                    s.get("sessionName", ""),
                    s.get("summary", ""),
                    s.get("project", ""),
                    s.get("sessionId", ""),
                ]).lower()
                if search not in haystack:
                    continue
            filtered.append(s)
        self.filtered_sessions = filtered
        self.populate_table()

    def populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.filtered_sessions))

        active_count = 0

        for row, session in enumerate(self.filtered_sessions):
            sid = session["sessionId"]
            is_running = sid in self.running_sessions

            if is_running:
                active_count += 1

            # Col 0: ID
            id_item = QTableWidgetItem()
            id_item.setData(Qt.DisplayRole, row + 1)
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_ID, id_item)

            # Col 1: Status indicator
            status_item = QTableWidgetItem("\u2B24")  # filled circle
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if is_running:
                status_item.setForeground(QColor(GREEN))
                status_item.setToolTip("Active")
            else:
                status_item.setForeground(QColor("#444"))
                status_item.setToolTip("Inactive")
            self.table.setItem(row, COL_STATUS, status_item)

            # Col 2: Action button (launch or focus)
            if is_running:
                btn = QPushButton("\u21AA")  # ↪ focus arrow
                btn.setObjectName("focusRowBtn")
                btn.setToolTip("Aller sur cette session")
                btn.clicked.connect(lambda checked, s=session: self.focus_session(s))
            else:
                btn = QPushButton("\u25B6")  # ▶ play
                btn.setObjectName("launchRowBtn")
                btn.setToolTip("Lancer cette session")
                btn.clicked.connect(lambda checked, s=session: self.launch_single(s))
            self.table.setCellWidget(row, COL_LAUNCH, btn)

            # Col 3: Checkbox
            cb = QCheckBox()
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, COL_CHECK, cb_widget)

            # Col 4: Session name (full UUID if no name)
            display_name = session["sessionName"] if session["sessionName"] else session["sessionId"]
            name_item = QTableWidgetItem(display_name)
            name_item.setToolTip(session["sessionId"])
            if session["sessionName"]:
                name_item.setForeground(Qt.white)
            else:
                name_item.setForeground(Qt.gray)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_NAME, name_item)

            # Col 5: Summary
            summary_item = QTableWidgetItem(session["summary"])
            summary_item.setToolTip(session["summary"])
            summary_item.setFlags(summary_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SUMMARY, summary_item)

            # Col 6: Project
            proj_item = QTableWidgetItem(session["project"])
            proj_item.setFlags(proj_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_PROJECT, proj_item)

            # Col 7: Messages
            msg_item = QTableWidgetItem()
            msg_item.setData(Qt.DisplayRole, session["messages"])
            msg_item.setTextAlignment(Qt.AlignCenter)
            msg_item.setFlags(msg_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_MSGS, msg_item)

            # Col 8: Created
            created_item = QTableWidgetItem(format_date(session["created"]))
            created_item.setFlags(created_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_CREATED, created_item)

            # Col 9: Modified
            modified_item = QTableWidgetItem(format_date(session["modified"]))
            modified_item.setFlags(modified_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_MODIFIED, modified_item)

            # Col 10: Size
            size_item = QTableWidgetItem(format_size(session["size"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SIZE, size_item)

            # Col 11: Summarize button
            sum_btn = QPushButton("\u2139")  # ℹ
            sum_btn.setObjectName("summarizeRowBtn")
            sum_btn.setToolTip("Résumer cette session (Claude headless)")
            sum_btn.clicked.connect(lambda checked, s=session: self.summarize_session(s))
            self.table.setCellWidget(row, COL_SUMMARIZE, sum_btn)

            # Col 12: Hide button
            is_hidden = sid in set(self.config.get("hidden_sessions", []))
            hide_btn = QPushButton("\u25CB" if is_hidden else "\u2299")  # ○ unhide / ⊙ hide
            hide_btn.setObjectName("hideRowBtn")
            hide_btn.setToolTip("Réafficher" if is_hidden else "Masquer")
            hide_btn.clicked.connect(lambda checked, s=session: self.toggle_hide_session(s))
            self.table.setCellWidget(row, COL_HIDE, hide_btn)

            # Col 12: Delete button
            del_btn = QPushButton("\u2715")  # ✕
            del_btn.setObjectName("deleteRowBtn")
            del_btn.setToolTip("Supprimer cette session")
            del_btn.clicked.connect(lambda checked, s=session: self.delete_session(s))
            self.table.setCellWidget(row, COL_DELETE, del_btn)

        self.table.setSortingEnabled(True)
        total = len(self.filtered_sessions)
        self.status_label.setText(f"{total} sessions \u2022 {active_count} actives")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")

    def update_status_indicators(self):
        """Update only status dots and action buttons without full table rebuild."""
        active_count = 0
        for row in range(self.table.rowCount()):
            session = self._session_for_row(row)
            if not session:
                continue

            sid = session["sessionId"]
            is_running = sid in self.running_sessions

            if is_running:
                active_count += 1

            # Update status dot
            status_item = self.table.item(row, COL_STATUS)
            if status_item:
                if is_running:
                    status_item.setForeground(QColor(GREEN))
                    status_item.setToolTip("Active")
                else:
                    status_item.setForeground(QColor("#444"))
                    status_item.setToolTip("Inactive")

            # Update action button
            old_btn = self.table.cellWidget(row, COL_LAUNCH)
            old_is_focus = old_btn and old_btn.objectName() == "focusRowBtn" if old_btn else False

            if is_running and not old_is_focus:
                btn = QPushButton("\u21AA")
                btn.setObjectName("focusRowBtn")
                btn.setToolTip("Aller sur cette session")
                btn.clicked.connect(lambda checked, s=session: self.focus_session(s))
                self.table.setCellWidget(row, COL_LAUNCH, btn)
            elif not is_running and (old_is_focus or old_btn is None):
                btn = QPushButton("\u25B6")
                btn.setObjectName("launchRowBtn")
                btn.setToolTip("Lancer cette session")
                btn.clicked.connect(lambda checked, s=session: self.launch_single(s))
                self.table.setCellWidget(row, COL_LAUNCH, btn)

        total = self.table.rowCount()
        self.status_label.setText(f"{total} sessions \u2022 {active_count} actives")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")

    def get_checkbox(self, row):
        widget = self.table.cellWidget(row, COL_CHECK)
        if widget:
            return widget.findChild(QCheckBox)
        return None

    def select_all(self):
        for row in range(self.table.rowCount()):
            cb = self.get_checkbox(row)
            if cb:
                cb.setChecked(True)

    def deselect_all(self):
        for row in range(self.table.rowCount()):
            cb = self.get_checkbox(row)
            if cb:
                cb.setChecked(False)

    def _session_for_row(self, row):
        name_item = self.table.item(row, COL_NAME)
        if name_item:
            sid = name_item.toolTip()
            for s in self.filtered_sessions:
                if s["sessionId"] == sid:
                    return s
        return None

    def get_selected_sessions(self):
        selected = []
        for row in range(self.table.rowCount()):
            cb = self.get_checkbox(row)
            if cb and cb.isChecked():
                s = self._session_for_row(row)
                if s:
                    selected.append(s)
        return selected

    def on_right_click(self, pos):
        """Right-click context menu to copy session info."""
        row = self.table.rowAt(pos.y())
        session = self._session_for_row(row)
        if not session:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_CARD};
                color: {TEXT};
                border: 1px solid {BORDER};
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: {ACCENT};
            }}
        """)

        name = session["sessionName"] or session["sessionId"]
        act_name = menu.addAction(f"Copier nom : {name}")
        act_id = menu.addAction(f"Copier ID : {session['sessionId']}")
        act_cmd = menu.addAction("Copier commande resume")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        clipboard = QApplication.clipboard()
        if action == act_name:
            clipboard.setText(name)
            self.status_label.setText("Nom copié")
        elif action == act_id:
            clipboard.setText(session["sessionId"])
            self.status_label.setText("Session ID copié")
        elif action == act_cmd:
            cmd = f'cd "{session["projectPath"]}" && claude --resume "{session["sessionId"]}"'
            clipboard.setText(cmd)
            self.status_label.setText("Commande copiée")
        else:
            return
        self.status_label.setStyleSheet(f"color: {GREEN};")
        QTimer.singleShot(2000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))

    def on_double_click(self, index):
        """Double-click: focus if active, launch if inactive."""
        row = index.row()
        session = self._session_for_row(row)
        if not session:
            return

        if session["sessionId"] in self.running_sessions:
            self.focus_session(session)
        else:
            self.launch_single(session)

    def focus_session(self, session):
        """Find and focus the terminal window of a running session."""
        sid = session["sessionId"]
        pid = self.running_sessions.get(sid)
        if not pid:
            self.status_label.setText("Session plus active")
            self.status_label.setStyleSheet(f"color: {ORANGE};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
            return

        if find_and_focus_session_window(pid):
            # Minimize CLILauncher so terminal comes to front
            self.showMinimized()
            label = session["sessionName"] or sid[:12]
            self.status_label.setText(f"Focus : {label}")
            self.status_label.setStyleSheet(f"color: {BLUE};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        else:
            self.status_label.setText("Fenêtre introuvable")
            self.status_label.setStyleSheet(f"color: {ORANGE};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))

    def _on_terminal_changed(self, terminal_name):
        """Save the selected terminal to config."""
        self.config["terminal"] = terminal_name
        save_config(self.config)

    def toggle_hidden(self):
        """Toggle showing/hiding masked sessions."""
        self.show_hidden = not self.show_hidden
        self.btn_toggle_hidden.setText("Masquer cachées" if self.show_hidden else "Afficher masquées")
        self.apply_filter()

    def toggle_hide_session(self, session):
        """Hide or unhide a session."""
        sid = session["sessionId"]
        hidden = self.config.get("hidden_sessions", [])
        if sid in hidden:
            hidden.remove(sid)
            msg = "Réaffichée"
        else:
            hidden.append(sid)
            msg = "Masquée"
        self.config["hidden_sessions"] = hidden
        save_config(self.config)
        label = session["sessionName"] or sid[:12]
        self.status_label.setText(f"{msg} : {label}")
        self.status_label.setStyleSheet(f"color: {ORANGE};")
        QTimer.singleShot(2000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        self.apply_filter()

    def summarize_session(self, session, force=False):
        """Show cached summary or launch claude headless."""
        sid = session["sessionId"]
        label = session["sessionName"] or sid[:12]

        # Check cache
        summaries = self.config.get("summaries", {})
        cached = summaries.get(sid)

        if cached and not force:
            dialog = SummaryDialog(self, label, cached["text"], cached["date"])
            dialog.refresh_requested.connect(lambda: self.summarize_session(session, force=True))
            dialog.exec()
            return

        self.status_label.setText(f"Résumé en cours : {label}...")
        self.status_label.setStyleSheet(f"color: {BLUE};")

        claude_cmd = self.config.get("claude_cmd", DEFAULT_CLAUDE_CMD)
        worker = SummaryWorker(sid, session["projectPath"], claude_cmd=claude_cmd)
        worker.finished.connect(lambda s_id, result: self._on_summary_done(s_id, result, label))
        self.summary_workers.append(worker)
        worker.start()

    def _on_summary_done(self, session_id, result, label):
        """Called when summary worker finishes."""
        # Save to cache
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        summaries = self.config.get("summaries", {})
        summaries[session_id] = {"text": result, "date": now}
        self.config["summaries"] = summaries
        save_config(self.config)

        self.status_label.setText(f"Résumé terminé : {label}")
        self.status_label.setStyleSheet(f"color: {GREEN};")
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))

        # Find session for refresh callback
        session = next((s for s in self.sessions if s["sessionId"] == session_id), None)
        dialog = SummaryDialog(self, label, result, now)
        if session:
            dialog.refresh_requested.connect(lambda: self.summarize_session(session, force=True))
        dialog.exec()

        # Cleanup worker refs
        self.summary_workers = [w for w in self.summary_workers if w.isRunning()]

    def delete_session(self, session):
        """Delete a session with confirmation."""
        sid = session["sessionId"]
        label = session["sessionName"] or sid[:12]
        size = format_size(session["size"])

        # Check if running
        if sid in self.running_sessions:
            QMessageBox.warning(
                self, "Session active",
                f"La session « {label} » est en cours d'exécution.\n"
                "Ferme-la d'abord avant de la supprimer."
            )
            return

        reply = QMessageBox.warning(
            self, "Supprimer la session",
            f"Tu es sûr ? Cela va supprimer toute la session « {label} » "
            f"et l'historique des échanges de cette session ({size}).\n\n"
            "Cette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted = delete_session_files(sid)
        if deleted:
            # Also remove from hidden list if present
            hidden = self.config.get("hidden_sessions", [])
            if sid in hidden:
                hidden.remove(sid)
                self.config["hidden_sessions"] = hidden
                save_config(self.config)

            self.status_label.setText(f"Supprimée : {label}")
            self.status_label.setStyleSheet(f"color: {RED};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
            self.refresh_sessions()
        else:
            QMessageBox.warning(self, "Erreur", "Fichier session introuvable.")

    def new_session(self):
        """Open dialog to create a new session."""
        # Collect unique project paths
        project_paths = sorted(set(s["projectPath"] for s in self.sessions if s["projectPath"]))
        if not project_paths:
            project_paths = [os.path.expanduser("~")]

        dialog = NewSessionDialog(self, project_paths)
        if dialog.exec() and dialog.result_data:
            data = dialog.result_data
            terminal = self.terminal_selector.currentText()
            claude_cmd = self.config.get("claude_cmd", DEFAULT_CLAUDE_CMD)
            claude_flags = self.config.get("claude_flags", DEFAULT_CLAUDE_FLAGS)
            ok = launch_new_session_in_terminal(
                data["project_path"], data["name"],
                claude_cmd=claude_cmd, claude_flags=claude_flags,
                terminal=terminal,
            )
            if ok:
                self.status_label.setText(f"Nouvelle session : {data['name']}")
                self.status_label.setStyleSheet(f"color: {GREEN};")
                QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
                QTimer.singleShot(3000, self.refresh_sessions)
            else:
                QMessageBox.warning(self, "Erreur", "Impossible de lancer le terminal.")

    def launch_single(self, session):
        terminal = self.terminal_selector.currentText()
        claude_cmd = self.config.get("claude_cmd", DEFAULT_CLAUDE_CMD)
        claude_flags = self.config.get("claude_flags", DEFAULT_CLAUDE_FLAGS)
        ok = launch_in_terminal(
            session["projectPath"], session["sessionId"],
            claude_cmd=claude_cmd, claude_flags=claude_flags,
            terminal=terminal,
        )
        label = session["sessionName"] or session["sessionId"][:12]
        if ok:
            self.status_label.setText(f"Lancé : {label}")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
            # Refresh running status after a delay to let the process start
            QTimer.singleShot(2000, self.refresh_running_status)
        else:
            QMessageBox.warning(self, "Erreur", "Impossible de lancer le terminal.")

    # ------------------------------------------------------------------
    # Sync: Push / Pull / Setup
    # ------------------------------------------------------------------

    def _has_sync_config(self) -> bool:
        """Check if a central server is configured."""
        return bool(self.config.get("central_host"))

    def _get_sync_manager(self) -> SyncManager:
        return SyncManager(self.config)

    def _update_sync_buttons_visibility(self):
        """Show/hide Push/Pull buttons based on config."""
        visible = self._has_sync_config()
        self.btn_push.setVisible(visible)
        self.btn_pull.setVisible(visible)

    def _show_first_launch_wizard(self):
        """Show the setup wizard on first launch."""
        dialog = SetupDialog(self, self.config, first_launch=True)
        if dialog.exec() and dialog.result_config is not None:
            self.config.update(dialog.result_config)
            save_config(self.config)
            self._update_sync_buttons_visibility()
            machine = self.config.get("machine_id", "")
            self.status_label.setText(f"Machine configuree : {machine}")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))

    def open_setup_dialog(self):
        """Open the settings dialog (gear button)."""
        dialog = SetupDialog(self, self.config, first_launch=False)
        if dialog.exec() and dialog.result_config is not None:
            self.config.update(dialog.result_config)
            save_config(self.config)
            self._update_sync_buttons_visibility()
            self.status_label.setText("Configuration enregistree")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))

    def on_push(self):
        """Push sessions to the central server."""
        if not self._has_sync_config():
            return

        self.btn_push.setEnabled(False)
        self.btn_pull.setEnabled(False)
        self.status_label.setText("Calcul des differences...")
        self.status_label.setStyleSheet(f"color: {BLUE};")

        sm = self._get_sync_manager()
        worker = DiffWorker(sm)
        worker.finished.connect(self._on_push_diff_ready)
        self.sync_workers.append(worker)
        worker.start()

    def _on_push_diff_ready(self, diff_summary):
        """Show diff dialog and ask user to confirm push."""
        self.btn_push.setEnabled(True)
        self.btn_pull.setEnabled(True)

        push_count = diff_summary.get("push_count", 0)
        up_to_date = diff_summary.get("up_to_date", 0)

        if push_count == 0:
            self.status_label.setText(f"Rien a envoyer ({up_to_date} fichiers deja a jour)")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
            return

        reply = QMessageBox.question(
            self, "Push vers le serveur",
            f"{push_count} fichier(s) a envoyer\n"
            f"{up_to_date} fichier(s) deja a jour\n\n"
            "Envoyer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            self.status_label.setText("Push annule")
            self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
            return

        self._run_push()

    def _run_push(self):
        """Execute the push in a background thread."""
        self.btn_push.setEnabled(False)
        self.btn_pull.setEnabled(False)
        self.status_label.setText("Push : demarrage...")
        self.status_label.setStyleSheet(f"color: {BLUE};")

        sm = self._get_sync_manager()
        worker = SyncWorker(sm, "push")
        worker.progress.connect(self._on_sync_progress)
        worker.finished.connect(self._on_push_done)
        self.sync_workers.append(worker)
        worker.start()

    def _on_sync_progress(self, current, total, filename):
        """Update status label with sync progress."""
        short = os.path.basename(filename) if filename else ""
        self.status_label.setText(f"Sync : {current}/{total} — {short}")

    def _on_push_done(self, result):
        """Handle push completion."""
        self.btn_push.setEnabled(True)
        self.btn_pull.setEnabled(True)

        pushed = result.get("pushed", 0)
        errors = result.get("errors", [])

        if errors:
            self.status_label.setText(f"Push : {pushed} envoyes, {len(errors)} erreur(s)")
            self.status_label.setStyleSheet(f"color: {ORANGE};")
            QMessageBox.warning(
                self, "Erreurs push",
                "Certains fichiers n'ont pas ete envoyes :\n\n" + "\n".join(errors[:10]),
            )
        else:
            self.status_label.setText(f"Push termine : {pushed} fichier(s) envoye(s)")
            self.status_label.setStyleSheet(f"color: {GREEN};")

        QTimer.singleShot(5000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        self.sync_workers = [w for w in self.sync_workers if w.isRunning()]

    def on_pull(self):
        """Pull sessions from the central server."""
        if not self._has_sync_config():
            return

        self.btn_push.setEnabled(False)
        self.btn_pull.setEnabled(False)
        self.status_label.setText("Calcul des differences...")
        self.status_label.setStyleSheet(f"color: {BLUE};")

        sm = self._get_sync_manager()
        worker = DiffWorker(sm)
        worker.finished.connect(self._on_pull_diff_ready)
        self.sync_workers.append(worker)
        worker.start()

    def _on_pull_diff_ready(self, diff_summary):
        """Show diff dialog and ask user to confirm pull."""
        self.btn_push.setEnabled(True)
        self.btn_pull.setEnabled(True)

        pull_count = diff_summary.get("pull_count", 0)
        up_to_date = diff_summary.get("up_to_date", 0)

        if pull_count == 0:
            self.status_label.setText(f"Rien a recevoir ({up_to_date} fichiers deja a jour)")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
            return

        reply = QMessageBox.question(
            self, "Pull depuis le serveur",
            f"{pull_count} fichier(s) a recevoir\n"
            f"{up_to_date} fichier(s) deja a jour\n\n"
            "Recevoir ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            self.status_label.setText("Pull annule")
            self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
            return

        self._run_pull()

    def _run_pull(self):
        """Execute the pull in a background thread."""
        self.btn_push.setEnabled(False)
        self.btn_pull.setEnabled(False)
        self.status_label.setText("Pull : demarrage...")
        self.status_label.setStyleSheet(f"color: {BLUE};")

        sm = self._get_sync_manager()
        worker = SyncWorker(sm, "pull")
        worker.progress.connect(self._on_sync_progress)
        worker.finished.connect(self._on_pull_done)
        self.sync_workers.append(worker)
        worker.start()

    def _on_pull_done(self, result):
        """Handle pull completion."""
        self.btn_push.setEnabled(True)
        self.btn_pull.setEnabled(True)

        pulled = result.get("pulled", 0)
        errors = result.get("errors", [])

        if errors:
            self.status_label.setText(f"Pull : {pulled} recus, {len(errors)} erreur(s)")
            self.status_label.setStyleSheet(f"color: {ORANGE};")
            QMessageBox.warning(
                self, "Erreurs pull",
                "Certains fichiers n'ont pas ete recus :\n\n" + "\n".join(errors[:10]),
            )
        else:
            self.status_label.setText(f"Pull termine : {pulled} fichier(s) recu(s)")
            self.status_label.setStyleSheet(f"color: {GREEN};")

        QTimer.singleShot(5000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        self.sync_workers = [w for w in self.sync_workers if w.isRunning()]

        # Auto-refresh sessions after pull
        if pulled > 0:
            self.refresh_sessions()

    def launch_selected(self):
        selected = self.get_selected_sessions()
        if not selected:
            QMessageBox.information(self, "Info", "Aucune session cochée.")
            return

        count = len(selected)
        if count > 5:
            reply = QMessageBox.question(
                self, "Confirmation",
                f"Lancer {count} sessions d'un coup ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        launched = 0
        terminal = self.terminal_selector.currentText()
        claude_cmd = self.config.get("claude_cmd", DEFAULT_CLAUDE_CMD)
        claude_flags = self.config.get("claude_flags", DEFAULT_CLAUDE_FLAGS)
        for session in selected:
            ok = launch_in_terminal(
                session["projectPath"], session["sessionId"],
                claude_cmd=claude_cmd, claude_flags=claude_flags,
                terminal=terminal,
            )
            if ok:
                launched += 1

        self.status_label.setText(f"{launched}/{count} sessions lancées")
        self.status_label.setStyleSheet(f"color: {GREEN};")
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        QTimer.singleShot(3000, self.refresh_running_status)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CLILauncher")
    window = SessionLauncher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

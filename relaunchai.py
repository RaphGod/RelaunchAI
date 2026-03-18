#!/usr/bin/env python3
"""RelaunchAI — PySide6 GUI to list and relaunch Claude Code sessions."""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QComboBox,
    QAbstractItemView,
)

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"

CLAUDE_CMD = "claude"
CLAUDE_FLAGS = "--dangerously-skip-permissions --chrome"
TERMINAL_CMD = "tilix"

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
            # Reconstruct from dir name: -home-rapha-claudedevlocal -> /home/rapha/claudedevlocal
            project_path = "/" + proj_dir.name.lstrip("-").replace("-", "/")

        project_name = os.path.basename(project_path)

        for jsonl_file in proj_dir.glob("*.jsonl"):
            sid = jsonl_file.stem

            # Skip non-UUID filenames
            if len(sid) < 30:
                continue

            # Get file stats
            try:
                stat = jsonl_file.stat()
                size_bytes = stat.st_size
                file_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            except OSError:
                size_bytes = 0
                file_mtime = ""

            # Check index data
            idx = index_data.get(sid, {})
            summary = idx.get("summary", "")
            first_prompt = idx.get("firstPrompt", "")
            messages = idx.get("messageCount", 0)
            created = idx.get("created", "")
            modified = idx.get("modified", file_mtime)
            custom_title = idx.get("customTitle", "")

            # If no index data, read first user message from jsonl
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

            # Session name: /rename > customTitle
            session_name = rename_map.get(sid, "") or custom_title

            # Resume arg for --resume
            resume_name = session_name

            # Summary display
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

    # Sort by modified date descending
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


def launch_session(project_path, resume_name, session_id):
    """Launch a Claude session in a new Tilix terminal."""
    # Always use sessionId for --resume (names open the picker instead of launching directly)
    cmd = f'cd "{project_path}" && {CLAUDE_CMD} {CLAUDE_FLAGS} --resume "{session_id}"'
    try:
        subprocess.Popen(
            [TERMINAL_CMD, "-e", f"bash -c '{cmd}'"],
            start_new_session=True,
        )
        return True
    except FileNotFoundError:
        for term in ["konsole", "xterm", "gnome-terminal"]:
            try:
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", "bash", "-c", cmd], start_new_session=True)
                else:
                    subprocess.Popen([term, "-e", f"bash -c '{cmd}'"], start_new_session=True)
                return True
            except FileNotFoundError:
                continue
    return False


# Columns
COL_ID = 0
COL_LAUNCH = 1
COL_CHECK = 2
COL_NAME = 3
COL_SUMMARY = 4
COL_PROJECT = 5
COL_MSGS = 6
COL_CREATED = 7
COL_MODIFIED = 8
COL_SIZE = 9
NUM_COLS = 10


class SessionLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sessions = []
        self.filtered_sessions = []
        self.setWindowTitle("RelaunchAI")
        self.setMinimumSize(1200, 600)
        self.resize(1400, 700)
        self.setup_ui()
        self.refresh_sessions()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("RelaunchAI")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        header.addWidget(title)
        header.addStretch()

        # Project filter
        self.project_filter = QComboBox()
        self.project_filter.setMinimumWidth(200)
        self.project_filter.addItem("Tous les projets")
        self.project_filter.currentTextChanged.connect(self.apply_filter)
        header.addWidget(QLabel("Projet :"))
        header.addWidget(self.project_filter)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(NUM_COLS)
        self.table.setHorizontalHeaderLabels(
            ["#", "", "", "Nom session", "Résumé", "Projet", "Msgs", "Créée", "Modifiée", "Taille"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)

        h = self.table.horizontalHeader()
        h.setSectionResizeMode(COL_ID, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_LAUNCH, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        h.setSectionResizeMode(COL_SUMMARY, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_PROJECT, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MSGS, QHeaderView.Fixed)
        h.setSectionResizeMode(COL_CREATED, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_MODIFIED, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_SIZE, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_ID, 35)
        self.table.setColumnWidth(COL_LAUNCH, 36)
        self.table.setColumnWidth(COL_CHECK, 36)
        self.table.setColumnWidth(COL_NAME, 200)
        self.table.setColumnWidth(COL_MSGS, 50)
        self.table.setColumnWidth(COL_SIZE, 70)

        h.setSortIndicatorShown(True)
        self.table.setSortingEnabled(True)

        layout.addWidget(self.table)

        # Bottom bar
        bottom = QHBoxLayout()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
        bottom.addWidget(self.status_label)

        bottom.addStretch()

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
                background-color: {BLUE};
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
        """)

    def refresh_sessions(self):
        self.sessions = load_all_sessions()

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

    def apply_filter(self):
        proj = self.project_filter.currentText()
        if proj == "Tous les projets":
            self.filtered_sessions = list(self.sessions)
        else:
            self.filtered_sessions = [s for s in self.sessions if s["project"] == proj]
        self.populate_table()

    def populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.filtered_sessions))

        for row, session in enumerate(self.filtered_sessions):
            # Col 0: ID
            id_item = QTableWidgetItem()
            id_item.setData(Qt.DisplayRole, row + 1)
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_ID, id_item)

            # Col 1: Launch button
            btn = QPushButton("\u25B6")
            btn.setObjectName("launchRowBtn")
            btn.setToolTip("Lancer cette session")
            btn.clicked.connect(lambda checked, s=session: self.launch_single(s))
            self.table.setCellWidget(row, COL_LAUNCH, btn)

            # Col 2: Checkbox
            cb = QCheckBox()
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, COL_CHECK, cb_widget)

            # Col 3: Session name (from /rename or sessionId)
            display_name = session["sessionName"] if session["sessionName"] else session["sessionId"][:12] + "..."
            name_item = QTableWidgetItem(display_name)
            name_item.setToolTip(session["sessionId"])
            if session["sessionName"]:
                name_item.setForeground(Qt.white)
            else:
                name_item.setForeground(Qt.gray)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_NAME, name_item)

            # Col 4: Summary
            summary_item = QTableWidgetItem(session["summary"])
            summary_item.setToolTip(session["summary"])
            summary_item.setFlags(summary_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SUMMARY, summary_item)

            # Col 5: Project
            proj_item = QTableWidgetItem(session["project"])
            proj_item.setFlags(proj_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_PROJECT, proj_item)

            # Col 6: Messages
            msg_item = QTableWidgetItem()
            msg_item.setData(Qt.DisplayRole, session["messages"])
            msg_item.setTextAlignment(Qt.AlignCenter)
            msg_item.setFlags(msg_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_MSGS, msg_item)

            # Col 7: Created
            created_item = QTableWidgetItem(format_date(session["created"]))
            created_item.setFlags(created_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_CREATED, created_item)

            # Col 8: Modified
            modified_item = QTableWidgetItem(format_date(session["modified"]))
            modified_item.setFlags(modified_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_MODIFIED, modified_item)

            # Col 9: Size
            size_item = QTableWidgetItem(format_size(session["size"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SIZE, size_item)

        self.table.setSortingEnabled(True)
        self.status_label.setText(f"{len(self.filtered_sessions)} sessions")

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

    def launch_single(self, session):
        ok = launch_session(session["projectPath"], session["resumeName"], session["sessionId"])
        label = session["sessionName"] or session["sessionId"][:12]
        if ok:
            self.status_label.setText(f"Lancé : {label}")
            self.status_label.setStyleSheet(f"color: {GREEN};")
            QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))
        else:
            QMessageBox.warning(self, "Erreur", "Impossible de lancer le terminal.")

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
        for session in selected:
            ok = launch_session(session["projectPath"], session["resumeName"], session["sessionId"])
            if ok:
                launched += 1

        self.status_label.setText(f"{launched}/{count} sessions lancées")
        self.status_label.setStyleSheet(f"color: {GREEN};")
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet(f"color: {TEXT_DIM};"))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RelaunchAI")
    window = SessionLauncher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

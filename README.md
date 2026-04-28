# CLILauncher

<p align="center">
  <img src="clilauncher.svg" width="128" alt="CLILauncher Logo"/>
</p>

<p align="center">
  <strong>Le cockpit ultime pour tes sessions Claude Code.</strong><br>
  Lance, gère, surveille, résume et synchronise tes sessions — entre Linux et Windows.
</p>

<p align="center">
  <a href="https://github.com/RaphGod/CLILauncher/releases"><img src="https://img.shields.io/badge/version-1.1.0-e94560.svg" alt="version"/></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python"/></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey.svg" alt="platforms"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license"/></a>
</p>

---

Tu utilises Claude Code avec 10 terminaux ouverts ? Tu relances tes sessions chaque matin en copiant-collant des UUIDs ? Tu changes de PC entre Linux et Windows et tu perds le fil de tes conversations ?

**CLILauncher règle tout ça.**

Une app desktop multi-plateforme qui scanne automatiquement toutes tes sessions Claude Code, détecte celles qui tournent, te permet de les piloter en un clic, et synchronise tes conversations entre toutes tes machines via un serveur central.

## ✨ Features

### 🎯 Session Management
- **Découverte automatique** — Scanne toutes tes sessions, même celles absentes de l'index Claude
- **Lancement unitaire** — Bouton ▶ par session, ouvre un terminal dédié
- **Lancement en masse** — Coche tes sessions du matin, un clic, tout démarre
- **Nouvelle session** — Bouton "+ Nouvelle session" avec choix projet + nom
- **Filtre par projet** — Switch rapide entre tes projets
- **Recherche temps réel** — Tape pour filtrer instantanément (nom, résumé, projet, ID)

### 🟢 Live Monitoring
- **Détection des sessions actives** — Point vert en temps réel (refresh auto 5s)
- **Switch de fenêtre** — Bouton ↪ pour sauter directement sur le terminal d'une session active
- **Double-clic intelligent** — Active = focus la fenêtre, Inactive = relance
- **Compteur live** — "X sessions • Y actives" en bas

### 🤖 AI-Powered Summary
- **Résumé intelligent** — Bouton ℹ qui lance Claude en headless pour analyser la session
- **Analyse tech lead** — Ignore les bugs corrigés, ne garde que le résultat final
- **Recommandation** — REPRENDRE / ARCHIVER / SUPPRIMER avec justification
- **Cache persistant** — Les résumés sont sauvegardés, "Relancer le résumé" pour regénérer
- **Détection d'obsolescence** — Signale les sessions mortes qui encombrent

### 🌐 Multi-Machine Sync (v1.1)
- **Push/Pull SSH** — Sauvegarde et restauration de tes sessions sur un serveur central
- **Manifest intelligent** — Ne transfère que les fichiers modifiés (delta)
- **Cross-platform** — Bossse sur Linux, reprends sur Windows et inversement
- **Wizard de setup** — Configuration en 30 secondes au premier lancement
- **Profil machine** — Chaque PC a son identité (libria1, portable-win, etc.)

### 🧹 Cleanup
- **Masquer** — Cache les sessions sans les supprimer (config persistante)
- **Supprimer** — Avec confirmation explicite, supprime le fichier session + subagents
- **Protection** — Impossible de supprimer une session active

### 🖥️ Cross-Platform (v1.1)
- **Linux** — Tilix, Konsole, gnome-terminal, xterm
- **Windows** — Windows Terminal, PowerShell, CMD
- **Sélecteur de terminal** dans l'UI, sauvegardé dans la config
- **Détection process** — psutil (cross-platform), fallback ps aux sur Linux
- **Focus fenêtre** — wmctrl/xdotool (Linux), ctypes/user32 (Windows)

### 🎨 UX
- **Dark theme** — Interface sombre et moderne
- **Icône custom** — SVG distinctif, pas de tête de terminal générique
- **Tri par colonne** — Date, taille, messages, projet...
- **Noms de session** — Affiche les noms `/rename` en blanc, les UUIDs en gris
- **Clic droit** — Menu contextuel : copier nom, ID, ou commande resume
- **Zero config** — Aucun setup pour le mode local, lit directement les fichiers Claude Code
- **Autostart** — Se lance au login (Linux/KDE)

## 📸 Screenshot

*(coming soon — l'app est tellement belle que même les screenshots sont en dark mode)*

## 🚀 Installation

### Linux

```bash
# Prérequis
sudo apt install python3-pip xdotool wmctrl   # ou équivalent
pip install PySide6 psutil

# Clone et lance
git clone https://github.com/RaphGod/CLILauncher.git
cd CLILauncher
python3 clilauncher.py
```

### Windows

Voir le guide détaillé : [doc-privée/NOTICE-WINDOWS.txt](#) (à demander à l'auteur)

Résumé :
```powershell
winget install Python.Python.3.12 Git.Git OpenJS.NodeJS.LTS
npm install -g @anthropic-ai/claude-code
git clone https://github.com/RaphGod/CLILauncher.git
cd CLILauncher
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install PySide6 psutil
python clilauncher.py
```

### Raccourci desktop (Linux/KDE)

```bash
cp clilauncher.desktop ~/.local/share/applications/
cp clilauncher.desktop ~/.config/autostart/
mkdir -p ~/.local/share/icons/hicolor/256x256/apps/
cp clilauncher.png ~/.local/share/icons/hicolor/256x256/apps/
```

## 🎮 Utilisation

### Boutons par session

| Bouton | Action |
|---|---|
| ▶ (vert) | Lancer cette session dans un nouveau terminal |
| ↪ (bleu) | Focus la fenêtre du terminal (si session active) |
| ☐ | Cocher pour sélection multiple |
| ℹ | Générer un résumé AI intelligent |
| ⊙ | Masquer la session de la liste |
| ✕ | Supprimer la session (avec confirmation) |

### Boutons globaux

| Bouton | Action |
|---|---|
| **+ Nouvelle session** | Crée une nouvelle session Claude (dialogue projet + nom) |
| **↑ Push** | Envoie tes sessions sur le serveur central |
| **↓ Pull** | Récupère les sessions du serveur central |
| **⚙ (engrenage)** | Édite la config serveur |
| **Tout cocher / décocher** | Sélection en masse |
| **Rafraîchir** | Recharge depuis le disque |
| **Relancer sélection** | Lance toutes les sessions cochées |
| **Afficher masquées** | Toggle l'affichage des sessions cachées |

### Colonnes

| Colonne | Description |
|---|---|
| # | Numéro de ligne |
| ● | Statut : vert = active, gris = inactive |
| ▶/↪ | Lancer ou focus |
| ☐ | Checkbox sélection multiple |
| Nom session | Nom `/rename` ou UUID complet |
| Résumé | Summary auto-généré |
| Projet | Répertoire de travail |
| Msgs | Nombre de messages |
| Créée | Date de création |
| Modifiée | Dernière activité |
| Taille | Taille du fichier session |
| ℹ ⊙ ✕ | Actions par ligne |

## 🔄 Workflow Multi-Machine

```
┌─────────────────────┐         ┌──────────────────────┐
│  Linux (libria1)    │         │  Windows (portable)  │
│                     │         │                      │
│  Bosse toute la     │         │  Récupère le travail │
│  journée            │         │  de la veille (Pull) │
│         │           │         │         ▲            │
│         ▼           │         │         │            │
│      ↑ Push ────────┼─────────┼─────────┘            │
│                     │  SSH    │                      │
│                     │   ▼     │  Bosse en vacances   │
│         ┌───────────┴─────────┴───────┐              │
│         │                             │              │
│         │   Serveur OVH (central)     │              │
│         │   /srv/shared/clilauncher   │              │
│         │   sessions/ + manifest.json │              │
│         │                             │              │
│         └───────────┬─────────┬───────┘              │
│                     │  SSH    │                      │
│      ↓ Pull ────────┼─────────┼─────────┐            │
│         ▲           │         │         ▼            │
│         │           │         │      ↑ Push          │
│  Reprend le travail │         │   Avant de fermer    │
│  fait sur Windows   │         │                      │
└─────────────────────┘         └──────────────────────┘
```

## 🔧 Comment ça marche

### Sources de données

CLILauncher combine 4 sources :

1. **`~/.claude/projects/*/sessions-index.json`** — Métadonnées indexées (peut être incomplet)
2. **`~/.claude/history.jsonl`** — Noms de sessions via `/rename`
3. **`~/.claude/projects/*/*.jsonl`** — Fichiers session bruts (scannés en complément)
4. **`~/.config/clilauncher/config.json`** — Config locale (sessions masquées, résumés AI, profil machine)

### Architecture

```
clilauncher.py        ← UI principale (PySide6)
platform_utils.py     ← Abstraction OS (Linux/Windows)
sync_manager.py       ← Push/Pull SSH avec manifest delta
clilauncher.svg/.png  ← Icône
clilauncher.desktop   ← Raccourci Linux
```

### Sync Push/Pull

Le sync utilise un fichier `manifest.json` sur le serveur qui track `{filepath: {size, mtime}}`. À chaque opération :
- **Push** : compare local vs remote → ne transfère que les fichiers modifiés via `scp`
- **Pull** : même logique inversée
- Pas besoin de rsync (qui n'existe pas sur Windows)

Le serveur stocke :
```
/srv/shared/clilauncher/
├── profiles/<machine-id>.json   ← profil de chaque PC
├── sessions/                     ← sessions Claude
│   ├── -home-rapha-claudedevlocal/
│   │   ├── sessions-index.json
│   │   └── *.jsonl
│   └── history.jsonl
├── config.json                   ← config partagée (masquées, résumés)
└── manifest.json                 ← état des fichiers
```

## ⚙️ Configuration

Stockée dans `~/.config/clilauncher/config.json` (Linux) ou `C:\Users\<user>\.config\clilauncher\config.json` (Windows).

```json
{
  "machine_id": "libria1",
  "central_host": "user@server.com",
  "central_path": "/srv/shared/clilauncher",
  "ssh_key": "~/.ssh/id_ed25519",
  "claude_cmd": "claude",
  "claude_flags": "--dangerously-skip-permissions --chrome",
  "terminal": "tilix",
  "hidden_sessions": [],
  "summaries": {}
}
```

## 🗺️ Roadmap

### Done ✅
- [x] Liste + lancement de sessions (v1.0)
- [x] Monitoring live + focus fenêtre (v1.0)
- [x] Résumé AI intelligent + cache (v1.0)
- [x] Masquer/supprimer avec confirmation (v1.0)
- [x] Recherche temps réel + nouvelle session (v1.0)
- [x] Icône custom (v1.0)
- [x] Cross-platform Linux/Windows (v1.1)
- [x] Push/Pull SSH avec manifest delta (v1.1)
- [x] Wizard de setup multi-machine (v1.1)

### Next 🚧
- [ ] PyInstaller → `.exe` Windows + AppImage Linux
- [ ] Focus fenêtre Windows (ctypes/user32, en cours)
- [ ] Support multi-agent (Codex, Gemini CLI)
- [ ] Édition des noms de session depuis l'app
- [ ] Stats d'utilisation (tokens, durée, coût estimé)
- [ ] Archivage avec compression des grosses sessions
- [ ] Service API centralisé (auth, multi-utilisateur, billing)
- [ ] Terminal web (xterm.js) pour intervention depuis n'importe où

## 🤝 Contribution

Les PRs sont bienvenus ! Particulièrement pour :
- Support macOS
- Support Codex / Gemini CLI
- PyInstaller / packaging
- Tests automatisés

## 🧠 En collaboration avec Claude Local

Conçu et développé par [RaphGod](https://github.com/RaphGod) en collaboration avec Claude Local (Claude Code, Opus 4.6).

Né un mercredi matin entre un fix audio PipeWire et une mise à jour de Claude Desktop — parce que les meilleurs outils naissent quand on en a marre de faire les choses à la main.

## 📜 Licence

MIT

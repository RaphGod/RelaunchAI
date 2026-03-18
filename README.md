# RelaunchAI

**Ton cockpit pour relancer tes sessions Claude Code en un clic.**

RelaunchAI est une app desktop (PySide6) qui scanne automatiquement tes sessions Claude Code, les affiche dans un joli tableau, et te permet de les relancer — une par une ou en masse — dans des terminaux séparés.

Fini de chercher les UUIDs de session et de taper des commandes à rallonge. Tu ouvres RelaunchAI, tu coches, tu lances. That's it.

## Features

- **Liste complète** — Scanne toutes tes sessions Claude Code (même celles absentes de l'index)
- **Bouton ▶ par session** — Lance une session en un clic dans un nouveau terminal
- **Sélection multiple** — Coche tes sessions, clique "Relancer sélection", et tout s'ouvre
- **Filtre par projet** — Combo pour filtrer par répertoire de travail
- **Noms de session** — Affiche les noms donnés via `/rename` + le résumé auto-généré
- **Tri par colonne** — Trie par date, taille, nombre de messages, projet...
- **Dark theme** — Parce qu'on est des devs, quand même
- **Zero config** — Lit directement les fichiers Claude Code, rien à configurer

## Screenshot

*(coming soon)*

## Installation

### Prérequis

- Python 3.10+
- PySide6
- Un terminal (Tilix, Konsole, xterm, ou gnome-terminal)
- Claude Code installé

### Setup

```bash
# Clone le repo
git clone https://github.com/RaphGod/RelaunchAI.git
cd RelaunchAI

# Installe PySide6 si pas déjà fait
pip install PySide6

# Lance l'app
python3 relaunchai.py
```

### Raccourci desktop (Linux/KDE)

```bash
# Menu des applications
cp relaunchai.desktop ~/.local/share/applications/

# Autostart au login
cp relaunchai.desktop ~/.config/autostart/
```

## Utilisation

| Action | Comment |
|---|---|
| Lancer une session | Bouton vert **▶** sur la ligne |
| Lancer plusieurs sessions | Cocher les checkboxes → **Relancer sélection** |
| Tout cocher/décocher | Boutons en bas |
| Filtrer par projet | Combo "Projet" en haut à droite |
| Rafraîchir la liste | Bouton **Rafraîchir** |

### Colonnes

| Colonne | Description |
|---|---|
| # | Numéro de ligne |
| ▶ | Bouton de lancement rapide |
| ☐ | Checkbox pour sélection multiple |
| Nom session | Nom donné via `/rename` (ou UUID tronqué en gris) |
| Résumé | Résumé auto-généré par Claude |
| Projet | Répertoire de travail |
| Msgs | Nombre de messages dans la session |
| Créée | Date de création |
| Modifiée | Dernière activité |
| Taille | Taille du fichier session |

## Comment ça marche

RelaunchAI combine 3 sources de données Claude Code :

1. **`~/.claude/projects/*/sessions-index.json`** — Métadonnées indexées (summary, dates, messageCount)
2. **`~/.claude/history.jsonl`** — Noms de sessions via `/rename`
3. **`~/.claude/projects/*/*.jsonl`** — Fichiers session bruts (pour ceux absents de l'index)

La commande de lancement générée :
```bash
cd "{projectPath}" && claude --dangerously-skip-permissions --chrome --resume "{sessionId}"
```

## Configuration

Tout se configure en haut du fichier `relaunchai.py` :

```python
CLAUDE_CMD = "claude"                                    # Commande Claude
CLAUDE_FLAGS = "--dangerously-skip-permissions --chrome"  # Flags par défaut
TERMINAL_CMD = "tilix"                                   # Terminal préféré
```

## Roadmap

- [ ] Support multi-agent (Codex, etc.)
- [ ] Édition des noms de session depuis l'app
- [ ] Indicateur de session active (déjà en cours)
- [ ] Export/import de la liste de sessions
- [ ] Icône custom pour l'app

## En collaboration avec Claude Local

Conçu et développé par [RaphGod](https://github.com/RaphGod) en collaboration avec Claude Local (Claude Code, Opus 4.6) lors d'une session "Maintenance PC" un mercredi matin — entre un fix audio PipeWire et une mise à jour de Claude Desktop.

## Licence

MIT

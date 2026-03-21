# RelaunchAI

<p align="center">
  <img src="relaunchai.svg" width="128" alt="RelaunchAI Logo"/>
</p>

<p align="center">
  <strong>Le cockpit ultime pour tes sessions Claude Code.</strong><br>
  Lance, gère, surveille et résume tes sessions — en un clic.
</p>

---

Tu utilises Claude Code avec 10 terminaux ouverts ? Tu relances tes sessions chaque matin en copiant-collant des UUIDs ? Tu ne sais plus quelle session fait quoi ?

**RelaunchAI règle tout ça.**

Une app desktop qui scanne automatiquement toutes tes sessions Claude Code, détecte celles qui tournent, et te permet de tout piloter depuis une seule interface.

## Features

### Session Management
- **Découverte automatique** — Scanne toutes tes sessions, même celles absentes de l'index Claude
- **Lancement unitaire** — Bouton ▶ par session, ouvre un terminal dédié
- **Lancement en masse** — Coche tes sessions du matin, un clic, tout démarre
- **Filtre par projet** — Switch rapide entre tes projets

### Live Monitoring
- **Détection des sessions actives** — Point vert en temps réel (refresh auto 5s)
- **Switch de fenêtre** — Bouton ↪ pour sauter directement sur le terminal d'une session active
- **Double-clic intelligent** — Active = focus la fenêtre, Inactive = relance

### AI-Powered Summary
- **Résumé intelligent** — Bouton ℹ qui lance Claude en headless pour analyser la session
- **Analyse tech lead** — Ignore les bugs corrigés, ne garde que le résultat final
- **Recommandation** — REPRENDRE / ARCHIVER / SUPPRIMER avec justification
- **Détection d'obsolescence** — Signale les sessions mortes qui encombrent

### Cleanup
- **Masquer** — Cache les sessions sans les supprimer (config persistante)
- **Supprimer** — Avec confirmation explicite, supprime le fichier session + subagents
- **Protection** — Impossible de supprimer une session active

### UX
- **Dark theme** — Interface sombre et moderne
- **Tri par colonne** — Date, taille, messages, projet...
- **Noms de session** — Affiche les noms `/rename` en blanc, les UUIDs en gris
- **Zero config** — Aucun setup, lit directement les fichiers Claude Code
- **Autostart** — Se lance au login, toujours prêt

## Screenshot

*(coming soon — l'app est tellement belle que même les screenshots sont en dark mode)*

## Installation

### Prérequis

- Python 3.10+
- PySide6
- xdotool + wmctrl (pour le switch de fenêtre)
- Un terminal (Tilix, Konsole, xterm, ou gnome-terminal)
- Claude Code installé

### Setup

```bash
# Clone le repo
git clone https://github.com/RaphGod/RelaunchAI.git
cd RelaunchAI

# Installe les dépendances
pip install PySide6
sudo apt install xdotool wmctrl  # Linux

# Lance l'app
python3 relaunchai.py
```

### Raccourci desktop (Linux/KDE)

```bash
# Menu des applications
cp relaunchai.desktop ~/.local/share/applications/

# Autostart au login (optionnel)
cp relaunchai.desktop ~/.config/autostart/

# Icône
mkdir -p ~/.local/share/icons/hicolor/256x256/apps/
cp relaunchai.png ~/.local/share/icons/hicolor/256x256/apps/
```

## Utilisation

| Action | Comment |
|---|---|
| Lancer une session | Bouton vert **▶** |
| Focus une session active | Bouton bleu **↪** ou double-clic |
| Lancer plusieurs sessions | Cocher → **Relancer sélection** |
| Résumer une session | Bouton **ℹ** (lance Claude headless) |
| Masquer une session | Bouton **⊙** |
| Supprimer une session | Bouton **✕** (avec confirmation) |
| Voir les masquées | **Afficher masquées** en bas |
| Filtrer par projet | Combo en haut à droite |

### Colonnes

| Colonne | Description |
|---|---|
| # | Numéro de ligne |
| ● | Statut : vert = active, gris = inactive |
| ▶/↪ | Lancer ou focus |
| ☐ | Checkbox pour sélection multiple |
| Nom session | Nom donné via `/rename` ou UUID tronqué |
| Résumé | Summary auto-généré |
| Projet | Répertoire de travail |
| Msgs | Nombre de messages |
| Créée | Date de création |
| Modifiée | Dernière activité |
| Taille | Taille du fichier session |
| ℹ | Résumé AI |
| ⊙ | Masquer |
| ✕ | Supprimer |

## Comment ça marche

RelaunchAI combine 3 sources de données Claude Code :

1. **`~/.claude/projects/*/sessions-index.json`** — Métadonnées indexées
2. **`~/.claude/history.jsonl`** — Noms de sessions via `/rename`
3. **`~/.claude/projects/*/*.jsonl`** — Fichiers session bruts

La détection des sessions actives scanne les processus `claude --resume` et remonte l'arbre PID pour trouver la fenêtre terminal via `xdotool`.

## Configuration

En haut de `relaunchai.py` :

```python
CLAUDE_CMD = "claude"                                    # Commande Claude
CLAUDE_FLAGS = "--dangerously-skip-permissions --chrome"  # Flags par défaut
TERMINAL_CMD = "tilix"                                   # Terminal préféré
```

Sessions masquées stockées dans `~/.config/relaunchai/config.json`.

## Roadmap

- [ ] Support multi-agent (Codex, Gemini CLI, etc.)
- [ ] Édition des noms de session depuis l'app
- [ ] Export/import de configuration
- [ ] Archivage avec compression des grosses sessions
- [ ] Stats d'utilisation (tokens, durée, coût estimé)
- [x] ~~Indicateur de session active~~
- [x] ~~Icône custom~~
- [x] ~~Résumé AI intelligent~~
- [x] ~~Masquer/supprimer des sessions~~

## En collaboration avec Claude Local

Conçu et développé par [RaphGod](https://github.com/RaphGod) en collaboration avec Claude Local (Claude Code, Opus 4.6).

Né un mercredi matin entre un fix audio PipeWire et une mise à jour de Claude Desktop — parce que les meilleurs outils naissent quand on en a marre de faire les choses à la main.

## Licence

MIT

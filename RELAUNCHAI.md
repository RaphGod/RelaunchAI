# RelaunchAI — Documentation technique

**Version :** 1.0.4
**Repo :** https://github.com/RaphGod/RelaunchAI

App PySide6 pour lister, surveiller, résumer et relancer les sessions Claude Code depuis une interface graphique.

## Lancement

```bash
# Direct
/home/rapha/claudedevlocal/drivux/.venv/bin/python3 /home/rapha/outils/claude/relaunchai.py

# Ou via le menu KDE : "RelaunchAI"
# Autostart : se lance automatiquement au login
```

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `/home/rapha/outils/claude/relaunchai.py` | Code source principal (~500 LOC) |
| `/home/rapha/outils/claude/relaunchai.svg` | Icône vectorielle |
| `/home/rapha/outils/claude/relaunchai.png` | Icône PNG 256x256 |
| `/home/rapha/outils/claude/relaunchai.desktop` | Fichier .desktop distribuable |
| `/home/rapha/outils/claude/README.md` | README GitHub (promo) |
| `/home/rapha/outils/claude/RELAUNCHAI.md` | Cette doc technique (maintenance) |
| `~/.local/share/applications/claude-sessions-launcher.desktop` | Raccourci menu KDE |
| `~/.config/autostart/claude-sessions-launcher.desktop` | Autostart au login |
| `~/.local/share/icons/hicolor/256x256/apps/relaunchai.png` | Icône installée |
| `~/.config/relaunchai/config.json` | Config persistante (sessions masquées) |

## Dépendances

- **Python 3.12** via le venv Drivux : `/home/rapha/claudedevlocal/drivux/.venv/`
- **PySide6** (installé dans ce venv)
- **Tilix** comme terminal (fallback : konsole, xterm, gnome-terminal)
- **xdotool** + **wmctrl** pour le switch de fenêtre vers les sessions actives
- **Claude Code** (`claude` CLI) pour le lancement et les résumés AI

## Sources de données

L'app lit directement les fichiers Claude Code + un fichier config propre :

| Source | Contenu |
|---|---|
| `~/.claude/projects/*/sessions-index.json` | Métadonnées indexées : summary, messageCount, dates, customTitle, projectPath |
| `~/.claude/history.jsonl` | Noms des sessions via `/rename` (champ `display` commençant par `/rename`) |
| `~/.claude/projects/*/*.jsonl` | Fichiers session bruts (scannés pour trouver ceux absents de l'index) |
| `~/.config/relaunchai/config.json` | Liste des sessions masquées (`hidden_sessions: [uuid, ...]`) |

### Pourquoi trois sources ?

Le `sessions-index.json` est souvent **incomplet** (ex: 2 entrées pour 9 fichiers .jsonl). L'app scanne donc les fichiers `.jsonl` directement puis enrichit avec l'index et les `/rename` de `history.jsonl`.

### Résolution du nom de session

Priorité pour la colonne "Nom session" :
1. `/rename` depuis `history.jsonl` (le plus récent gagne)
2. `customTitle` depuis `sessions-index.json`
3. Sinon : sessionId complet (UUID affiché en gris)

## Colonnes du tableau

| # | Colonne | Source | Description |
|---|---|---|---|
| 0 | `#` | Calculé | Numéro de ligne |
| 1 | `●` | Process scan | Point vert = active, gris = inactive (refresh auto 5s) |
| 2 | `▶`/`↪` | — | Vert = lancer, Bleu = focus fenêtre (si active) |
| 3 | `☐` | — | Checkbox pour sélection multiple |
| 4 | Nom session | `/rename` ou `customTitle` | Nom ou UUID complet |
| 5 | Résumé | `summary` ou `firstPrompt` | Résumé auto-généré |
| 6 | Projet | `projectPath` | Nom du répertoire projet |
| 7 | Msgs | `messageCount` | Nombre de messages |
| 8 | Créée | `created` | Date de création |
| 9 | Modifiée | `modified` | Dernière modification |
| 10 | Taille | Fichier `.jsonl` | Taille du fichier session |
| 11 | `ℹ` | — | Résumé AI intelligent (Claude headless) |
| 12 | `⊙`/`○` | — | Masquer / Réafficher |
| 13 | `✕` | — | Supprimer (avec confirmation) |

## Interactions

### Lancement de session
```bash
cd "{projectPath}" && claude --dangerously-skip-permissions --chrome --resume "{sessionId}"
```
- Utilise toujours le **sessionId** (UUID) pour `--resume`, pas le nom
- Le nom ouvre un picker interactif au lieu de lancer directement
- Chaque session s'ouvre dans un **nouveau terminal Tilix**

### Détection des sessions actives
- Scan `ps aux` toutes les 5 secondes pour trouver les `claude --resume {uuid}`
- Point vert = process trouvé, gris = pas de process
- Le bouton change : ▶ (lancer) → ↪ (focus fenêtre)

### Focus fenêtre (switch vers terminal actif)
- Remonte l'arbre PID : `claude` → `bash` → `tilix`
- `xdotool search --pid` pour trouver le window ID
- `wmctrl -i -a` pour activer la fenêtre (plus rapide que xdotool sur KDE)
- RelaunchAI se minimise automatiquement pour ne pas rester devant

### Double-clic
- Session active → focus la fenêtre
- Session inactive → la relance

### Clic droit (menu contextuel)
- Copier nom de session
- Copier Session ID (UUID)
- Copier commande resume complète

### Résumé AI intelligent
- Lance `claude -p "{prompt}" --resume {sessionId}` en arrière-plan (QThread)
- Timeout : 2 minutes
- Le prompt analyse comme un tech lead :
  - Ignore les bugs corrigés et tentatives échouées
  - Ne garde que la version finale du code
  - Recommande : REPRENDRE / ARCHIVER / SUPPRIMER
  - Signale les sessions obsolètes
- Résultat affiché dans une popup (SummaryDialog)

### Masquer une session
- Bouton `⊙` → ajoute le sessionId dans `~/.config/relaunchai/config.json`
- La session disparaît de la liste
- Bouton "Afficher masquées" en bas pour les revoir
- Bouton `○` pour réafficher une session masquée

### Supprimer une session
- Bouton `✕` → QMessageBox de confirmation :
  > "Tu es sûr ? Cela va supprimer toute la session et l'historique des échanges (X M). Cette action est irréversible."
- Supprime le `.jsonl` + le dossier subagents
- Impossible de supprimer une session active (bloqué avec message)

## Boutons barre du bas

| Bouton | Action |
|---|---|
| Afficher/Masquer cachées | Toggle l'affichage des sessions masquées |
| Tout cocher | Coche toutes les checkboxes |
| Tout décocher | Décoche toutes les checkboxes |
| Rafraîchir | Relit toutes les sources de données |
| Relancer sélection | Lance toutes les sessions cochées (confirmation si > 5) |

## Architecture du code

```
relaunchai.py
│
├── Constants (couleurs, chemins, flags)
├── SUMMARY_PROMPT              # Prompt tech lead pour résumé AI
│
├── Fonctions utilitaires
│   ├── load_config() / save_config()     # Config JSON persistante
│   ├── delete_session_files()            # Supprime .jsonl + subagents
│   ├── get_running_sessions()            # ps aux → {sessionId: pid}
│   ├── find_terminal_window()            # PID → window ID (xdotool)
│   ├── focus_window()                    # wmctrl -i -a (fallback xdotool)
│   ├── get_rename_map()                  # history.jsonl → {sessionId: nom}
│   ├── get_index_data()                  # sessions-index.json → {sessionId: metadata}
│   ├── load_all_sessions()               # Scan .jsonl + enrichit index + rename
│   ├── format_size() / format_date()     # Formatage affichage
│   └── launch_session()                  # subprocess.Popen(tilix -e bash -c '...')
│
├── SummaryWorker(QThread)      # Thread background pour résumé AI
│   └── run()                   # claude -p "..." --resume {id}
│
├── SummaryDialog(QDialog)      # Popup affichage résumé
│
└── SessionLauncher(QMainWindow)
    ├── setup_ui()              # Layout : header, table, bottom bar
    ├── apply_stylesheet()      # Dark theme complet
    ├── refresh_sessions()      # Recharge données + filtre projets
    ├── refresh_running_status()# Update dots + boutons (timer 5s)
    ├── apply_filter()          # Filtre projet + sessions masquées
    ├── populate_table()        # Remplit le QTableWidget (14 colonnes)
    ├── update_status_indicators() # Refresh léger (dots + boutons seulement)
    ├── on_right_click()        # Menu contextuel (copier nom/id/cmd)
    ├── on_double_click()       # Focus si active, lance si inactive
    ├── focus_session()         # Trouve fenêtre + wmctrl + minimize self
    ├── summarize_session()     # Lance SummaryWorker
    ├── toggle_hidden()         # Toggle affichage sessions masquées
    ├── toggle_hide_session()   # Masquer/réafficher une session
    ├── delete_session()        # Supprime avec confirmation
    ├── launch_single()         # Lance une session (bouton ▶)
    └── launch_selected()       # Lance les sessions cochées
```

## Maintenance

### Ajouter un terminal alternatif

Dans `launch_session()`, la liste de fallback :
```python
for term in ["konsole", "xterm", "gnome-terminal"]:
```

### Changer les flags Claude

Constante en haut du fichier :
```python
CLAUDE_FLAGS = "--dangerously-skip-permissions --chrome"
```

### Modifier le thème

Couleurs en constantes en haut du fichier (`BG_DARK`, `ACCENT`, `GREEN`, `BLUE`, `RED`, etc.). Le stylesheet est dans `apply_stylesheet()`.

### Modifier le prompt de résumé AI

Constante `SUMMARY_PROMPT` en haut du fichier. Le prompt actuel demande une analyse tech lead intelligente.

### Si l'index Claude change de format

Champs lus depuis `sessions-index.json` :
- `entries[].sessionId`, `customTitle`, `summary`, `firstPrompt`
- `entries[].messageCount`, `created`, `modified`, `isSidechain`
- `entries[].fullPath`, `projectPath`
- `originalPath` (au niveau racine)

### Sessions fantômes (sans messages)

Certains `.jsonl` ne contiennent que des `file-history-snapshot` sans aucun message `human`. Ce sont des sessions crashées ou interrompues. Elles apparaissent avec un UUID gris et ne sont pas resumables. Solution : les masquer ou supprimer via l'interface.

### Versions taguées sur GitHub

| Tag | Description |
|---|---|
| v1.0.1 | Lanceur de base : liste + lancement + filtre |
| v1.0.4 | Monitoring live, résumé AI, masquer/supprimer, icône, clic droit |

# RelaunchAI

App PySide6 pour lister, filtrer et relancer les sessions Claude Code depuis une interface graphique.

## Lancement

```bash
# Direct
/home/rapha/claudedevlocal/drivux/.venv/bin/python3 /home/rapha/outils/claude/relaunchai.py

# Ou via le menu KDE : "RelaunchAI"
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `/home/rapha/outils/claude/relaunchai.py` | Code source de l'app |
| `~/.local/share/applications/claude-sessions-launcher.desktop` | Raccourci menu KDE |
| `~/.config/autostart/claude-sessions-launcher.desktop` | Autostart au login |

## Dépendances

- **Python 3.12** via le venv Drivux : `/home/rapha/claudedevlocal/drivux/.venv/`
- **PySide6** (installé dans ce venv)
- **Tilix** comme terminal (fallback : konsole, xterm, gnome-terminal)

## Sources de données

L'app ne stocke rien — elle lit directement les fichiers Claude Code :

| Source | Contenu |
|---|---|
| `~/.claude/projects/*/sessions-index.json` | Métadonnées indexées : summary, messageCount, dates, customTitle, projectPath |
| `~/.claude/history.jsonl` | Noms des sessions via `/rename` (champ `display` commençant par `/rename`) |
| `~/.claude/projects/*/*.jsonl` | Fichiers session bruts (scannés pour trouver ceux absents de l'index) |

### Pourquoi deux sources ?

Le `sessions-index.json` est souvent **incomplet** (ex: 2 entrées pour 9 fichiers .jsonl). L'app scanne donc les fichiers `.jsonl` directement puis enrichit avec l'index et les `/rename` de `history.jsonl`.

### Résolution du nom de session

Priorité pour la colonne "Nom session" :
1. `/rename` depuis `history.jsonl` (le plus récent gagne)
2. `customTitle` depuis `sessions-index.json`
3. Sinon : sessionId tronqué (affiché en gris)

## Colonnes du tableau

| # | Colonne | Source | Description |
|---|---|---|---|
| 0 | `#` | Calculé | Numéro de ligne (1, 2, 3...) |
| 1 | `▶` | — | Bouton pour lancer cette session seule |
| 2 | `☐` | — | Checkbox pour sélection multiple |
| 3 | Nom session | `/rename` ou `customTitle` | Nom donné par l'utilisateur |
| 4 | Résumé | `summary` ou `firstPrompt` | Résumé auto-généré par Claude |
| 5 | Projet | `projectPath` | Nom du répertoire projet |
| 6 | Msgs | `messageCount` | Nombre de messages |
| 7 | Créée | `created` | Date de création |
| 8 | Modifiée | `modified` | Dernière modification |
| 9 | Taille | Fichier `.jsonl` | Taille du fichier session |

## Commande de lancement d'une session

```bash
cd "{projectPath}" && claude --dangerously-skip-permissions --chrome --resume "{sessionId}"
```

- Utilise toujours le **sessionId** (UUID) pour `--resume`, pas le nom
- Le nom ouvre un picker interactif au lieu de lancer directement
- Chaque session s'ouvre dans un **nouveau terminal Tilix**

## Boutons

| Bouton | Action |
|---|---|
| `▶` (vert par ligne) | Lance cette session dans un nouveau Tilix |
| Tout cocher | Coche toutes les checkboxes |
| Tout décocher | Décoche toutes les checkboxes |
| Rafraîchir | Relit les sources de données |
| Relancer sélection | Lance toutes les sessions cochées (confirmation si > 5) |

## Filtre

Le combo "Projet" en haut à droite filtre par répertoire projet (claudedevlocal, claudedevsrv, libria, etc.).

## Architecture du code

```
relaunchai.py
├── get_rename_map()        # Parse history.jsonl → {sessionId: nom}
├── get_index_data()        # Parse sessions-index.json → {sessionId: metadata}
├── load_all_sessions()     # Scan .jsonl + enrichit avec index + rename
├── launch_session()        # subprocess.Popen(tilix -e bash -c '...')
└── SessionLauncher(QMainWindow)
    ├── setup_ui()          # Layout : header, table, bottom bar
    ├── refresh_sessions()  # Recharge données + filtre projets
    ├── populate_table()    # Remplit le QTableWidget
    ├── launch_single()     # Lance une session (bouton ▶)
    └── launch_selected()   # Lance les sessions cochées
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

Les couleurs sont des constantes en haut du fichier (`BG_DARK`, `ACCENT`, etc.). Le stylesheet est dans `apply_stylesheet()`.

### Si l'index Claude change de format

Les champs lus depuis `sessions-index.json` :
- `entries[].sessionId`, `customTitle`, `summary`, `firstPrompt`
- `entries[].messageCount`, `created`, `modified`, `isSidechain`
- `entries[].fullPath`, `projectPath`
- `originalPath` (au niveau racine)

### Si les sessions ne s'affichent pas toutes

L'app scanne les `.jsonl` directement en plus de l'index. Si un `.jsonl` n'a ni entrée dans l'index ni premier message lisible, il apparaîtra quand même avec le sessionId tronqué en gris.

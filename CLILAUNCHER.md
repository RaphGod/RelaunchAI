# CLILauncher — Documentation technique

**Version :** 1.1.0
**Repo :** https://github.com/RaphGod/CLILauncher
**Domaine :** clilauncher.com

App PySide6 cross-platform (Linux + Windows) pour gérer, surveiller, résumer et synchroniser les sessions Claude Code entre plusieurs machines via un serveur SSH central.

---

## Table des matières

1. [Lancement](#lancement)
2. [Fichiers du projet](#fichiers-du-projet)
3. [Dépendances](#dépendances)
4. [Sources de données](#sources-de-données)
5. [Colonnes du tableau](#colonnes-du-tableau)
6. [Interactions](#interactions)
7. [Architecture du code](#architecture-du-code)
8. [Sync Push/Pull SSH](#sync-pushpull-ssh)
9. [Configuration](#configuration)
10. [Maintenance](#maintenance)
11. [Versions](#versions)

---

## Lancement

### Linux
```bash
# Direct
python3 /home/rapha/claudedevlocal/clilauncher/clilauncher.py

# Via venv Drivux (où PySide6 est installé)
/home/rapha/claudedevlocal/drivux/.venv/bin/python3 clilauncher.py

# Menu KDE : "CLILauncher"
# Autostart : se lance automatiquement au login
```

### Windows
```powershell
cd CLILauncher
.\venv\Scripts\Activate.ps1
python clilauncher.py
```

---

## Fichiers du projet

### Code source
| Fichier | Lignes | Rôle |
|---|---|---|
| `clilauncher.py` | ~1900 | App principale PySide6 (UI + workers + dialogs) |
| `platform_utils.py` | ~390 | Abstraction OS Linux/Windows (process, focus, terminaux) |
| `sync_manager.py` | ~500 | Push/Pull SSH avec manifest delta |

### Assets
| Fichier | Rôle |
|---|---|
| `clilauncher.svg` | Icône vectorielle (cercle bleu/vert + flèche play rouge + dots neuronaux) |
| `clilauncher.png` | Icône PNG 256x256 |
| `clilauncher.desktop` | Fichier .desktop pour Linux/KDE |

### Documentation
| Fichier | Rôle |
|---|---|
| `README.md` | Doc publique GitHub (promo + install + usage) |
| `CLILAUNCHER.md` | Cette doc technique (maintenance) |
| `LICENSE` | MIT |
| `doc-privée/SPEC-clilauncher-crossplatform.md` | Spec refactoring cross-platform |
| `doc-privée/SPEC-clilauncher-vision-roadmap.md` | Vision & roadmap (Phases 1-5) |
| `doc-privée/PLAN-implementation.md` | Plan d'implémentation Étapes 1-3 |
| `doc-privée/NOTICE-WINDOWS.txt` | Guide installation Windows |

### Fichiers utilisateur (générés)
| Fichier | Rôle |
|---|---|
| `~/.config/clilauncher/config.json` | Config locale (machine, serveur, sessions masquées, résumés AI) |
| `~/.local/share/applications/clilauncher.desktop` | Raccourci menu KDE |
| `~/.config/autostart/clilauncher.desktop` | Autostart au login |
| `~/.local/share/icons/hicolor/256x256/apps/clilauncher.png` | Icône installée |

---

## Dépendances

### Python
- **Python 3.10+**
- **PySide6** — UI Qt
- **psutil** — détection process cross-platform

### Linux (optionnel pour focus fenêtre)
- **xdotool** — recherche fenêtre par PID
- **wmctrl** — focus de fenêtre (plus rapide que xdotool sur KDE)

### Terminaux supportés
| OS | Terminaux |
|---|---|
| Linux | tilix, konsole, gnome-terminal, xterm |
| Windows | wt (Windows Terminal), powershell, cmd |

### Externes
- **Claude Code** (`claude` CLI dans le PATH)
- **scp + ssh** — pour le sync (natifs sur Linux et Win10+)

---

## Sources de données

CLILauncher combine 4 sources :

| Source | Contenu |
|---|---|
| `~/.claude/projects/*/sessions-index.json` | Métadonnées : summary, customTitle, messageCount, dates, projectPath |
| `~/.claude/history.jsonl` | Noms de sessions via `/rename` (champ `display`) |
| `~/.claude/projects/*/*.jsonl` | Fichiers session bruts (scannés en complément) |
| `~/.config/clilauncher/config.json` | Config CLILauncher (masquées, résumés, profil machine, serveur) |

### Pourquoi 4 sources ?

Le `sessions-index.json` est souvent incomplet (ex : 2 entrées pour 9 fichiers). L'app scanne donc les `.jsonl` directement puis enrichit avec l'index et les `/rename` de `history.jsonl`.

### Résolution du nom de session

Priorité pour la colonne "Nom session" :
1. `/rename` depuis `history.jsonl` (le plus récent gagne)
2. `customTitle` depuis `sessions-index.json`
3. Sinon : sessionId complet (UUID affiché en gris)

---

## Colonnes du tableau

| # | Colonne | Source | Description |
|---|---|---|---|
| 0 | `#` | Calculé | Numéro de ligne |
| 1 | `●` | Process scan | Vert = active, gris = inactive (refresh auto 5s) |
| 2 | `▶`/`↪` | — | Vert = lancer, Bleu = focus fenêtre |
| 3 | `☐` | — | Checkbox sélection multiple |
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

---

## Interactions

### Lancement de session
```bash
# Linux (Tilix)
tilix -e bash -c 'cd "{projectPath}" && claude --dangerously-skip-permissions --chrome --resume "{sessionId}"'

# Windows (PowerShell)
powershell -NoExit -Command "cd '{projectPath}'; claude --dangerously-skip-permissions --chrome --resume `"{sessionId}`""
```

- Utilise toujours le **sessionId** (UUID) pour `--resume` (un nom ouvre un picker)
- Chaque session s'ouvre dans un nouveau terminal

### Détection des sessions actives
- **Linux** : parse `ps aux` ou utilise psutil → cherche `claude --resume <uuid>`
- **Windows** : `psutil.process_iter()` avec filtrage cmdline
- Refresh auto toutes les 5 secondes (timer Qt)
- Point vert = process trouvé, gris = absent
- Le bouton change : ▶ → ↪

### Focus fenêtre
- **Linux** : remonte arbre PID (`ps -o ppid=`), `xdotool search --pid`, `wmctrl -i -a`
- **Windows** : `psutil.Process.parent()` pour remonter, `ctypes.windll.user32.EnumWindows` + `SetForegroundWindow`
- CLILauncher se minimise automatiquement après focus

### Double-clic
- Active → focus la fenêtre
- Inactive → lance la session

### Clic droit (menu contextuel)
- Copier nom de session
- Copier sessionId (UUID)
- Copier commande resume complète

### Résumé AI
- Lance `claude -p "{prompt}" --resume {sessionId}` en background (QThread)
- Timeout : 2 minutes
- Cache dans `config.json` sous `summaries[sessionId] = {text, date}`
- Bouton "Relancer le résumé" pour regénérer
- Le prompt analyse comme un tech lead :
  - Ignore les bugs corrigés et tentatives échouées
  - Ne garde que la version finale du code
  - Recommande : REPRENDRE / ARCHIVER / SUPPRIMER

### Recherche
- Filtre temps réel sur : nom, résumé, projet, sessionId
- Combinable avec le filtre projet

### Nouvelle session
- Dialog avec dropdown projet (rempli depuis les projets existants) + champ nom
- Lance : `cd {projet} && claude {flags} -n "{nom}"`

### Masquer une session
- Bouton `⊙` → ajoute le sessionId dans `config["hidden_sessions"]`
- La session disparaît de la liste
- Bouton "Afficher masquées" pour les revoir
- Bouton `○` pour réafficher

### Supprimer une session
- Bouton `✕` → QMessageBox de confirmation explicite
- Supprime le `.jsonl` + le dossier subagents
- Impossible si la session est active

---

## Architecture du code

### `clilauncher.py`

```
Constants (couleurs, chemins, defaults)
SUMMARY_PROMPT              # Prompt tech lead pour résumé AI

Fonctions globales
├── load_config() / save_config()
├── delete_session_files()
├── get_rename_map()        # parse history.jsonl
├── get_index_data()        # parse sessions-index.json
├── load_all_sessions()     # combine sources
├── format_size() / format_date()

QThread Workers
├── SummaryWorker           # Claude headless pour résumé AI
├── SyncWorker              # push/pull en background
├── DiffWorker              # calcul diff en background

QDialogs
├── SetupDialog             # wizard premier lancement / config serveur
├── NewSessionDialog        # nouvelle session
├── SummaryDialog           # affichage résumé AI

SessionLauncher(QMainWindow)
├── setup_ui()              # header + table + bottom
├── apply_stylesheet()      # dark theme complet
├── refresh_sessions()      # reload data + filtres
├── refresh_running_status()# update dots/boutons (timer 5s)
├── apply_filter()          # projet + recherche + masquées
├── populate_table()        # remplit le QTableWidget
├── on_right_click()        # menu contextuel
├── on_double_click()       # focus si active, lance sinon
├── focus_session()         # via platform_utils
├── summarize_session()     # SummaryWorker + cache
├── new_session()           # NewSessionDialog
├── on_push() / on_pull()   # SyncWorker
├── _show_first_launch_wizard() / _show_setup_dialog()
├── toggle_hide_session() / delete_session()
├── launch_single() / launch_selected()
```

### `platform_utils.py`

```
WINDOWS = sys.platform == "win32"

# Détection process
get_running_sessions()           # psutil partout, fallback ps aux Linux

# Focus fenêtre
find_and_focus_session_window()  # xdotool/wmctrl Linux | ctypes Windows

# Lancement terminal
TERMINAL_PROFILES                # dict des profils par OS
get_available_terminals()        # shutil.which() detection
launch_in_terminal()             # cd {path} && claude --resume {id}
launch_new_session_in_terminal() # même chose avec -n {name}
```

### `sync_manager.py`

```
SyncManager(profile)
├── _ssh_cmd()               # ssh remote_cmd
├── _scp_push() / _scp_pull()# scp avec timeout adaptatif
├── test_connection()        # echo ok via ssh
├── init_remote()            # mkdir -p central_path
├── _collect_local_session_files()
├── _build_local_manifest()  # {path: {size, mtime}}
├── _get_remote_manifest()   # cat manifest.json via ssh
├── _push_remote_manifest()
├── diff()                   # to_push, to_pull, local_only, remote_only
├── diff_summary()           # for UI dialogs
├── push(callback)           # boucle scp + manifest + profile
├── pull(callback)           # idem inversé
├── _resolve_local_path()    # rel → abs sur le système local
└── push_profile()           # save machine profile
```

---

## Sync Push/Pull SSH

### Principe

Pas de rsync (n'existe pas nativement sur Windows). À la place :
1. Génération d'un `manifest.json` local : `{relative_path: {size, mtime}}`
2. Lecture du manifest distant via `ssh cat manifest.json`
3. Comparaison → liste des fichiers à transférer (delta)
4. `scp` pour chaque fichier modifié
5. Push du manifest mis à jour

### Structure serveur

```
/srv/shared/clilauncher/
├── profiles/
│   ├── libria1.json          # profil PC Linux (ssh, paths, last_push)
│   └── portable-win.json     # profil PC Windows
├── sessions/
│   ├── -home-rapha-claudedevlocal/
│   │   ├── sessions-index.json
│   │   └── *.jsonl
│   ├── -home-rapha-claudedevsrv/
│   │   └── ...
│   └── history.jsonl
├── config.json               # config partagée (masquées, résumés)
└── manifest.json             # {path: {size, mtime}}
```

### Mapping path local ↔ serveur

| Serveur | Linux | Windows |
|---|---|---|
| `sessions/-home-rapha-foo/bar.jsonl` | `~/.claude/projects/-home-rapha-foo/bar.jsonl` | `C:\Users\X\.claude\projects\-home-rapha-foo\bar.jsonl` |
| `sessions/history.jsonl` | `~/.claude/history.jsonl` | `C:\Users\X\.claude\history.jsonl` |
| `config.json` | `~/.config/clilauncher/config.json` | `C:\Users\X\.config\clilauncher\config.json` |
| `profiles/<id>.json` | (lecture seule, pas restauré) | (idem) |

### Configuration SSH

Options par défaut pour robustesse :
```
-o StrictHostKeyChecking=no
-o ConnectTimeout=10
-o BatchMode=yes
```

Timeout scp adaptatif : 60s base + 60s/50MB, capé à 600s.

### Workflow type

```
LINUX (matin) :
  ↓ Pull        # récupère ce que Windows a fait hier
  ... bosse ...
  ↑ Push        # envoie le travail du jour
  Quitte

WINDOWS (vacances) :
  ↓ Pull        # récupère depuis le serveur
  ... bosse ...
  ↑ Push        # envoie avant de fermer
  Quitte

LINUX (retour) :
  ↓ Pull        # récupère le travail Windows
  ...
```

---

## Configuration

`~/.config/clilauncher/config.json` :

```json
{
  "machine_id": "libria1",
  "central_host": "claudedeployer@37.187.156.119",
  "central_path": "/srv/shared/clilauncher",
  "ssh_key": "~/.ssh/id_claudedeployer",
  "claude_cmd": "claude",
  "claude_flags": "--dangerously-skip-permissions --chrome",
  "terminal": "tilix",
  "hidden_sessions": ["uuid1", "uuid2"],
  "summaries": {
    "uuid3": {
      "text": "...résumé AI...",
      "date": "28/04/2026 11:30"
    }
  }
}
```

### Premier lancement

Si `machine_id` n'est pas dans la config, un wizard s'ouvre automatiquement (timer 200ms après le start). Il demande :
- Nom de la machine
- Host SSH (optionnel)
- Chemin distant (optionnel)
- Clé SSH (optionnel)

Bouton "Tester la connexion" → `ssh echo ok`. Bouton "Passer" pour usage local uniquement.

### Édition ultérieure

Bouton ⚙ dans le header → ouvre `SetupDialog` en mode édition.

---

## Maintenance

### Modifier le prompt de résumé AI
Constante `SUMMARY_PROMPT` en haut de `clilauncher.py`.

### Ajouter un terminal
Modifier `TERMINAL_PROFILES` dans `platform_utils.py` :
```python
"linux": {
    "alacritty": {
        "cmd": ["alacritty", "-e", "bash", "-c", "{full_cmd}"],
    },
},
```

### Modifier les flags Claude par défaut
Constantes `DEFAULT_CLAUDE_CMD`, `DEFAULT_CLAUDE_FLAGS` en haut de `clilauncher.py`.

### Modifier le thème
Couleurs en constantes (`BG_DARK`, `ACCENT`, `GREEN`, `BLUE`, etc.). Stylesheet dans `apply_stylesheet()`.

### Ajouter une option de sync
1. Ajouter le champ dans `SetupDialog.setup_ui()`
2. Sauvegarder dans `result_config` dans `_on_save()`
3. Lire dans `SyncManager.__init__()`

### Sessions fantômes (sans messages)
Certains `.jsonl` ne contiennent que des `file-history-snapshot` sans message `human`. Ce sont des sessions crashées. Elles apparaissent avec UUID gris et ne sont pas resumables. Solution : masquer ou supprimer.

### Bug : push UI sans manifest/profile
**Symptôme** : sessions pushées mais `manifest.json` et `profiles/` vides.
**Cause** : exception dans la boucle scp interrompait l'exécution avant les calls finaux.
**Fix appliqué (commit 266e0c0)** : try/except per-file + try/except sur les calls manifest/profile + timeout adaptatif.

---

## Versions

| Tag | Date | Notes |
|---|---|---|
| **v1.0.1** | 2026-04 | Lanceur de base : liste, lancement, filtre projet |
| **v1.0.4** | 2026-04 | Live monitoring, résumé AI, masquer/supprimer, icône, recherche, nouvelle session, clic droit |
| **v1.1.0** | 2026-04-28 | Cross-platform Linux/Windows + Push/Pull SSH avec manifest delta + wizard setup |

### Roadmap (à venir)

- **v1.2** : PyInstaller (.exe Windows + AppImage Linux), focus fenêtre Windows complet, multi-agent (Codex, Gemini)
- **v2.0** : Service API centralisé (FastAPI sur OVH), auth JWT, multi-utilisateur
- **v2.5** : Terminal web (xterm.js + WebSocket)
- **v3.0** : Pont CerbAlive (mémoire de projet partagée)

Voir `doc-privée/SPEC-clilauncher-vision-roadmap.md` pour la vision complète.

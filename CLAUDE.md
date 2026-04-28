# CLILauncher — Contexte Claude Code

## Ce projet

CLILauncher est une app desktop PySide6 cross-platform pour gérer les sessions Claude Code (et bientôt d'autres CLI IA).

- **Repo** : https://github.com/RaphGod/CLILauncher
- **Domaine** : clilauncher.com
- **Version courante** : v1.1.0

## Documentation

| Doc | À lire en cas de... |
|---|---|
| [`README.md`](README.md) | Doc publique : promo, install, usage |
| [`CLILAUNCHER.md`](CLILAUNCHER.md) | **Doc technique complète** (architecture, code, sync, maintenance) |
| `doc-privée/SPEC-clilauncher-crossplatform.md` | Spec refactoring cross-platform (privé) |
| `doc-privée/SPEC-clilauncher-vision-roadmap.md` | Vision & roadmap complète Phases 1-5 (privé) |
| `doc-privée/PLAN-implementation.md` | Plan Étapes 1-3 avec réponses utilisateur (privé) |
| `doc-privée/NOTICE-WINDOWS.txt` | Guide installation Windows (privé) |

## Règle importante

**À chaque mise à jour du code (nouvelle feature, fix, refactoring), mettre à jour :**
1. **`CLILAUNCHER.md`** — la doc technique (architecture, fichiers, version, etc.)
2. **`README.md`** — si la feature est visible utilisateur
3. **Ce `CLAUDE.md`** — si la roadmap ou le contexte change

## Prochaine étape (à reprendre au retour)

**Tester Codex CLI de OpenAI** comme deuxième agent supporté.

Voir `doc-privée/SPEC-clilauncher-vision-roadmap.md` section "Agents supportés (roadmap multi-agent)" pour la structure de config `agents` à implémenter dans `global-config.json`.

## Architecture rapide

```
clilauncher.py        ← UI principale (PySide6, ~1900 lignes)
platform_utils.py     ← Abstraction OS Linux/Windows (~390 lignes)
sync_manager.py       ← Push/Pull SSH avec manifest delta (~500 lignes)
```

## Serveur central

- **Host** : `claudedeployer@37.187.156.119`
- **Path** : `/srv/shared/clilauncher`
- **Clé SSH** : `~/.ssh/id_claudedeployer`

## Machines

- **libria1** (Linux) : PC principal — configuré
- **portable-win** (Windows) : à configurer (voir NOTICE-WINDOWS.txt)

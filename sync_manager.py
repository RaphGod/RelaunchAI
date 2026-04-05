"""sync_manager.py — Push/Pull sessions to/from a central SSH server.

Uses scp for file transfer (native on Linux and Win10+) and ssh for
remote commands.  A manifest.json approach tracks {filepath: {size, mtime}}
so only changed files are transferred.

No rsync dependency — works on Windows without extra tooling.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
CONFIG_DIR = Path.home() / ".config" / "clilauncher"
CONFIG_FILE = CONFIG_DIR / "config.json"

# SSH/SCP common options for robustness
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=10",
    "-o", "BatchMode=yes",
]


class SyncManager:
    """Backup/restore Claude sessions to/from a central SSH server.

    NOT real-time sync — this is atomic push (local -> server) or
    pull (server -> local).  One workstation active at a time.
    """

    def __init__(self, profile: dict):
        self.machine_id = profile.get("machine_id", "unknown")
        self.central_host = profile.get("central_host", "")
        self.central_path = profile.get("central_path", "/srv/shared/clilauncher")
        self.ssh_key = os.path.expanduser(profile.get("ssh_key", "~/.ssh/id_ed25519"))
        self.profile = profile

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------

    def _ssh_cmd(self, remote_cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a command on the remote server via ssh."""
        cmd = [
            "ssh",
            "-i", self.ssh_key,
            *SSH_OPTS,
            self.central_host,
            remote_cmd,
        ]
        log.debug("SSH: %s", " ".join(cmd))
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )

    def _scp_push(self, local_path: str, remote_path: str) -> bool:
        """Copy a local file to the remote server via scp."""
        cmd = [
            "scp",
            "-i", self.ssh_key,
            *SSH_OPTS,
            local_path,
            f"{self.central_host}:{remote_path}",
        ]
        log.debug("SCP push: %s -> %s", local_path, remote_path)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                log.error("scp push failed: %s", r.stderr.strip())
                return False
            return True
        except subprocess.TimeoutExpired:
            log.error("scp push timeout: %s", local_path)
            return False
        except OSError as e:
            log.error("scp push error: %s", e)
            return False

    def _scp_pull(self, remote_path: str, local_path: str) -> bool:
        """Copy a remote file to local via scp."""
        cmd = [
            "scp",
            "-i", self.ssh_key,
            *SSH_OPTS,
            f"{self.central_host}:{remote_path}",
            local_path,
        ]
        log.debug("SCP pull: %s -> %s", remote_path, local_path)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                log.error("scp pull failed: %s", r.stderr.strip())
                return False
            return True
        except subprocess.TimeoutExpired:
            log.error("scp pull timeout: %s", remote_path)
            return False
        except OSError as e:
            log.error("scp pull error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Remote helpers
    # ------------------------------------------------------------------

    def test_connection(self) -> tuple[bool, str]:
        """Test SSH connectivity.  Returns (ok, message)."""
        if not self.central_host:
            return False, "Aucun serveur configuré"
        try:
            r = self._ssh_cmd("echo ok", timeout=15)
            if r.returncode == 0 and "ok" in r.stdout:
                return True, "Connexion OK"
            return False, r.stderr.strip() or "Connexion échouée"
        except subprocess.TimeoutExpired:
            return False, "Timeout (serveur injoignable)"
        except FileNotFoundError:
            return False, "Commande ssh introuvable"
        except OSError as e:
            return False, f"Erreur : {e}"

    def init_remote(self):
        """Create the remote directory structure if it doesn't exist."""
        dirs = [
            self.central_path,
            f"{self.central_path}/profiles",
            f"{self.central_path}/sessions",
        ]
        mkdir_cmd = " && ".join(f'mkdir -p "{d}"' for d in dirs)
        r = self._ssh_cmd(mkdir_cmd)
        if r.returncode != 0:
            log.error("init_remote failed: %s", r.stderr.strip())
        return r.returncode == 0

    # ------------------------------------------------------------------
    # Manifest logic
    # ------------------------------------------------------------------

    def _collect_local_session_files(self) -> dict[str, Path]:
        """Scan local Claude session files.

        Returns {relative_path: absolute_Path} for all transferable files.
        Relative paths use forward slashes (POSIX) for consistency.
        """
        files: dict[str, Path] = {}

        if not PROJECTS_DIR.exists():
            return files

        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue

            proj_name = proj_dir.name  # e.g. -home-rapha-claudedevlocal

            # sessions-index.json
            idx = proj_dir / "sessions-index.json"
            if idx.exists():
                rel = f"sessions/{proj_name}/sessions-index.json"
                files[rel] = idx

            # *.jsonl files (not in subagent subdirectories)
            for jsonl in proj_dir.glob("*.jsonl"):
                rel = f"sessions/{proj_name}/{jsonl.name}"
                files[rel] = jsonl

        # history.jsonl
        if HISTORY_FILE.exists():
            files["sessions/history.jsonl"] = HISTORY_FILE

        # CLILauncher config (hidden sessions, summaries)
        if CONFIG_FILE.exists():
            files["config.json"] = CONFIG_FILE

        return files

    def _build_local_manifest(self) -> dict:
        """Build manifest from local session files.

        Returns {relative_path: {"size": int, "mtime": float}}.
        """
        manifest = {}
        for rel_path, abs_path in self._collect_local_session_files().items():
            try:
                st = abs_path.stat()
                manifest[rel_path] = {
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            except OSError:
                continue
        return manifest

    def _get_remote_manifest(self) -> dict:
        """Read manifest.json from the server.  Returns {} if not found."""
        remote_manifest = f"{self.central_path}/manifest.json"
        r = self._ssh_cmd(f"cat '{remote_manifest}' 2>/dev/null || echo '{{}}'")
        if r.returncode != 0:
            return {}
        try:
            return json.loads(r.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            return {}

    def _push_remote_manifest(self, manifest: dict) -> bool:
        """Write manifest.json to the server."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="clilauncher_manifest_",
        )
        try:
            json.dump(manifest, tmp, indent=2)
            tmp.close()
            remote = f"{self.central_path}/manifest.json"
            return self._scp_push(tmp.name, remote)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def diff(self) -> dict:
        """Compare local vs remote manifests.

        Returns::

            {
                "to_push":     [rel_paths newer locally],
                "to_pull":     [rel_paths newer remotely],
                "local_only":  [rel_paths only on local],
                "remote_only": [rel_paths only on server],
                "up_to_date":  [rel_paths identical],
            }
        """
        local_m = self._build_local_manifest()
        remote_m = self._get_remote_manifest()

        local_keys = set(local_m.keys())
        remote_keys = set(remote_m.keys())

        result = {
            "to_push": [],
            "to_pull": [],
            "local_only": sorted(local_keys - remote_keys),
            "remote_only": sorted(remote_keys - local_keys),
            "up_to_date": [],
        }

        for key in local_keys & remote_keys:
            l = local_m[key]
            r = remote_m[key]
            if l["size"] != r["size"] or l["mtime"] > r["mtime"]:
                result["to_push"].append(key)
            elif r["mtime"] > l["mtime"]:
                result["to_pull"].append(key)
            else:
                result["up_to_date"].append(key)

        # local_only files also need pushing
        result["to_push"].extend(result["local_only"])

        return result

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def push(self, callback=None) -> dict:
        """Push changed files to the server.

        Args:
            callback: optional ``callback(current, total, filename)`` for progress.

        Returns::

            {"pushed": int, "skipped": int, "errors": [str]}
        """
        result = {"pushed": 0, "skipped": 0, "errors": []}

        # Ensure remote dirs
        self.init_remote()

        local_m = self._build_local_manifest()
        remote_m = self._get_remote_manifest()
        file_map = self._collect_local_session_files()

        # Determine what to push
        to_push = []
        for rel_path, local_info in local_m.items():
            remote_info = remote_m.get(rel_path)
            if remote_info is None:
                to_push.append(rel_path)
            elif (local_info["size"] != remote_info["size"]
                  or local_info["mtime"] > remote_info["mtime"]):
                to_push.append(rel_path)

        total = len(to_push)
        if total == 0:
            result["skipped"] = len(local_m)
            return result

        # Collect remote directories to create
        remote_dirs = set()
        for rel_path in to_push:
            parent = os.path.dirname(rel_path)
            if parent:
                remote_dirs.add(f"{self.central_path}/{parent}")

        # Create all needed remote dirs in one ssh call
        if remote_dirs:
            mkdir_cmd = " && ".join(f'mkdir -p "{d}"' for d in sorted(remote_dirs))
            self._ssh_cmd(mkdir_cmd)

        # Push each file
        for i, rel_path in enumerate(to_push):
            if callback:
                callback(i + 1, total, rel_path)

            abs_path = file_map.get(rel_path)
            if abs_path is None or not abs_path.exists():
                result["errors"].append(f"Fichier local introuvable : {rel_path}")
                continue

            remote_path = f"{self.central_path}/{rel_path}"
            ok = self._scp_push(str(abs_path), remote_path)
            if ok:
                result["pushed"] += 1
            else:
                result["errors"].append(f"Echec scp : {rel_path}")

        result["skipped"] = len(local_m) - total

        # Update remote manifest with the full local manifest
        # (pushed files now have local timestamps on the server)
        self._push_remote_manifest(local_m)

        # Push profile
        self.push_profile(self.profile)

        return result

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def pull(self, callback=None) -> dict:
        """Pull changed files from the server.

        Args:
            callback: optional ``callback(current, total, filename)`` for progress.

        Returns::

            {"pulled": int, "skipped": int, "errors": [str]}
        """
        result = {"pulled": 0, "skipped": 0, "errors": []}

        local_m = self._build_local_manifest()
        remote_m = self._get_remote_manifest()

        # Determine what to pull: files newer on server or server-only
        to_pull = []
        for rel_path, remote_info in remote_m.items():
            local_info = local_m.get(rel_path)
            if local_info is None:
                to_pull.append(rel_path)
            elif (remote_info["size"] != local_info["size"]
                  or remote_info["mtime"] > local_info["mtime"]):
                to_pull.append(rel_path)

        total = len(to_pull)
        if total == 0:
            result["skipped"] = len(remote_m)
            return result

        for i, rel_path in enumerate(to_pull):
            if callback:
                callback(i + 1, total, rel_path)

            local_abs = self._resolve_local_path(rel_path)
            if local_abs is None:
                result["errors"].append(f"Chemin local non résolu : {rel_path}")
                continue

            # Ensure local parent directory exists
            local_abs.parent.mkdir(parents=True, exist_ok=True)

            remote_path = f"{self.central_path}/{rel_path}"
            ok = self._scp_pull(remote_path, str(local_abs))
            if ok:
                result["pulled"] += 1
            else:
                result["errors"].append(f"Echec scp : {rel_path}")

        result["skipped"] = len(remote_m) - total
        return result

    def _resolve_local_path(self, rel_path: str) -> Path | None:
        """Map a relative manifest path back to a local absolute path.

        Mapping rules:
            sessions/<proj_name>/sessions-index.json  ->  ~/.claude/projects/<proj_name>/sessions-index.json
            sessions/<proj_name>/<file>.jsonl          ->  ~/.claude/projects/<proj_name>/<file>.jsonl
            sessions/history.jsonl                     ->  ~/.claude/history.jsonl
            config.json                                ->  ~/.config/clilauncher/config.json
        """
        parts = rel_path.split("/")

        if rel_path == "config.json":
            return CONFIG_FILE

        if parts[0] == "sessions":
            if len(parts) == 2 and parts[1] == "history.jsonl":
                return HISTORY_FILE
            if len(parts) == 3:
                proj_name = parts[1]
                filename = parts[2]
                return PROJECTS_DIR / proj_name / filename

        return None

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def push_profile(self, profile: dict) -> bool:
        """Save machine profile to the server."""
        import tempfile
        data = dict(profile)
        data["last_push"] = datetime.now(timezone.utc).isoformat()
        data["os"] = sys.platform

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="clilauncher_profile_",
        )
        try:
            json.dump(data, tmp, indent=2)
            tmp.close()
            remote = f"{self.central_path}/profiles/{self.machine_id}.json"
            return self._scp_push(tmp.name, remote)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Convenience: summary of diff for UI display
    # ------------------------------------------------------------------

    def diff_summary(self) -> dict:
        """Return a human-readable diff summary for display in confirmation dialogs.

        Returns::

            {
                "push_count": int,
                "pull_count": int,
                "up_to_date": int,
                "details": str,      # multi-line description
            }
        """
        d = self.diff()
        push_count = len(d["to_push"])
        pull_count = len(d["to_pull"]) + len(d["remote_only"])
        up_to_date = len(d["up_to_date"])

        lines = []
        if push_count:
            lines.append(f"{push_count} fichier(s) a envoyer (plus recents localement)")
        if pull_count:
            lines.append(f"{pull_count} fichier(s) a recevoir (plus recents sur le serveur)")
        if up_to_date:
            lines.append(f"{up_to_date} fichier(s) deja a jour")
        if not lines:
            lines.append("Rien a synchroniser")

        return {
            "push_count": push_count,
            "pull_count": pull_count,
            "up_to_date": up_to_date,
            "details": "\n".join(lines),
        }

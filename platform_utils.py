"""platform_utils.py — Cross-platform abstraction for CLILauncher.

Provides OS-agnostic functions for:
- Detecting running Claude sessions
- Finding and focusing terminal windows
- Launching sessions in terminal emulators
- Listing available terminals

Works on Linux and Windows. macOS support can be added later.
"""

import shutil
import subprocess
import sys

WINDOWS = sys.platform == "win32"

# Optional: psutil for cross-platform process inspection
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _clean_session_id(raw: str) -> str:
    """Strip all surrounding quotes and whitespace from a session ID."""
    return raw.strip().strip("\"'").strip("\"'")


# ---------------------------------------------------------------------------
# 1. Detect running Claude sessions
# ---------------------------------------------------------------------------

def _get_running_sessions_psutil() -> dict[str, int]:
    """Detect running 'claude --resume <id>' via psutil (cross-platform)."""
    running: dict[str, int] = {}
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
            cmd_str = " ".join(cmdline)
            if "claude" not in cmd_str or "--resume" not in cmd_str:
                continue
            for i, arg in enumerate(cmdline):
                if arg == "--resume" and i + 1 < len(cmdline):
                    sid = _clean_session_id(cmdline[i + 1])
                    if len(sid) > 30:
                        running[sid] = proc.info["pid"]
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return running


def _get_running_sessions_ps() -> dict[str, int]:
    """Detect running sessions via 'ps aux' (Linux fallback)."""
    running: dict[str, int] = {}
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if "claude" not in line or "--resume" not in line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pid = int(parts[1])
            for i, arg in enumerate(parts):
                if arg == "--resume" and i + 1 < len(parts):
                    sid = _clean_session_id(parts[i + 1])
                    if len(sid) > 30:
                        running[sid] = pid
                    break
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return running


def get_running_sessions() -> dict[str, int]:
    """Return {session_id: pid} for all running Claude --resume sessions.

    Uses psutil if available (works on both Linux and Windows),
    falls back to 'ps aux' on Linux when psutil is not installed.
    """
    if HAS_PSUTIL:
        return _get_running_sessions_psutil()
    if not WINDOWS:
        return _get_running_sessions_ps()
    # Windows without psutil: cannot detect sessions
    return {}


# ---------------------------------------------------------------------------
# 2. Find and focus the terminal window of a running session
# ---------------------------------------------------------------------------

def _walk_pid_ancestors(pid: int, max_depth: int = 5) -> list[int]:
    """Return list of ancestor PIDs from pid up to init, max max_depth levels."""
    ancestors: list[int] = []
    current = pid
    for _ in range(max_depth):
        try:
            if HAS_PSUTIL:
                parent = psutil.Process(current).ppid()
            else:
                result = subprocess.run(
                    ["ps", "-o", "ppid=", "-p", str(current)],
                    capture_output=True, text=True, timeout=3,
                )
                parent = int(result.stdout.strip())
            if parent <= 1:
                break
            ancestors.append(parent)
            current = parent
        except (ValueError, OSError):
            break
        except Exception:
            break
    return ancestors


def _find_and_focus_linux(claude_pid: int) -> bool:
    """Linux: walk PID tree, find window via xdotool, focus via wmctrl."""
    if not shutil.which("xdotool"):
        return False

    try:
        # Walk up: claude -> bash -> terminal
        pid = claude_pid
        for _ in range(3):
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=3,
            )
            ppid = result.stdout.strip()
            if not ppid:
                break
            # Try to find window at each level
            xdo = subprocess.run(
                ["xdotool", "search", "--pid", ppid],
                capture_output=True, text=True, timeout=3,
            )
            if xdo.stdout.strip():
                window_id = int(xdo.stdout.strip().splitlines()[0])
                return _focus_window_linux(window_id)
            pid = int(ppid)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return False


def _focus_window_linux(window_id: int) -> bool:
    """Raise and focus a window by its X11 window ID."""
    try:
        hex_id = f"0x{window_id:08x}"
        subprocess.Popen(["wmctrl", "-i", "-a", hex_id])
        return True
    except OSError:
        try:
            subprocess.Popen(["xdotool", "windowactivate", str(window_id)])
            return True
        except OSError:
            return False


def _find_and_focus_windows(claude_pid: int) -> bool:
    """Windows: enumerate windows via ctypes, match against PID tree, focus."""
    if not WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Collect all PIDs in the ancestor tree
        pids_to_check = {claude_pid}
        if HAS_PSUTIL:
            for ancestor in _walk_pid_ancestors(claude_pid):
                pids_to_check.add(ancestor)

        found_hwnd = None

        def enum_callback(hwnd, _):
            nonlocal found_hwnd
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids_to_check and user32.IsWindowVisible(hwnd):
                found_hwnd = hwnd
                return False  # stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM,
        )
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        if found_hwnd:
            SW_RESTORE = 9
            user32.ShowWindow(found_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(found_hwnd)
            return True
    except Exception:
        pass
    return False


def find_and_focus_session_window(claude_pid: int) -> bool:
    """Find the terminal window hosting a Claude session and bring it to front.

    On Linux: walks PID tree, uses xdotool + wmctrl.
    On Windows: uses ctypes EnumWindows + SetForegroundWindow.
    Returns True if window was found and focused, False otherwise.
    """
    if WINDOWS:
        return _find_and_focus_windows(claude_pid)
    return _find_and_focus_linux(claude_pid)


# ---------------------------------------------------------------------------
# 3. Terminal detection
# ---------------------------------------------------------------------------

# Terminal profiles: name -> (executable, build_args_function)
# Linux terminals
_LINUX_TERMINALS = ["tilix", "konsole", "gnome-terminal", "xterm"]
# Windows terminals
_WINDOWS_TERMINALS = ["wt", "powershell", "cmd"]


def get_available_terminals() -> list[str]:
    """Return list of terminal emulators available on this OS.

    Uses shutil.which() to check for each known terminal.
    On Windows, powershell and cmd are always available.
    """
    if WINDOWS:
        available = []
        for term in _WINDOWS_TERMINALS:
            if term in ("powershell", "cmd"):
                available.append(term)  # always present on Windows
            elif shutil.which(term):
                available.append(term)
        return available
    else:
        return [t for t in _LINUX_TERMINALS if shutil.which(t)]


# ---------------------------------------------------------------------------
# 4. Launch a session in a terminal (--resume existing session)
# ---------------------------------------------------------------------------

def _build_full_cmd(project_path: str, claude_cmd: str, claude_flags: str,
                    extra_args: str) -> str:
    """Build the full shell command string for launching Claude."""
    return f'cd "{project_path}" && {claude_cmd} {claude_flags} {extra_args}'


def _launch_linux(full_cmd: str, terminal: str) -> bool:
    """Launch full_cmd in the given Linux terminal emulator."""
    try:
        if terminal == "gnome-terminal":
            subprocess.Popen(
                ["gnome-terminal", "--", "bash", "-c", full_cmd],
                start_new_session=True,
            )
        elif terminal == "konsole":
            subprocess.Popen(
                ["konsole", "-e", "bash", "-c", full_cmd],
                start_new_session=True,
            )
        elif terminal == "xterm":
            subprocess.Popen(
                ["xterm", "-e", f"bash -c '{full_cmd}'"],
                start_new_session=True,
            )
        else:
            # tilix (default) and any other terminal
            subprocess.Popen(
                [terminal, "-e", f"bash -c '{full_cmd}'"],
                start_new_session=True,
            )
        return True
    except (FileNotFoundError, OSError):
        return False


def _launch_windows(full_cmd: str, terminal: str) -> bool:
    """Launch full_cmd in the given Windows terminal."""
    try:
        if terminal == "wt":
            # Windows Terminal
            subprocess.Popen(
                ["wt", "cmd", "/k", full_cmd],
                creationflags=0x00000010,  # CREATE_NEW_CONSOLE
            )
        elif terminal == "powershell":
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command", full_cmd],
                creationflags=0x00000010,
            )
        else:
            # cmd (default fallback)
            subprocess.Popen(
                ["cmd", "/k", full_cmd],
                creationflags=0x00000010,
            )
        return True
    except (FileNotFoundError, OSError):
        return False


def launch_in_terminal(project_path: str, session_id: str,
                       claude_cmd: str = "claude",
                       claude_flags: str = "--dangerously-skip-permissions --chrome",
                       terminal: str = "") -> bool:
    """Launch 'claude --resume <session_id>' in a terminal emulator.

    Args:
        project_path: Working directory for the session.
        session_id: The Claude session ID to resume.
        claude_cmd: The claude executable name/path.
        claude_flags: Flags to pass to claude (e.g. --dangerously-skip-permissions).
        terminal: Terminal emulator to use. If empty, picks the first available.

    Returns True if the terminal was launched successfully.
    """
    if not terminal:
        available = get_available_terminals()
        if not available:
            return False
        terminal = available[0]

    full_cmd = _build_full_cmd(
        project_path, claude_cmd, claude_flags,
        f'--resume "{session_id}"',
    )

    if WINDOWS:
        return _launch_windows(full_cmd, terminal)

    # Linux: try requested terminal, then fallback to others
    if _launch_linux(full_cmd, terminal):
        return True

    # Fallback: try other available terminals
    for alt in get_available_terminals():
        if alt != terminal and _launch_linux(full_cmd, alt):
            return True
    return False


# ---------------------------------------------------------------------------
# 5. Launch a NEW session in a terminal (with -n flag)
# ---------------------------------------------------------------------------

def launch_new_session_in_terminal(project_path: str, session_name: str,
                                   claude_cmd: str = "claude",
                                   claude_flags: str = "--dangerously-skip-permissions --chrome",
                                   terminal: str = "") -> bool:
    """Launch 'claude -n <session_name>' in a terminal emulator.

    Args:
        project_path: Working directory for the session.
        session_name: Name for the new session (-n flag).
        claude_cmd: The claude executable name/path.
        claude_flags: Flags to pass to claude.
        terminal: Terminal emulator to use. If empty, picks the first available.

    Returns True if the terminal was launched successfully.
    """
    if not terminal:
        available = get_available_terminals()
        if not available:
            return False
        terminal = available[0]

    full_cmd = _build_full_cmd(
        project_path, claude_cmd, claude_flags,
        f'-n "{session_name}"',
    )

    if WINDOWS:
        return _launch_windows(full_cmd, terminal)

    if _launch_linux(full_cmd, terminal):
        return True

    for alt in get_available_terminals():
        if alt != terminal and _launch_linux(full_cmd, alt):
            return True
    return False

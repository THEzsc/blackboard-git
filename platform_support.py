"""Platform paths, backend choice and process-level session locking."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import time


def cache_root(platform=None, env=None):
    platform = platform or sys.platform
    env = os.environ if env is None else env
    if env.get('BLACKBOARD_CACHE_DIR'):
        return Path(env['BLACKBOARD_CACHE_DIR']).expanduser().resolve()
    home = Path.home()
    if platform == 'darwin':
        return home / 'Library/Application Support/BlackboardGit'
    if platform == 'win32':
        return Path(env.get('LOCALAPPDATA', str(home / 'AppData/Local'))) / 'BlackboardGit'
    return Path(env.get('XDG_DATA_HOME', str(home / '.local/share'))) / 'blackboard-git'


def backend(platform=None, env=None):
    platform = platform or sys.platform
    env = os.environ if env is None else env
    selected = env.get('BLACKBOARD_BACKEND', 'auto')
    if selected not in ('auto', 'webkit', 'chromium'):
        raise ValueError('BLACKBOARD_BACKEND must be auto, webkit or chromium')
    if selected == 'auto':
        return 'webkit' if platform == 'darwin' else 'chromium'
    if selected == 'webkit' and platform != 'darwin':
        raise ValueError('WebKit backend requires macOS; select chromium')
    return selected


@contextmanager
def session_lock(path, timeout=960):
    with Path(path).open('a+b') as file:
        if os.name == 'nt':
            import msvcrt
            if file.tell() == 0:
                file.write(b'0'); file.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    file.seek(0); msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Another Blackboard sync is still running')
                    time.sleep(0.1)
            try:
                yield
            finally:
                file.seek(0); msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Another Blackboard sync is still running')
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)

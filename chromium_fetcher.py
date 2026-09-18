"""Use an installed browser first; download a shared Playwright build only if absent."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit


def browser_candidates(platform=None, env=None):
    platform = platform or sys.platform
    env = os.environ if env is None else env
    override = env.get('BLACKBOARD_BROWSER_PATH')
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise ValueError('BLACKBOARD_BROWSER_PATH does not point to a file')
        return [path]
    paths = []
    if platform == 'win32':
        for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if env.get(key):
                for rel in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe', 'Chromium/Application/chrome.exe'):
                    paths.append(Path(env[key]) / rel)
    elif platform == 'darwin':
        for folder in (Path('/Applications'), Path.home() / 'Applications'):
            for rel in ('Google Chrome.app/Contents/MacOS/Google Chrome', 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge', 'Chromium.app/Contents/MacOS/Chromium'):
                paths.append(folder / rel)
    for name in ('google-chrome', 'google-chrome-stable', 'msedge', 'microsoft-edge', 'microsoft-edge-stable', 'chromium', 'chromium-browser', 'chrome'):
        found = shutil.which(name, path=env.get('PATH', ''))
        if found:
            paths.append(Path(found))
    return list(dict.fromkeys(p for p in paths if p.is_file()))


def launch_context(chromium, cache, headless=False):
    profile = cache / 'chromium-profile'
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    candidates = browser_candidates()
    # Respect Playwright's standard user-level, versioned shared cache and optional
    # PLAYWRIGHT_BROWSERS_PATH. Never download Chrome/Edge over the user's installation.
    if not candidates:
        bundled = Path(chromium.executable_path)
        if not bundled.is_file():
            print('Blackboard: no installed browser found; downloading Chromium to the shared Playwright cache.', file=sys.stderr)
            subprocess.run([sys.executable, '-m', 'playwright', 'install', '--no-shell', 'chromium'], check=True, stdout=sys.stderr)
        candidates = [Path(chromium.executable_path)]
    errors = []
    for executable in candidates:
        try:
            context = chromium.launch_persistent_context(str(profile), executable_path=str(executable), headless=headless,
                accept_downloads=False, timeout=45000)
            print('Blackboard: using browser ' + str(executable), file=sys.stderr)
            return context
        except Exception as error:
            errors.append(type(error).__name__)
    raise RuntimeError('Installed browser could not launch (' + ', '.join(errors) + '). Check browser policies, close any other process using this app profile, or set BLACKBOARD_BROWSER_PATH. On Linux install browser system dependencies (python -m playwright install-deps chromium). No extra browser was downloaded.')


class SnapshotWriter:
    def __init__(self, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.seen = set()
        self.total = 0
        self.done = False

    def receive(self, message):
        kind = message.get('kind')
        if kind == 'progress':
            print(str(message.get('text', '')), file=sys.stderr)
        elif kind == 'file':
            path = message['path']
            parts = path.split('/')
            if (not path or path.startswith('/') or '\\' in path or ':' in path or
                any(part in ('', '.', '..') for part in parts) or path in self.seen or
                not (path.startswith(('files/', 'pages/')) or path in ('manifest.json', 'index.html', 'announcements-source.html'))):
                raise ValueError('Unsafe or duplicate exporter path')
            data = base64.b64decode(message['base64'], validate=True)
            self.total += len(data)
            if self.total > 320 * 1024 * 1024:
                raise ValueError('Export exceeds size limit')
            target = self.output.joinpath(*parts)
            if not target.resolve().is_relative_to(self.output.resolve()):
                raise ValueError('Unsafe exporter destination')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.seen.add(path)
        elif kind == 'done':
            if message.get('complete') is not True or not {'manifest.json', 'announcements-source.html'} <= self.seen:
                raise ValueError('Incomplete export; repository not updated')
            self.done = True
        else:
            raise ValueError('Unknown exporter message')


def evaluate(client, world, expression, await_promise=False):
    result = client.send('Runtime.evaluate', {'expression': expression, 'contextId': world,
        'returnByValue': True, 'awaitPromise': await_promise})
    if result.get('exceptionDetails'):
        raise RuntimeError('Browser script failed; repository not updated')
    return result.get('result', {}).get('value')


def fetch(url, output, course, script, cache):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError('Chromium backend needs Playwright. Run setup.py or pip install -r requirements-chromium.txt with this Python interpreter.') from error
    writer = SnapshotWriter(output)
    with sync_playwright() as playwright:
        context = launch_context(playwright.chromium, cache)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print('Blackboard: complete SSO in the browser if requested. This app uses its own persistent profile.', file=sys.stderr)
            deadline = time.monotonic() + 900
            client = context.new_cdp_session(page)
            world = None
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise RuntimeError('Login window closed')
                if urlsplit(page.url).netloc == 'learn.intl.zju.edu.cn':
                    try:
                        frame = client.send('Page.getFrameTree')['frameTree']['frame']['id']
                        world = client.send('Page.createIsolatedWorld', {'frameId': frame, 'worldName': 'blackboard-git'})['executionContextId']
                        probe = "fetch('/learn/api/public/v1/courses/' + " + json.dumps(course) + ",{credentials:'same-origin'}).then(r=>r.ok && (r.headers.get('content-type')||'').includes('json')).catch(()=>false)"
                        if evaluate(client, world, probe, True):
                            break
                    except Exception:
                        # SSO navigation can destroy a context between probe requests.
                        pass
                page.wait_for_timeout(1000)
            else:
                raise TimeoutError('SSO login timed out')
            # Bridge and queue exist only in an isolated world, not in page JavaScript.
            evaluate(client, world, "window.__blackboardCourseId=" + json.dumps(course) + ";window.__bbMessages=[];window.webkit={messageHandlers:{blackboardExport:{postMessage:m=>window.__bbMessages.push(m)}}};")
            evaluate(client, world, script)
            while time.monotonic() < deadline and not writer.done:
                message = evaluate(client, world, 'window.__bbMessages.shift() || null')
                if message:
                    writer.receive(message)
                else:
                    page.wait_for_timeout(100)
            if not writer.done:
                raise TimeoutError('Course export timed out; repository not updated')
        finally:
            context.close()

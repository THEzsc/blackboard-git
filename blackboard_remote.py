"""Git remote transport backed by live Blackboard snapshots and platform-selected browser sessions."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, parse_qs
from blackboard_git import pull, git
from finalize_export import finalize
from platform_support import backend, cache_root, session_lock

ROOT = Path(__file__).resolve().parent
HOST = 'learn.intl.zju.edu.cn'
CACHE = cache_root()

def parse_url(raw):
    if raw.startswith('blackboard::'): raw=raw[len('blackboard::'):]
    u=urlsplit(raw)
    if u.scheme!='https' or u.hostname!=HOST or u.port not in (None,443) or u.username or u.password:
        raise ValueError('Only https://learn.intl.zju.edu.cn course URLs are supported')
    ids=parse_qs(u.query).get('course_id',[])
    if len(ids)!=1 or not re.fullmatch(r'_\d+_\d+',ids[0]):
        raise ValueError('A course URL containing course_id=_1234_1 is required')
    course=ids[0]
    # Discard all unrelated query parameters, including any SSO code/token.
    return course, f'https://{HOST}/webapps/blackboard/execute/modulepage/view?course_id={course}&mode=view'

def exporter_script():
    script=(ROOT/'export-course.js').read_text(encoding='utf-8')
    script=script.replace("const courseId = new URL(location.href).searchParams.get('course_id');", "const courseId = window.__blackboardCourseId;")
    script=script.replace("console.log('[Course Mirror]', s);", "window.webkit.messageHandlers.blackboardExport.postMessage({kind:'progress',text:s});")
    script=script.replace('    manifest.complete=!issues.length;', '''    try {
      const r = await request(`${origin}/webapps/blackboard/execute/announcement?method=search&context=mybb&course_id=${courseId}&viewChoice=2`);
      const announcementHTML = await r.text();
      const doc = new DOMParser().parseFromString(announcementHTML, 'text/html');
      if (!doc.getElementById('announcementList')) {
        const container = doc.getElementById('containerdiv');
        const form = container?.querySelector('form#announcementForm');
        const correctCourse = form?.querySelector('input[name="course_id"]')?.value === courseId;
        const courseView = form?.querySelector('input[name="viewChoice"]')?.value === '2';
        const remainder = container?.cloneNode(true);
        remainder?.querySelectorAll('script,style,link,form#announcementForm,h2.hideoff').forEach(el=>el.remove());
        // Original renders an empty course announcement page as only its filter form.
        // Do not treat login, permission errors or an unknown layout as an empty list.
        if (!correctCourse || !courseView || !remainder || remainder.textContent.trim() || remainder.children.length) {
          throw Error('Announcement list unavailable (unrecognized or inaccessible page)');
        }
      }
      add('announcements-source.html', announcementHTML);
    } catch(e) { note('announcements', courseId, e.message); }
    manifest.complete=!issues.length;''')
    marker='    // ZIP store format:'
    assert marker in script
    bridge='''    for (const issue of issues) {
      window.webkit.messageHandlers.blackboardExport.postMessage({kind:'progress',text:`Export issue [${issue.stage}] ${issue.id}: ${issue.message}`});
    }
    for (const file of files) {
      let binary = '';
      for (let i=0;i<file.data.length;i+=32768) binary += String.fromCharCode(...file.data.subarray(i,i+32768));
      window.webkit.messageHandlers.blackboardExport.postMessage({kind:'file',path:file.path,base64:btoa(binary)});
    }
    window.webkit.messageHandlers.blackboardExport.postMessage({kind:'done',complete:manifest.complete});
    return;
'''
    return script.replace(marker,bridge+marker,1)

def refresh(raw):
    course,url=parse_url(raw)
    CACHE.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(CACHE,0o700)
    # Each backend shares one persistent profile. Serialize exports across courses.
    with session_lock(CACHE/'session.lock'):
        repo=CACHE/course/'repository'; repo.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='export-',dir=repo.parent) as tmp:
            snapshot=Path(tmp)/'snapshot'
            fixture=os.environ.get('BLACKBOARD_OFFLINE_SNAPSHOT')
            if fixture:
                print('Blackboard: OFFLINE snapshot mode; no online check.',file=sys.stderr)
                snapshot=Path(fixture).resolve()
                if json.loads((snapshot/'manifest.json').read_text(encoding='utf-8'))['courseId']!=course:
                    raise ValueError('Offline snapshot belongs to another course')
            else:
                app=ROOT/'native/Blackboard Git.app/Contents/MacOS/BlackboardFetcher'
                if backend() == 'webkit' and not app.exists(): raise ValueError('Run python3 setup.py first')
                script=Path(tmp)/'export.js'; script.write_text(exporter_script(), encoding='utf-8')
                # The application has its own persistent WKWebsiteDataStore; no cookie extraction.
                if backend() == 'webkit':
                    result = subprocess.run([str(app),url,str(snapshot),course,str(script)],stdout=sys.stderr,timeout=920)
                    if result.returncode:
                        manifest = snapshot/'manifest.json'
                        if manifest.exists():
                            issues = json.loads(manifest.read_text(encoding='utf-8')).get('issues', [])
                            if issues:
                                raise RuntimeError('Export incomplete: ' + '; '.join(f"{i['stage']} / {i['id']}: {i['message']}" for i in issues))
                        raise RuntimeError(f'Browser export stopped (exit {result.returncode}); no course update was committed')
                else:
                    from chromium_fetcher import fetch
                    fetch(url,snapshot,course,script.read_text(encoding='utf-8'),CACHE)
                with contextlib.redirect_stdout(sys.stderr):
                    finalize(snapshot,snapshot/'announcements-source.html',Path(tmp)/'verified.zip')
                (snapshot/'announcements-source.html').unlink()
            # Restore the directory synchronizer's local bookkeeping if the cache was seeded by Git clone.
            stable=repo/'.blackboard/git-snapshot.json'
            state=repo/'.blackboard/sync-state.json'
            if stable.exists() and not state.exists(): state.write_text(stable.read_text(encoding='utf-8'), encoding='utf-8')
            with contextlib.redirect_stdout(sys.stderr): pull(snapshot,repo)
        return repo

def helper():
    if len(sys.argv)!=3: raise ValueError('This helper is invoked by Git')
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(0, os.O_BINARY)
        msvcrt.setmode(1, os.O_BINARY)
    raw=sys.argv[2]
    parse_url(raw)
    for key in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_PREFIX'):
        os.environ.pop(key,None)
    # Do not use buffered stdin: Git switches this same fd to its binary wire protocol.
    def line():
        data=bytearray()
        while True:
            b=os.read(0,1)
            if not b:return data.decode()
            if b==b'\n':return data.decode()
            data+=b
    while True:
        command=line()
        if not command:return
        if command=='capabilities':
            print('connect\n',flush=True)
        elif command=='connect git-upload-pack':
            repo=refresh(raw)
            print('',flush=True)
            raise SystemExit(subprocess.call(['git','upload-pack',str(repo)]))
        elif command.startswith('connect '):
            raise ValueError('Blackboard remote is read-only; pushing is unsupported')
        else:
            raise ValueError('Unsupported Git helper command: '+command)

if __name__=='__main__':
    try: helper()
    except Exception as error:
        print('Blackboard Git: '+str(error),file=sys.stderr)
        sys.exit(1)

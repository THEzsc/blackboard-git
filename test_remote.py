import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from blackboard_remote import parse_url, ROOT

class RemoteTest(unittest.TestCase):
    def test_url_validation(self):
        self.assertEqual('_1234_1',parse_url('https://learn.intl.zju.edu.cn/x?course_id=_1234_1')[0])
        for url in ['https://evil.test/?course_id=_1234_1','https://user:pass@learn.intl.zju.edu.cn/?course_id=_1234_1','https://learn.intl.zju.edu.cn/?course_id=../x']:
            with self.assertRaises(ValueError):parse_url(url)
    def test_real_git_clone_and_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp); source=tmp/'snapshot';source.mkdir()
            (source/'folder.html').write_text('folder');(source/'file.html').write_text('file')
            manifest={'complete':True,'issues':[],'courseId':'_123_1','courseName':'Test','finishedAt':'2026-09-18','assets':[],
                'nodes':[{'id':'folder','title':'Content','type':'resource/x-bb-folder','page':'folder.html'},
                {'id':'file','parentId':'folder','title':'Notes','type':'resource/x-bb-file','files':['test.txt'],'page':'file.html'}]}
            def version(text):
                data=text.encode();(source/'test.txt').write_bytes(data)
                manifest['assets']=[{'path':'test.txt','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]
                (source/'manifest.json').write_text(json.dumps(manifest))
            version('first')
            env=dict(os.environ,PATH=str(ROOT)+os.pathsep+os.environ['PATH'],BLACKBOARD_OFFLINE_SNAPSHOT=str(source),BLACKBOARD_CACHE_DIR=str(tmp/'cache'))
            def command(*args,check=True):return subprocess.run(['git',*args],env=env,capture_output=True,text=True,check=check)
            dest=tmp/'checkout';url='blackboard::https://learn.intl.zju.edu.cn/course?course_id=_123_1'
            command('clone',url,str(dest))
            self.assertEqual('first',(dest/'Content/Notes.txt').read_text())
            second=tmp/'plain-https-checkout'
            command('-c','url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf=https://learn.intl.zju.edu.cn/', 'clone',url.removeprefix('blackboard::'),str(second))
            self.assertEqual('first',(second/'Content/Notes.txt').read_text())
            first=command('-C',str(dest),'rev-parse','HEAD').stdout
            version('second');command('-C',str(dest),'pull','--ff-only')
            self.assertEqual('second',(dest/'Content/Notes.txt').read_text())
            self.assertNotEqual(first,command('-C',str(dest),'rev-parse','HEAD').stdout)
            command('-C',str(dest),'pull','--ff-only')
            self.assertEqual('2',command('-C',str(dest),'rev-list','--count','HEAD').stdout.strip())
            (dest/'Content/Notes.txt').write_text('local edit');version('third')
            self.assertNotEqual(0,command('-C',str(dest),'pull','--ff-only',check=False).returncode)
            self.assertEqual('local edit',(dest/'Content/Notes.txt').read_text())
            self.assertNotEqual(0,command('-C',str(dest),'push',check=False).returncode)

if __name__=='__main__': unittest.main()

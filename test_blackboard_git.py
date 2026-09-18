import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from blackboard_git import pull, git

class VersioningTest(unittest.TestCase):
    def test_history_deletion_noop_and_personal_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source'; source.mkdir()
            dest = Path(tmp)/'course'; dest.mkdir()
            personal = dest/'作业答案.txt'; personal.write_text('my work', encoding='utf-8')
            (source/'file.txt').write_text('v1', encoding='utf-8')
            (source/'folder.html').write_text('folder', encoding='utf-8')
            (source/'file.html').write_text('file', encoding='utf-8')
            manifest = {'complete':True, 'issues':[], 'courseId':'_test_1', 'courseName':'Test', 'finishedAt':'2026-09-16',
                'nodes':[{'id':'folder', 'title':'Content', 'type':'resource/x-bb-folder', 'page':'folder.html'},
                    {'id':'file', 'parentId':'folder', 'title':'Notes', 'type':'resource/x-bb-file', 'files':['file.txt'], 'page':'file.html'}],
                'assets':[]}
            def run():
                data=(source/'file.txt').read_bytes()
                manifest['assets']=[{'path':'file.txt','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}] if len(manifest['nodes'])>1 else []
                (source/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()): pull(source,dest)
            run(); first=git(dest,'rev-parse','HEAD')
            run(); self.assertEqual(first,git(dest,'rev-parse','HEAD'))
            (source/'file.txt').write_text('v2', encoding='utf-8'); run()
            self.assertEqual('v1',git(dest,'show',first+':Content/Notes.txt'))
            self.assertEqual('v2',(dest/'Content/Notes.txt').read_text(encoding='utf-8'))
            (dest/'Content/Notes.txt').write_text('local edits', encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Local change preserved'): run()
            self.assertEqual('local edits',(dest/'Content/Notes.txt').read_text(encoding='utf-8'))
            (dest/'Content/Notes.txt').write_text('v2', encoding='utf-8')
            manifest['nodes']=manifest['nodes'][:1]; run()
            self.assertFalse((dest/'Content/Notes.txt').exists())
            self.assertEqual('3',git(dest,'rev-list','--count','HEAD'))
            self.assertEqual('my work',personal.read_text(encoding='utf-8'))
            self.assertNotIn('作业答案',git(dest,'ls-files'))
            run(); self.assertEqual('3',git(dest,'rev-list','--count','HEAD'))

if __name__=='__main__': unittest.main()

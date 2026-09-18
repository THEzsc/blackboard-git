import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from chromium_fetcher import browser_candidates, launch_context, SnapshotWriter
from platform_support import backend, cache_root, session_lock
from install_git_helper import install

ROOT=Path(__file__).resolve().parent

class PlatformTests(unittest.TestCase):
    def test_platform_selection_and_paths(self):
        for platform, expected in [('darwin','webkit'),('win32','chromium'),('linux','chromium')]:
            self.assertEqual(expected,backend(platform,{}))
        self.assertEqual('chromium',backend('darwin',{'BLACKBOARD_BACKEND':'chromium'}))
        with self.assertRaises(ValueError):backend('win32',{'BLACKBOARD_BACKEND':'webkit'})
        self.assertEqual(Path('/tmp/local/BlackboardGit'),cache_root('win32',{'LOCALAPPDATA':'/tmp/local'}))
        self.assertEqual(Path('/tmp/data/blackboard-git'),cache_root('linux',{'XDG_DATA_HOME':'/tmp/data'}))

    def test_windows_detection_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            browser=Path(tmp)/'Microsoft/Edge/Application/msedge.exe'
            browser.parent.mkdir(parents=True);browser.touch()
            self.assertEqual([browser],browser_candidates('win32',{'PROGRAMFILES':tmp,'PATH':''}))
            self.assertEqual([browser],browser_candidates('linux',{'BLACKBOARD_BROWSER_PATH':str(browser)}))
            with self.assertRaises(ValueError):browser_candidates('linux',{'BLACKBOARD_BROWSER_PATH':tmp+'/missing'})

    def test_browser_reuse_and_download_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp);installed=cache/'chrome';installed.touch()
            browser=Mock();browser.executable_path=str(cache/'shared-chromium')
            with patch('chromium_fetcher.browser_candidates',return_value=[installed]), patch('chromium_fetcher.subprocess.run') as download:
                launch_context(browser,cache)
                download.assert_not_called()
                self.assertEqual(str(installed),browser.launch_persistent_context.call_args.kwargs['executable_path'])
            Path(browser.executable_path).touch()
            with patch('chromium_fetcher.browser_candidates',return_value=[]), patch('chromium_fetcher.subprocess.run') as download:
                launch_context(browser,cache);download.assert_not_called()
            Path(browser.executable_path).unlink()
            with patch('chromium_fetcher.browser_candidates',return_value=[]), patch('chromium_fetcher.subprocess.run') as download:
                launch_context(browser,cache);download.assert_called_once()
                self.assertEqual(['install','--no-shell','chromium'],download.call_args.args[0][-3:])
            browser.launch_persistent_context.side_effect=RuntimeError('policy')
            with patch('chromium_fetcher.browser_candidates',return_value=[installed]), patch('chromium_fetcher.subprocess.run') as download:
                with self.assertRaises(RuntimeError):launch_context(browser,cache)
                download.assert_not_called()

    def test_writer_rejects_unsafe_and_incomplete_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer=SnapshotWriter(tmp)
            for path in ('../secret','/file','files/../../secret','files/C:secret','files\\bad'):
                with self.assertRaises(ValueError):writer.receive({'kind':'file','path':path,'base64':'YQ=='})
            with self.assertRaises(ValueError):writer.receive({'kind':'done','complete':True})
            for path in ('manifest.json','announcements-source.html'):
                writer.receive({'kind':'file','path':path,'base64':base64.b64encode(b'test').decode()})
            writer.receive({'kind':'done','complete':True});self.assertTrue(writer.done)

    def test_launcher_preserves_interpreter_and_works_with_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher=install(ROOT,bindir=tmp,rewrite=False)
            env=dict(os.environ,PATH=tmp+os.pathsep+os.environ['PATH'])
            result=subprocess.run(['git','remote-blackboard'],env=env,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode)
            self.assertIn('invoked by Git',result.stderr)
            with self.assertRaises(ValueError):install(ROOT,bindir=tmp,python='/other/python',rewrite=False)
            self.assertTrue(launcher.is_file())

    def test_lock_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            with session_lock(Path(tmp)/'lock'):
                with self.assertRaises(TimeoutError):
                    with session_lock(Path(tmp)/'lock',timeout=0):pass
            with session_lock(Path(tmp)/'lock',timeout=0):pass

if __name__=='__main__':unittest.main()

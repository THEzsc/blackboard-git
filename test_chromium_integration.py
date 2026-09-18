"""Optional real-browser test; all site traffic is served by synthetic local routes."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from blackboard_remote import exporter_script
from chromium_fetcher import fetch, launch_context
from finalize_export import parse_announcements
from test_announcements import EMPTY


@unittest.skipUnless(os.environ.get('BLACKBOARD_BROWSER_TESTS')=='1', 'Set BLACKBOARD_BROWSER_TESTS=1 for real-browser tests')
class ChromiumIntegration(unittest.TestCase):
    def test_isolated_export_and_persistent_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'cache'; cache.mkdir()
            observed=[]; contexts=[]
            def launch(chromium, path):
                context=launch_context(chromium,path,headless=True)
                contexts.append(context)
                def route(request):
                    url=urlsplit(request.request.url); path=url.path
                    if url.hostname!='learn.intl.zju.edu.cn':
                        request.abort();return
                    if path.endswith('/attachments/_3_1/download'):
                        request.fulfill(status=200,content_type='application/pdf',body=b'%PDF-1.4\nSynthetic fixture\n');return
                    if path.endswith('/attachments'):
                        value={'results':[{'id':'_3_1','fileName':'notes.pdf'}]}
                    elif path.endswith('/children'):
                        value={'results':[{'id':'_2_1','parentId':'_1_1','title':'Notes','contentHandler':{'id':'resource/x-bb-file'}}]}
                    elif path.endswith('/contents'):
                        value={'results':[{'id':'_1_1','title':'Content','hasChildren':True,'contentHandler':{'id':'resource/x-bb-folder'}}]}
                    elif '/learn/api/' in path:
                        value={'name':'Synthetic course'}
                    else:
                        observed.append(request.request.headers.get('cookie',''))
                        body=EMPTY if attempt == 1 else '<html><body><ul id="announcementList"><li><h3>Test announcement</h3></li></ul></body></html>'
                        request.fulfill(status=200,content_type='text/html',headers={'Set-Cookie':'fixture_session=retained; Max-Age=3600; Secure; HttpOnly; Path=/'},body=body);return
                    request.fulfill(status=200,content_type='application/json',body=json.dumps(value))
                context.route('**/*',route)
                return context
            url='https://learn.intl.zju.edu.cn/webapps/blackboard/execute/modulepage/view?course_id=_1234_1'
            for attempt in range(2):
                start=len(observed)
                with patch('chromium_fetcher.launch_context',side_effect=launch):
                    fetch(url,Path(tmp)/str(attempt),'_1234_1',exporter_script(),cache)
                manifest=json.loads((Path(tmp)/str(attempt)/'manifest.json').read_text(encoding='utf-8'))
                self.assertTrue(manifest['complete']);self.assertEqual(1,len(manifest['assets']))
                if attempt==1:
                    self.assertIn('fixture_session=retained',observed[start])
                    announcement=(Path(tmp)/str(attempt)/'announcements-source.html').read_text(encoding='utf-8')
                    self.assertEqual([],parse_announcements(announcement,'_1234_1').children)

if __name__=='__main__':unittest.main()

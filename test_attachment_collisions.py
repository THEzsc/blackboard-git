import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from sync_directory import sync

class AttachmentCollisionTests(unittest.TestCase):
    def test_duplicates_and_distinct_same_named_attachments(self):
        for duplicate in (True, False):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source';source.mkdir();(source/'files').mkdir();dest=Path(tmp)/'out'
                assets=[];names=[]
                for index,data in enumerate((b'first',b'first' if duplicate else b'second'),1):
                    rel=f'files/_2_1-_{index}_1-book.pdf';names.append(rel)
                    (source/rel).write_bytes(data)
                    assets.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                (source/'folder.html').write_text('folder')
                (source/'book.html').write_text(''.join(f'<a href="{p}">file</a>' for p in names))
                manifest={'complete':True,'issues':[],'courseId':'_1234_1','courseName':'Test','finishedAt':'test','assets':assets,'nodes':[
                    {'id':'folder','title':'Content','type':'resource/x-bb-folder','page':'folder.html'},
                    {'id':'book','parentId':'folder','title':'Textbook','type':'resource/x-bb-document','page':'book.html','files':names}]}
                (source/'manifest.json').write_text(json.dumps(manifest))
                with contextlib.redirect_stdout(io.StringIO()):sync(source,dest)
                files=list((dest/'Content/Textbook').glob('*.pdf'))
                self.assertEqual(1 if duplicate else 2,len(files))
                self.assertEqual({b'first'} if duplicate else {b'first',b'second'},set(f.read_bytes() for f in files))
                page=(dest/'Content/Textbook.html').read_text()
                self.assertNotIn('files/_2_1',page)
                before={str(f):f.read_bytes() for f in files}
                with contextlib.redirect_stdout(io.StringIO()):sync(source,dest)
                self.assertEqual(before,{str(f):f.read_bytes() for f in (dest/'Content/Textbook').glob('*.pdf')})

if __name__=='__main__':unittest.main()

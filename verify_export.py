"""Validate a course ZIP's CRC, hashes, safe paths and local HTML references."""
import argparse, hashlib, json, posixpath, zipfile
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from pathlib import PurePosixPath
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.refs=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k in ('href','src') and v: self.refs.append(v)
def verify(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); errors=[]
        if z.testzip(): errors.append('CRC mismatch')
        if len(names)!=len(set(names)): errors.append('Duplicate archive path')
        for name in names:
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name: errors.append('Unsafe path: '+name)
        m=json.loads(z.read('manifest.json'))
        for asset in m['assets']:
            data=z.read(asset['path'])
            if len(data)!=asset['bytes']: errors.append('Size mismatch: '+asset['path'])
            if hashlib.sha256(data).hexdigest()!=asset['sha256']: errors.append('Hash mismatch: '+asset['path'])
            if 'pdf' in asset['mimeType'] and not data.startswith(b'%PDF-'): errors.append('Invalid PDF: '+asset['path'])
        for name in names:
            if not name.endswith('.html'): continue
            p=Links();p.feed(z.read(name).decode('utf8'))
            for ref in p.refs:
                u=urlsplit(ref)
                if u.scheme or u.netloc or not u.path: continue
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(u.path)))
                if target not in names: errors.append(f'Broken local link: {name} -> {ref}')
        result={'courseId':m['courseId'],'courseName':m.get('courseName'),'nodes':len(m['nodes']),'assets':len(m['assets']),'assetBytes':sum(a['bytes'] for a in m['assets']),'exportIssues':m['issues'],'validationErrors':errors}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if errors: raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip');verify(p.parse_args().zip)

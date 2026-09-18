"""Materialize a verified course snapshot as the Blackboard display hierarchy.
No network, deletion or overwrite of unmanaged/locally modified files.
Usage: python3 sync_directory.py SNAPSHOT DESTINATION
"""
import argparse, hashlib, html, json, os, re, shutil, tempfile
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, unquote

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def name(s):
 s=str(s).replace('/', '／').replace(':','：').replace('\\','＼')
 s=re.sub(r'[\x00-\x1f]', '', s).strip()
 if not s or s in ('.','..'):raise ValueError('Invalid display name')
 if len(s.encode())>240:raise ValueError('Display name too long: '+s)
 return s

def sync(source,destination):
 source=Path(source).resolve(); dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=True)
 m=json.loads((source/'manifest.json').read_text())
 if not m.get('complete') or m.get('issues'):raise ValueError('Refusing incomplete snapshot')
 nodes={n['id']:n for n in m['nodes']};meta=dest/'.blackboard'
 if meta.is_symlink():raise ValueError('Metadata directory is a symlink')
 meta.mkdir(exist_ok=True)
 statepath=meta/'sync-state.json'; previous=json.loads(statepath.read_text()) if statepath.exists() else {}
 if previous and previous['courseId']!=m['courseId']:raise ValueError('Destination belongs to another course')
 old=previous.get('files',{}); paths={}; folders={};planned={};mapping={}
 def folder(id,seen=()):
  if not id or id not in nodes:return Path()
  if id in seen:raise ValueError('Cyclic hierarchy')
  n=nodes[id]
  if n.get('type')!='resource/x-bb-folder':return folder(n.get('parentId'),seen+(id,))/name(n['title'])
  if id not in folders:folders[id]=folder(n.get('parentId'),seen+(id,))/name(n['title'])
  return folders[id]
 def source_file(rel):
  p=(source/rel).resolve()
  if not p.is_relative_to(source):raise ValueError('Unsafe source path')
  return p
 for a in m['assets']:
  p=source_file(a['path'])
  if sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']:raise ValueError('Invalid asset: '+a['path'])
 def plan(rel,data,kind,nodeid):
  k=rel.as_posix()
  if k.casefold() in {x.casefold() for x in planned}:raise ValueError('Filename collision: '+k)
  planned[k]=(data,kind,nodeid)
 for n in m['nodes']:
  if n.get('type')=='resource/x-bb-folder':paths[n['id']]=folder(n['id']);continue
  parent=folder(n.get('parentId')); assets=n.get('files',[])
  if len(assets)==1 and n.get('type')=='resource/x-bb-file':
   original=re.sub(r'^_\d+_\d+-_\d+_\d+-','',Path(assets[0]).name)
   suffix=Path(original).suffix;display=name(n['title'])
   filename=display if suffix and display.lower().endswith(suffix.lower()) else display+suffix
   rel=parent/filename;plan(rel,source_file(assets[0]).read_bytes(),'attachment',n['id']);mapping[assets[0]]=rel
   paths[n['id']]=rel
  else:
   rel=parent/(name(n['title'])+'.html');paths[n['id']]=rel
   for a in assets:
    filename=re.sub(r'^_\d+_\d+-_\d+_\d+-','',Path(a).name)
    assetrel=parent/name(n['title'])/name(filename)
    plan(assetrel,source_file(a).read_bytes(),'attachment',n['id']);mapping[a]=assetrel
 for n in m['nodes']:
  mapping[n['page']]=paths[n['id']]
 mapping['index.html']=Path('.blackboard/index.html')
 if m.get('announcements'):mapping['announcements.html']=Path('Announcements/公告.html')
 def rewrite(text,oldpath,newpath):
  def link(match):
   u=urlsplit(html.unescape(match.group(2)))
   if u.scheme or u.netloc:return match.group(0)
   key=os.path.normpath(str(Path(oldpath).parent/unquote(u.path)))
   target=mapping.get(key)
   if target is None:return match.group(0)
   if target in folders.values():target=Path('.blackboard/index.html')
   return match.group(1)+'="'+html.escape(os.path.relpath(target,newpath.parent),quote=True)+'"'
  return re.sub(r'(href|src)="([^"]*)"',link,text)
 for n in m['nodes']:
  rel=paths[n['id']]
  if n.get('type')=='resource/x-bb-folder':continue
  if rel.as_posix() not in planned:
   plan(rel,rewrite(source_file(n['page']).read_text(),n['page'],rel).encode(),'description',n['id'])
 if m.get('announcements'):
  rel=mapping['announcements.html'];plan(rel,rewrite((source/'announcements.html').read_text(),'announcements.html',rel).encode(),'announcement',None)
 # Validate all paths before making any content changes.
 def checked(rel):
  p=dest/rel
  for q in [p,*p.parents]:
   if q==dest:break
   if q.is_symlink():raise ValueError('Refusing symlink: '+str(q))
  if not p.resolve().is_relative_to(dest):raise ValueError('Unsafe destination')
  return p
 for rel in folders.values():
  p=checked(rel)
  if p.exists() and not p.is_dir():raise ValueError('Folder conflicts with file: '+str(p))
 for rel in planned:
  p=checked(rel)
  if p.exists() and not p.is_file():raise ValueError('File conflicts with directory: '+str(p))
 conflicts=[]
 for rel,(data,_,_) in planned.items():
  p=checked(rel);want=hashlib.sha256(data).hexdigest()
  if p.exists() and sha(p)!=want and (rel not in old or sha(p)!=old[rel]['sha256']):conflicts.append(rel)
 if conflicts:raise ValueError('Local files preserved; resolve conflicts first: '+json.dumps(conflicts,ensure_ascii=False))
 for rel in folders.values():checked(rel).mkdir(parents=True,exist_ok=True)
 written=skipped=0;new={};stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 for rel,(data,kind,nodeid) in planned.items():
  p=checked(rel);digest=hashlib.sha256(data).hexdigest();p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists() and sha(p)==digest:skipped+=1
  else:
   if p.exists():
    backup=meta/'history'/stamp/rel;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,backup)
   fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.sync-')
   try:
    with os.fdopen(fd,'wb') as f:f.write(data)
    os.replace(tmp,p)
   finally:
    if os.path.exists(tmp):os.unlink(tmp)
   written+=1
  assert sha(p)==digest
  new[rel]={'sha256':digest,'kind':kind,'nodeId':nodeid}
 missing=sorted(set(old)-set(new))
 state={'courseId':m['courseId'],'snapshotAt':m.get('finishedAt'),'syncedAt':datetime.now(timezone.utc).isoformat(),'files':new,'previousPathsRetained':missing,'nodes':{k:v.as_posix() for k,v in paths.items()}}
 index='<!doctype html><meta charset="utf-8"><title>blackboard-git 课程目录</title><h1>'+html.escape(m['courseName'])+'</h1><p>源快照：'+html.escape(m.get('finishedAt',''))+'</p><ul>'
 for k in planned:index+='<li><a href="'+html.escape('../'+k,quote=True)+'">'+html.escape(k)+'</a></li>'
 (meta/'index.html').write_text(index+'</ul>')
 (meta/'source-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 temp=statepath.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));os.replace(temp,statepath)
 print(json.dumps({'destination':str(dest),'snapshotAt':state['snapshotAt'],'folders':len(folders),'attachments':sum(v['kind']=='attachment' for v in new.values()),'written':written,'unchanged':skipped,'oldPathsRetained':missing},ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('source');a.add_argument('destination');x=a.parse_args();sync(x.source,x.destination)

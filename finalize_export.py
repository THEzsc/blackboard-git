"""Add a saved Blackboard announcements snapshot and explicit online-only labels."""
from pathlib import Path
from html.parser import HTMLParser
from html import escape
from urllib.parse import urljoin,urlsplit
import json,zipfile,argparse
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class Node:
 def __init__(self,tag='',attrs=()): self.tag=tag;self.attrs=dict(attrs);self.children=[]
class Parser(HTMLParser):
 def __init__(self): super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
 def handle_starttag(self,t,a):
  n=Node(t,a);self.stack[-1].children.append(n)
  if t not in VOID:self.stack.append(n)
 def handle_endtag(self,t):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==t:self.stack=self.stack[:i];break
 def handle_data(self,d):self.stack[-1].children.append(d)
def walk(n):
 if isinstance(n,Node):
  yield n
  for c in n.children:yield from walk(c)
def clean(n):
 if isinstance(n,str):return escape(n)
 if n.tag in {'script','style','form','input','button','iframe','embed','object','svg','meta','link'}:return ''
 body=''.join(clean(c) for c in n.children)
 if n.tag=='a':
  u=urljoin('https://learn.intl.zju.edu.cn',n.attrs.get('href',''))
  return '<a rel="noreferrer" href="'+escape(u,quote=True)+'">'+body+'</a>' if urlsplit(u).scheme in ('http','https') else body
 if n.tag in {'p','div','span','h3','ul','ol','li','strong','b','em','i','br','table','tr','td','th','tbody'}:
  return '<'+n.tag+'>'+body+('' if n.tag=='br' else '</'+n.tag+'>')
 return body

def finalize(folder,source,output):
 p=Path(folder);m=json.loads((p/'manifest.json').read_text());parser=Parser();parser.feed(Path(source).read_text())
 target=next((n for n in walk(parser.root) if n.attrs.get('id')=='announcementList'),None)
 if target is None:raise ValueError('Missing announcement list; cannot label snapshot successful')
 entries=[n for n in target.children if isinstance(n,Node) and n.tag=='li']
 index=(p/'index.html').read_text();head=index.split('<body>',1)[0]
 announcement=head+'<body><a href="index.html">← 课程目录</a><h1>课程公告</h1><p>当前可见公告页面快照</p><article>'+clean(target)+'</article></body></html>'
 (p/'announcements.html').write_text(announcement)
 m['announcements']={'count':len(entries),'page':'announcements.html','scope':'visible-announcement-page'}
 m['onlineOnly']=[]
 for n in m['nodes']:
  if not n.get('type') or 'assignment' in n.get('type',''):
   n['offlineStatus']='description-only';m['onlineOnly'].append(n['id'])
   page=p/n['page'];s=page.read_text();s=s.replace('<article>','<p><strong>此处仅归档说明；填写问卷或提交作业请回原站。</strong></p><article>',1)
   page.write_text(s)
  if n.get('type')!='resource/x-bb-folder' and n.get('parentId'):
   page=p/n['page'];s=page.read_text();old=n['online'];n['online']=old.replace('content_id='+n['id'],'content_id='+n['parentId']);page.write_text(s.replace(escape(old,quote=True),escape(n['online'],quote=True)))
 index=index.replace('<article>','<p><a href="announcements.html">课程公告（'+str(len(entries))+'）</a> · '+str(len(m['onlineOnly']))+' 项问卷/作业仅归档说明</p><article>',1)
 (p/'index.html').write_text(index)
 (p/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  for f in sorted(p.rglob('*')):
   if f.is_file():z.write(f,f.relative_to(p))
 print(json.dumps({'output':str(output),'announcements':len(entries),'onlineOnly':len(m['onlineOnly'])},ensure_ascii=False))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('folder');a.add_argument('source');a.add_argument('output');x=a.parse_args();finalize(x.folder,x.source,x.output)

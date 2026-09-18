/* Learn Course Mirror 0.1 — no dependencies, no external server.
   Run in the console of your logged-in learn.intl.zju.edu.cn course page.
   Only same-origin GET requests. No submissions, enrollment or credential export.
   Downloads one ZIP containing HTML pages, original files and a manifest. */
(async function () {
  'use strict';
  const origin = 'https://learn.intl.zju.edu.cn';
  if (location.origin !== origin) throw Error('请在 Learn 课程页面运行');
  const courseId = new URL(location.href).searchParams.get('course_id');
  if (!/^_\d+_\d+$/.test(courseId || '')) throw Error('页面 URL 中没有有效 course_id');
  if (window.__courseMirrorRunning) throw Error('已有导出任务正在运行');
  window.__courseMirrorRunning = true;
  const base = `${origin}/learn/api/public/v1/courses/${courseId}`;
  const files = [], nodes = [], issues = [], assets = new Map();
  const maxBytes = 300 * 1024 * 1024;
  let bytes = 0, requests = 0;
  const enc = new TextEncoder();
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe = s => String(s || 'file').replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').replace(/^\.+/, '_').slice(0, 120);
  const typeName = h => ({'resource/x-bb-folder':'目录','resource/x-bb-file':'文件','resource/x-bb-document':'页面','resource/x-bb-assignment':'作业说明'}[h] || '说明 / 在线资源');
  const uiLink = id => `${origin}/webapps/blackboard/content/listContent.jsp?course_id=${courseId}&content_id=${encodeURIComponent(id)}`;
  const note = (stage, id, message) => issues.push({stage, id, message: String(message).slice(0,400)});
  const log = s => { console.log('[Course Mirror]', s); status.textContent = s; };
  const status = document.createElement('div');
  status.style.cssText = 'position:fixed;bottom:20px;right:20px;max-width:520px;background:#142c38;color:white;padding:20px;border-radius:12px;z-index:2147483647;font:15px sans-serif;white-space:pre-wrap';
  document.body.append(status);
  function add(path, data) {
    if (typeof data === 'string') data = enc.encode(data);
    bytes += data.length;
    if (bytes > maxBytes + 10*1024*1024) throw Error('超过导出内存预算');
    files.push({path, data});
  }
  async function request(url) {
    const u = new URL(url, origin);
    if (u.origin !== origin) throw Error('外部资源仅保留链接');
    if (++requests > 5000) throw Error('请求上限已触发，导出不完整');
    for (let attempt=0; attempt<3; attempt++) {
      const r = await fetch(u.href, {credentials:'same-origin', mode:'same-origin', signal:AbortSignal.timeout(45000)});
      if ((r.status===429 || r.status>=500) && attempt<2) {
        const delay = Math.min(15, Math.max(1, Number(r.headers.get('Retry-After')) || 2**attempt));
        await new Promise(ok=>setTimeout(ok,delay*1000)); continue;
      }
      if (!r.ok) throw Error(`HTTP ${r.status}`);
      if (/\/(login|cas)\/|authValidate|customLogin/.test(new URL(r.url).pathname)) throw Error('登录态失效');
      return r;
    }
  }
  async function json(url) {
    const r=await request(url);
    if (!(r.headers.get('content-type') || '').includes('json')) throw Error('API 未返回 JSON，可能需要登录');
    return r.json();
  }
  async function list(url) {
    const result=[], pages=new Set();
    while (url) {
      const u = new URL(url, origin);
      if (u.origin!==origin || !u.pathname.startsWith(new URL(base).pathname+'/')) throw Error('分页超出当前课程');
      if (pages.has(u.href)) throw Error('分页循环');
      pages.add(u.href);
      const d=await json(u.href);
      if (!Array.isArray(d.results)) throw Error('列表缺少 results');
      result.push(...d.results);
      url=d.paging?.nextPage;
    }
    return result;
  }
  function refs(html) {
    const doc = new DOMParser().parseFromString(html || '', 'text/html');
    return [...doc.querySelectorAll('a[href],img[src],embed[src],object[data],iframe[src],source[src]')].map(el=>({el, raw:el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data')}));
  }
  async function asset(url, suggested, key, depth=0) {
    const u=new URL(url, origin);
    if (u.origin!==origin) throw Error('外部资源仅保留链接');
    const cacheKey=u.href;
    if (assets.has(cacheKey)) return assets.get(cacheKey);
    if (depth>3) throw Error('查看器解析深度上限');
    const r=await request(u.href);
    const type=(r.headers.get('content-type') || '').toLowerCase();
    if (type.includes('text/html')) {
      const html=await r.text();
      const candidates=refs(html).map(x=>new URL(x.raw,r.url)).filter(x=>x.origin===origin && x.pathname.startsWith('/bbcswebdav/') && x.href!==u.href);
      if (candidates.length!==1) throw Error(`返回 HTML，无法唯一识别文件（${candidates.length} 个候选）`);
      const path=await asset(candidates[0].href,suggested,key,depth+1); assets.set(cacheKey,path); return path;
    }
    const declared=Number(r.headers.get('content-length') || 0);
    if (declared && bytes+declared>maxBytes) { await r.body?.cancel(); throw Error('文件超过本次 300 MB 预算'); }
    const chunks=[]; let size=0;
    const reader=r.body.getReader();
    while (true) {
      const {done,value}=await reader.read(); if(done) break;
      size+=value.length;
      if(bytes+size>maxBytes) { await reader.cancel(); throw Error('达到本次 300 MB 预算'); }
      chunks.push(value);
    }
    if(!size) throw Error('空文件');
    const data=new Uint8Array(size); let offset=0;
    for(const c of chunks){data.set(c,offset);offset+=c.length;}
    if(/^\s*(?:<!doctype html|<html)/i.test(new TextDecoder().decode(data.slice(0,150)))) throw Error('检测到伪装为文件的 HTML');
    let name=suggested || 'file';
    const cd=r.headers.get('content-disposition') || '';
    const star=cd.match(/filename\*=UTF-8''([^;]+)/i), plain=cd.match(/filename="([^"]+)"/i);
    try { if(star) name=decodeURIComponent(star[1]); else if(plain) name=plain[1]; } catch {}
    if(!/\.[a-z0-9]{1,8}$/i.test(name)) {
      const ext=type.includes('pdf')?'.pdf':type.includes('png')?'.png':type.includes('jpeg')?'.jpg':type.includes('presentationml')?'.pptx':type.includes('wordprocessingml')?'.docx':type.includes('zip')?'.zip':'';
      name+=ext;
    }
    if(type.includes('pdf') && new TextDecoder().decode(data.slice(0,5))!=='%PDF-') throw Error('PDF 文件头校验失败');
    const path=`files/${safe(key)}-${safe(name)}`;
    if(files.some(f=>f.path===path)) throw Error('文件名冲突');
    add(path,data); assets.set(cacheKey,path);
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('');
    manifest.assets.push({path,bytes:size,mimeType:type,sha256:hash});
    return path;
  }
  const css='body{max-width:1080px;margin:48px auto;padding:0 24px;font:16px/1.7 system-ui;color:#183341;background:#f6f8fa}a{color:#126b81}article{background:white;border:1px solid #dde4e8;border-radius:12px;padding:24px;margin:20px 0}img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}small{color:#667}';
  const page=(title,body)=>`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${esc(title)}</title><style>${css}</style><body>${body}</body></html>`;
  function clean(html, map) {
    const doc=new DOMParser().parseFromString(html || '', 'text/html');
    const allowed=new Set('p div span strong b em i u s h1 h2 h3 h4 h5 h6 ul ol li a img table thead tbody tr th td blockquote pre code br hr sub sup dl dt dd'.split(' '));
    for(const el of [...doc.body.querySelectorAll('*')]) {
      if(!allowed.has(el.localName)) { if(['script','style','iframe','object','embed','form','input','button','link','meta','svg','math'].includes(el.localName)) el.remove(); else el.replaceWith(...el.childNodes); continue; }
      const raw=el.getAttribute('href') || el.getAttribute('src');
      const alt=el.getAttribute('alt');
      for(const at of [...el.attributes]) el.removeAttribute(at.name);
      if(alt) el.setAttribute('alt',alt);
      if(raw) {
        let u; try{u=new URL(raw,origin);}catch{continue;}
        if(!['http:','https:'].includes(u.protocol)) continue;
        const local=map.get(u.href);
        if(el.localName==='img') { if(local) el.setAttribute('src','../'+local); else el.replaceWith(doc.createTextNode('[图片未下载]')); }
        else if(el.localName==='a') { el.setAttribute('href',local?'../'+local:u.href); el.setAttribute('rel','noreferrer'); }
      }
    }
    return doc.body.innerHTML;
  }
  const manifest={version:1,courseId,scope:'course-content-tree',startedAt:new Date().toISOString(),assets:[],nodes:[],issues,complete:false,limitations:['外部工具、测验作答、提交记录及讨论不在内容树镜像范围；仅保留可见入口。','本版每次重新导出，不提供增量同步。']};
  try {
    log('正在读取课程信息…');
    const course=await json(base); manifest.courseName=course.name || course.displayName || courseId;
    const queue=await list(base+'/contents?limit=200'), seen=new Set();
    while(queue.length) {
      const n=queue.shift(); if(seen.has(n.id)) continue;
      if(!/^_\d+_\d+$/.test(n.id || '')) {note('node','unknown','无效内容 ID');continue;}
      seen.add(n.id); nodes.push(n);
      if(nodes.length>3000) throw Error('节点保护上限，导出不完整');
      log(`扫描目录：${nodes.length} 个条目，待扫描 ${queue.length}`);
      if(n.hasChildren) {
        try{queue.push(...await list(`${base}/contents/${n.id}/children?limit=200`));}
        catch(e){note('children',n.id,e.message);}
      }
    }
    for (const n of nodes) {
      log(`下载与整理 ${nodes.indexOf(n)+1}/${nodes.length}：${n.title}`);
      const record={id:n.id,parentId:n.parentId,title:n.title,position:n.position,type:n.contentHandler?.id,created:n.created,modified:n.modified,files:[],page:`pages/${safe(n.id)}.html`,online:uiLink(n.contentHandler?.id==='resource/x-bb-folder' ? n.id : (n.parentId || n.id))};
      const map=new Map(); let attachments=[];
      const handler=n.contentHandler?.id || '';
      record.offlineStatus=(!handler || /assignment|test|blti/.test(handler))?'description-only':'archived';
      if(/document|file|assignment/.test(handler)) {
        try{attachments=await list(`${base}/contents/${n.id}/attachments?limit=200`);}
        catch(e){note('attachments',n.id,e.message);}
      }
      for(const a of attachments) {
        try{const p=await asset(`${base}/contents/${n.id}/attachments/${encodeURIComponent(a.id)}/download`,a.fileName,`${n.id}-${a.id}`);record.files.push(p);}
        catch(e){note('download',`${n.id}/${a.id}`,e.message);}
      }
      let source=n.body || '';
      // File handlers may not expose attachments on older Original deployments.
      if(handler==='resource/x-bb-file' && !record.files.length) {
        try {
          const r=await request(uiLink(n.parentId || n.id));
          const doc=new DOMParser().parseFromString(await r.text(),'text/html');
          const item=doc.getElementById('contentListItem:'+n.id) || doc.getElementById('contentListItem:'+n.id.replace(/_/g,''));
          let links=item ? [...item.querySelectorAll('a[href]')] : [];
          if(!links.length) links=[...doc.querySelectorAll('a[href]')].filter(a=>a.getAttribute('href').includes(`pid-${n.id.split('_')[1]}-`));
          const target=links.map(a=>new URL(a.getAttribute('href'),r.url)).find(u=>u.origin===origin && u.pathname.startsWith('/bbcswebdav/'));
          if(!target) throw Error('未找到该文件的可见下载链接');
          record.files.push(await asset(target.href,n.contentHandler?.file?.fileName || n.title,n.id));
        } catch(e){note('file-fallback',n.id,e.message);}
      }
      let ri=0;
      for(const ref of refs(source)) {
        let u;try{u=new URL(ref.raw,origin);}catch{continue;}
        if(u.origin===origin && u.pathname.startsWith('/bbcswebdav/')) {
          try{const p=await asset(u.href,ref.el.textContent.trim() || 'embedded',`${n.id}-inline-${++ri}`);map.set(u.href,p);if(!record.files.includes(p))record.files.push(p);}
          catch(e){note('inline',n.id,e.message);}
        }
      }
      const external=n.contentHandler?.url;
      const children=nodes.filter(c=>c.parentId===n.id).sort((a,b)=>(a.position||0)-(b.position||0));
      add(record.page,page(n.title,`<a href="../index.html">← 课程目录</a><h1>${esc(n.title)}</h1><small>${esc(typeName(handler))} · ${esc(n.modified || n.created || '')}</small>${record.offlineStatus==='description-only'?'<p>此处仅归档说明；填写问卷或提交作业请回原站。</p>':''}<article>${clean(source,map)}${external && /^https?:/.test(external)?`<p><a rel="noreferrer" href="${esc(external)}">在原站打开外部资源</a></p>`:''}<ul>${record.files.map(p=>`<li><a href="../${esc(p)}">${esc(p.split('/').pop())}</a></li>`).join('')}</ul><ul>${children.map(c=>`<li><a href="${safe(c.id)}.html">${esc(c.title)}</a></li>`).join('')}</ul></article><p><a rel="noreferrer" href="${esc(record.online)}">返回 Blackboard 查看</a></p>`));
      manifest.nodes.push(record);
    }
    manifest.complete=!issues.length;
  } catch(e) { note('fatal',courseId,e.message); }
  try {
    manifest.finishedAt=new Date().toISOString();
    add('manifest.json',JSON.stringify(manifest,null,2));
    const indexNodes=new Map(manifest.nodes.map(n=>[n.id,n]));
    function tree(parent,visited=new Set()) {
      return '<ul>'+manifest.nodes.filter(n=>parent ? n.parentId===parent : !indexNodes.has(n.parentId)).sort((a,b)=>(a.position||0)-(b.position||0)).map(n=>{
        if(visited.has(n.id))return '';const next=new Set(visited);next.add(n.id);
        return `<li><a href="${esc(n.page)}">${esc(n.title)}</a> <small>${n.files.length?`${n.files.length} 文件`:esc(typeName(n.type))}</small>${tree(n.id,next)}</li>`;
      }).join('')+'</ul>';
    }
    add('index.html',page(manifest.courseName || courseId,`<h1>${esc(manifest.courseName || courseId)}</h1><p>课程资料离线镜像 · ${esc(manifest.finishedAt)}</p><p>${manifest.nodes.length} 个条目 · ${manifest.assets.length} 个文件 · ${(bytes/1048576).toFixed(1)} MB</p><p>${manifest.complete?'内容树扫描与已发现资源下载完成':'部分导出：请查看下方未完成项'}</p><article>${tree(null)}</article><article><h2>范围与未完成项</h2>${manifest.limitations.map(s=>`<p>${esc(s)}</p>`).join('')}<ul>${issues.map(i=>`<li>${esc(i.stage)} / ${esc(i.id)}：${esc(i.message)}</li>`).join('')}</ul></article><a href="manifest.json">导出清单</a>`));
    // ZIP store format: UTF-8 names + CRC-32, no third-party ZIP code/CDN.
    const table=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let j=0;j<8;j++)c=c&1?0xedb88320^(c>>>1):c>>>1;table[n]=c;}
    const crc=d=>{let c=0xffffffff;for(const b of d)c=table[(c^b)&255]^(c>>>8);return(c^0xffffffff)>>>0;};
    const parts=[],central=[];let off=0,centralSize=0;
    for(const f of files){
      const name=enc.encode(f.path),sum=crc(f.data),h=new Uint8Array(30),v=new DataView(h.buffer);
      v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint32(14,sum,true);v.setUint32(18,f.data.length,true);v.setUint32(22,f.data.length,true);v.setUint16(26,name.length,true);
      parts.push(h,name,f.data);
      const ch=new Uint8Array(46),cv=new DataView(ch.buffer);cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint32(16,sum,true);cv.setUint32(20,f.data.length,true);cv.setUint32(24,f.data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,off,true);
      central.push(ch,name);centralSize+=46+name.length;off+=30+name.length+f.data.length;
    }
    const end=new Uint8Array(22),ev=new DataView(end.buffer);ev.setUint32(0,0x06054b50,true);ev.setUint16(8,files.length,true);ev.setUint16(10,files.length,true);ev.setUint32(12,centralSize,true);ev.setUint32(16,off,true);
    const blob=new Blob([...parts,...central,end],{type:'application/zip'}),url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=`Learn-${courseId}-${Date.now()}.zip`;a.textContent='下载课程镜像 ZIP';a.style.cssText='display:block;color:#9ce8ff;margin-top:12px';
    log(`导出结束：${manifest.nodes.length} 条目，${manifest.assets.length} 文件，${issues.length} 未完成项。`);status.append(a);a.click();
    console.log('MIRROR_RESULT',JSON.stringify({courseId,nodes:manifest.nodes.length,assets:manifest.assets.length,issues}));
    // Keep the object URL alive for the explicit retry-download link until this page closes.
  } finally {window.__courseMirrorRunning=false;}
})();

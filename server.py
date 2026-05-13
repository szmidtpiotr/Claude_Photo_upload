#!/usr/bin/env python3
"""
Tiny upload server for screenshots from iPhone (or any browser).
Saves to ~/screenshots/ and returns the absolute path for pasting into Claude.
"""

import http.server
import socketserver
import cgi
import os
import re
import datetime
import json
import html
from pathlib import Path

PORT = 37701
SAVE_DIR = Path.home() / "screenshots"
SAVE_DIR.mkdir(exist_ok=True)

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Screenshot">
<title>Screenshot Upload</title>
<style>
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{margin:0;font:16px -apple-system,system-ui,sans-serif;background:#0a0e14;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
  .card{background:#141821;border-radius:24px;padding:32px;max-width:420px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.4)}
  h1{margin:0 0 8px;font-size:24px;font-weight:600}
  p.sub{margin:0 0 24px;color:#7d8590;font-size:14px}
  .buttons{display:flex;gap:12px;margin-bottom:16px}
  .btn{flex:1;background:linear-gradient(135deg,#4dc9f6,#7dd8f8);color:#0a0e14;text-align:center;padding:16px;border-radius:16px;font-weight:600;font-size:16px;cursor:pointer;border:none;transition:transform .15s}
  .btn:active{transform:scale(.97)}
  .btn-secondary{background:#2a3140;color:#e0e0e0}
  label.btn{display:block;padding:24px;font-size:18px}
  input[type=file]{display:none}
  .preview{margin-top:16px;padding:16px;background:#1f242e;border-radius:12px;display:none;text-align:center}
  .preview.show{display:block}
  .preview img{max-width:100%;max-height:300px;border-radius:8px;margin-bottom:12px}
  .preview-actions{display:flex;gap:8px}
  .preview-actions button{flex:1;padding:12px;border:none;border-radius:8px;cursor:pointer;font-size:14px;transition:transform .15s}
  .preview-actions button:active{transform:scale(.97)}
  .send-btn{background:linear-gradient(135deg,#4dc9f6,#7dd8f8);color:#0a0e14;font-weight:600}
  .cancel-btn{background:#2a3140;color:#e0e0e0}
  .result{margin-top:24px;padding:16px;background:#1f242e;border-radius:12px;display:none;word-break:break-all}
  .result.show{display:block}
  .result code{display:block;color:#7dd8f8;margin:8px 0;font-size:13px}
  .copy-btn{background:#2a3140;color:#e0e0e0;border:none;padding:10px 16px;border-radius:8px;font-size:14px;cursor:pointer;margin-top:8px;width:100%}
  .copy-btn:active{background:#3a4150}
  .copied{color:#4caf50}
  .progress{margin-top:16px;height:4px;background:#2a3140;border-radius:2px;overflow:hidden;display:none}
  .progress.show{display:block}
  .progress-bar{height:100%;background:#4dc9f6;width:0%;transition:width .2s}
  .recent{margin-top:24px}
  .recent h3{margin:0 0 12px;font-size:14px;color:#7d8590;font-weight:500}
  .recent-item{display:flex;align-items:center;gap:10px;padding:8px;background:#1f242e;border-radius:8px;margin-bottom:6px;cursor:pointer}
  .recent-item:active{background:#2a3140}
  .recent-item img{width:64px;height:48px;object-fit:cover;border-radius:6px;flex-shrink:0;background:#0a0e14}
  .recent-item span{font-size:11px;color:#b0b0b0;word-break:break-all;overflow:hidden}
  .result-thumb{display:none;max-width:100%;max-height:200px;border-radius:8px;margin-bottom:12px;width:100%;object-fit:contain}
  .result-thumb.show{display:block}
</style>
</head>
<body>
<div class="card">
  <h1>📸 Screenshot</h1>
  <p class="sub">Upload to <code style="color:#7dd8f8">~/screenshots/</code></p>

  <div class="buttons">
    <button class="btn" id="paste-btn">Paste (Ctrl+V)</button>
    <label class="btn btn-secondary" for="file-input" style="margin:0;padding:16px">Choose File</label>
  </div>
  <p style="font-size:12px;color:#7d8590;margin:8px 0 0">On iOS: Use long-press Paste instead of button</p>
  <input type="file" id="file-input" accept="image/*" multiple>

  <div class="preview" id="preview">
    <img id="preview-img" src="" alt="Preview">
    <div class="preview-actions">
      <button class="send-btn" id="send-btn">Send Photo</button>
      <button class="cancel-btn" id="cancel-btn">Cancel</button>
    </div>
  </div>

  <div class="progress" id="progress"><div class="progress-bar" id="bar"></div></div>

  <div class="result" id="result">
    <img class="result-thumb" id="result-thumb" src="" alt="Preview">
    <div>Saved at (copied to clipboard!):</div>
    <code id="path"></code>
    <button class="copy-btn" id="copy">Copy Again</button>
  </div>

  <div class="recent" id="recent-section" style="display:none">
    <h3>Recent uploads</h3>
    <div id="recent-list"></div>
  </div>

  <div id="ios-install" style="display:none;margin-top:20px;text-align:center">
    <a href="/shortcut" style="display:inline-block;background:linear-gradient(135deg,#4dc9f6,#7dd8f8);color:#0a0e14;padding:14px 24px;border-radius:14px;font-weight:600;font-size:15px;text-decoration:none">
      📲 Install iOS Shortcut
    </a>
    <p style="font-size:12px;color:#7d8590;margin:8px 0 0">
      Adds "Upload to Claude" to your Share Sheet
    </p>
  </div>
</div>

<script>
function copyToClipboardFallback(text){const textarea=document.createElement('textarea');textarea.value=text;document.body.appendChild(textarea);textarea.select();document.execCommand('copy');document.body.removeChild(textarea)}
function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
const pasteBtn=document.getElementById('paste-btn'),input=document.getElementById('file-input'),result=document.getElementById('result'),pathEl=document.getElementById('path'),resultThumb=document.getElementById('result-thumb'),copyBtn=document.getElementById('copy'),progress=document.getElementById('progress'),bar=document.getElementById('bar'),preview=document.getElementById('preview'),previewImg=document.getElementById('preview-img'),sendBtn=document.getElementById('send-btn'),cancelBtn=document.getElementById('cancel-btn');
let pendingFile=null;
function showResult(path){
  const name=path.split('/').pop();
  resultThumb.src='/files/'+encodeURIComponent(name);
  resultThumb.classList.add('show');
  pathEl.textContent=path;
  result.classList.add('show');
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(path).catch(()=>{copyToClipboardFallback(path)})}else{copyToClipboardFallback(path)}
}

pasteBtn.addEventListener('click',async()=>{
  try{
    const items=await navigator.clipboard.read();
    for(const item of items){
      if(item.types.includes('image/png')){
        const blob=await item.getType('image/png');
        displayPreview(blob,'png');
        return;
      }else if(item.types.includes('image/jpeg')){
        const blob=await item.getType('image/jpeg');
        displayPreview(blob,'jpg');
        return;
      }
    }
    alert('No image found in clipboard');
  }catch(err){
    alert('Unable to access clipboard: '+err.message);
  }
});

document.addEventListener('paste',e=>{
  const items=e.clipboardData.items;
  for(const item of items){
    if(item.kind==='file'&&item.type.startsWith('image/')){
      e.preventDefault();
      const file=item.getAsFile();
      displayPreview(file,item.type.split('/')[1],true);
      return;
    }
  }
});

function displayPreview(blob,ext,autoSend){
  const reader=new FileReader();
  reader.onload=e=>{
    previewImg.src=e.target.result;
    preview.classList.add('show');
    if(autoSend)setTimeout(()=>{sendBtn.click()},300);
  };
  reader.readAsDataURL(blob);
  const ext_map={'png':'.png','jpeg':'.jpg','jpg':'.jpg'};
  pendingFile={blob,ext:ext_map[ext]||'.png'};
}

cancelBtn.addEventListener('click',()=>{
  preview.classList.remove('show');
  pendingFile=null;
});

sendBtn.addEventListener('click',async()=>{
  if(!pendingFile)return;
  const fd=new FormData();
  fd.append('file',new File([pendingFile.blob],'screenshot'+pendingFile.ext,{type:pendingFile.blob.type}));
  progress.classList.add('show');bar.style.width='10%';
  preview.classList.remove('show');
  try{
    const xhr=new XMLHttpRequest();
    xhr.upload.onprogress=ev=>{if(ev.lengthComputable)bar.style.width=(ev.loaded/ev.total*90+10)+'%'};
    xhr.onload=()=>{
      bar.style.width='100%';
      const data=JSON.parse(xhr.responseText);
      showResult(data.path);
      pendingFile=null;
      setTimeout(()=>{progress.classList.remove('show');bar.style.width='0%'},500);
      loadRecent();
    };
    xhr.open('POST','/upload');xhr.send(fd);
  }catch(err){alert('Upload failed: '+err.message)}
});

input.addEventListener('change',async e=>{
  const files=e.target.files;if(!files.length)return;
  for(const f of files){
    const fd=new FormData();fd.append('file',f);
    progress.classList.add('show');bar.style.width='10%';
    try{
      const xhr=new XMLHttpRequest();
      xhr.upload.onprogress=ev=>{if(ev.lengthComputable)bar.style.width=(ev.loaded/ev.total*90+10)+'%'};
      xhr.onload=()=>{
        bar.style.width='100%';
        const data=JSON.parse(xhr.responseText);
        showResult(data.path);
        setTimeout(()=>{progress.classList.remove('show');bar.style.width='0%'},500);
        loadRecent();
      };
      xhr.open('POST','/upload');xhr.send(fd);
    }catch(err){alert('Upload failed: '+err.message)}
  }
});

copyBtn.addEventListener('click',async()=>{
  try{
    await navigator.clipboard.writeText(pathEl.textContent);
    copyBtn.textContent='Copied!';copyBtn.classList.add('copied');
    setTimeout(()=>{copyBtn.textContent='Copy Path';copyBtn.classList.remove('copied')},1500);
  }catch(e){
    const r=document.createRange();r.selectNode(pathEl);
    window.getSelection().removeAllRanges();window.getSelection().addRange(r);
    document.execCommand('copy');
  }
});

async function loadRecent(){
  try{
    const r=await fetch('/recent');const d=await r.json();
    if(!d.files.length)return;
    document.getElementById('recent-section').style.display='block';
    const list=document.getElementById('recent-list');
    list.innerHTML=d.files.map(f=>{
      const name=f.split('/').pop();
      return `<div class="recent-item" data-path="${escHtml(f)}"><img src="/files/${encodeURIComponent(name)}" loading="lazy" onerror="this.style.display='none'"><span>${escHtml(name)}</span></div>`;
    }).join('');
    list.querySelectorAll('.recent-item').forEach(el=>{
      el.addEventListener('click',()=>{
        const p=el.dataset.path;
        if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(p).catch(()=>copyToClipboardFallback(p))}else{copyToClipboardFallback(p)}
      });
    });
  }catch(e){}
}
if(/iPhone|iPad|iPod/.test(navigator.userAgent))document.getElementById('ios-install').style.display='block';
loadRecent();
</script>
</body>
</html>
"""

def _generate_shortcut(upload_url: str) -> bytes:
    """Generate a binary plist iOS Shortcut that POSTs an image to upload_url."""
    import plistlib

    URL_UUID  = "4A3F2E1D-0B9C-8D7E-6F5A-4B3C2D1E0F9A"
    DICT_UUID = "6C5D4E3F-2D1E-0F9A-8B7C-6D5E4F3A2B1C"

    def token_attachment(output_name, output_uuid):
        return {
            "Value": {
                "attachmentsByRange": {
                    "{0, 1}": {
                        "OutputName": output_name,
                        "OutputUUID": output_uuid,
                        "Type":       "ActionOutput",
                    }
                },
                "string": "￼",
            },
            "WFSerializationType": "WFTextTokenString",
        }

    shortcut = {
        "WFWorkflowActions": [
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.geturlcontents",
                "WFWorkflowActionParameters": {
                    "WFHTTPMethod":   "POST",
                    "WFURL":          upload_url,
                    "WFHTTPBodyType": "File",
                    "WFHTTPBody": {
                        "Value":               {"Type": "ExtensionInput"},
                        "WFSerializationType": "WFTextTokenAttachment",
                    },
                    "UUID": URL_UUID,
                },
            },
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.getdictionaryvalue",
                "WFWorkflowActionParameters": {
                    "WFDictionaryKey": "path",
                    "WFInput":         token_attachment("Contents of URL", URL_UUID),
                    "UUID":            DICT_UUID,
                },
            },
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.setclipboard",
                "WFWorkflowActionParameters": {
                    "WFInput": token_attachment("Dictionary Value", DICT_UUID),
                },
            },
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
                "WFWorkflowActionParameters": {
                    "WFNotificationActionTitle":      "✓ Uploaded to Claude",
                    "WFNotificationActionBody":       token_attachment("Dictionary Value", DICT_UUID),
                    "WFNotificationActionPlaySound":  False,
                },
            },
        ],
        "WFWorkflowClientVersion": "1226.0.1",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,
            "WFWorkflowIconStartColor":  4292093695,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": [
            "WFImageContentItem",
            "WFPhotoMediaContentItem",
        ],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowName":   "Upload to Claude",
        "WFWorkflowTypes":  ["ShareSheet"],
    }

    return plistlib.dumps(shortcut, fmt=plistlib.FMT_BINARY)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode())
        elif self.path == "/recent":
            files = sorted(SAVE_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            data = {"files": [str(f.absolute()) for f in files]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path.startswith("/files/"):
            name = os.path.basename(self.path[7:])
            filepath = SAVE_DIR / name
            if filepath.exists() and filepath.parent.resolve() == SAVE_DIR.resolve():
                ext = os.path.splitext(name)[1].lower()
                mime = {".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".gif": "image/gif",
                        ".webp": "image/webp"}.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.end_headers()
                with open(filepath, "rb") as fp:
                    self.wfile.write(fp.read())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/shortcut":
            host   = self.headers.get("Host", "claude-photo.studio-colorbox.com")
            scheme = "http" if host.startswith("localhost") else "https"
            data   = _generate_shortcut(f"{scheme}://{host}/upload-raw")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-apple-shortcut")
            self.send_header("Content-Disposition", 'attachment; filename="UploadToClaude.shortcut"')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/upload":
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type", ""))
            if ctype != "multipart/form-data":
                self.send_response(400)
                self.end_headers()
                return
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]},
            )
            f = form["file"]

            # Optional subfolder: only allow safe relative paths, no traversal
            save_dir = SAVE_DIR
            if "folder" in form:
                raw = form["folder"].value.strip()
                if raw and re.match(r'^[\w\-/]+$', raw) and ".." not in raw:
                    save_dir = SAVE_DIR / raw
                    save_dir.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(f.filename)[1] or ".png"
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out = save_dir / f"screenshot_{ts}{ext}"
            with open(out, "wb") as fp:
                fp.write(f.file.read())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"path": str(out.absolute())}).encode())
        elif self.path.startswith("/upload-raw"):
            # Raw binary upload from iOS Shortcuts (body = image bytes, Content-Type = MIME type)
            from urllib.parse import urlparse, parse_qs
            query    = parse_qs(urlparse(self.path).query)
            ext_hint = query.get("ext", [""])[0]
            ct       = self.headers.get("Content-Type", "image/png")
            ext_map  = {"image/png": ".png", "image/jpeg": ".jpg", "image/heic": ".heic",
                        "image/gif": ".gif", "image/webp": ".webp"}
            ext      = ext_hint or ext_map.get(ct.split(";")[0].strip(), ".png")

            # Optional subfolder from query param
            raw_folder = query.get("folder", [""])[0].strip()
            save_dir   = SAVE_DIR
            if raw_folder and re.match(r'^[\w\-/]+$', raw_folder) and ".." not in raw_folder:
                save_dir = SAVE_DIR / raw_folder
                save_dir.mkdir(parents=True, exist_ok=True)

            length = int(self.headers.get("Content-Length", 0))
            data   = self.rfile.read(length)
            ts     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out    = save_dir / f"screenshot_{ts}{ext}"
            out.write_bytes(data)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"path": str(out.absolute())}).encode())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        print(f"Screenshot upload server on :{PORT} → {SAVE_DIR}")
        httpd.serve_forever()

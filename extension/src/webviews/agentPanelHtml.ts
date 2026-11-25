export function getAgentPanelHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy"
  content="default-src 'none'; img-src data: https:; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#15151f;
  --bg2:#1e1e2a;
  --bg3:#262636;
  --border:#2e2e42;
  --fg:#e8e8f0;
  --fg-dim:#8a8aa0;
  --input-bg:#1e1e2a;
  --input-border:#3a3a52;
  --btn:#7c3aed;
  --btn-fg:#fff;
  --btn2:#2e2e42;
  --btn2-fg:#c8c8e0;
  --accent:#c084fc;
  --accent2:#f0247a;
  --green:#4ade80;
  --red:#f87171;
  --amber:#fbbf24;
  --code-bg:#0f0f17;
  --user-bg:#2a1f3d;
  --user-border:#4a3070;
  --r:10px;
  --mono:'Cascadia Code','JetBrains Mono',Consolas,monospace;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--fg);
  font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;line-height:1.55}
#shell{display:flex;flex-direction:column;height:100vh}

/* ── top bar ── */
#topbar{display:flex;align-items:center;gap:8px;padding:8px 12px;
  background:linear-gradient(90deg,#1a0a24 0%,#2a1040 100%);
  border-bottom:1px solid var(--border);flex-shrink:0}
#dot{width:8px;height:8px;border-radius:50%;background:#555;flex-shrink:0;
  transition:all .3s;box-shadow:0 0 6px currentColor}
#dot.on{background:var(--green);color:var(--green)}
#dot.off{background:var(--red);color:var(--red)}
#brand{font-weight:700;font-size:13px;background:linear-gradient(90deg,var(--accent),var(--accent2));
  -webkit-background-clip:text;background-clip:text;color:transparent;flex-shrink:0}
#ws-info{flex:1;min-width:0;font-size:10.5px;color:var(--fg-dim);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;padding-left:4px}
#ws-info b{color:var(--fg);font-weight:600}
#model-sel{background:var(--input-bg);color:var(--fg);border:1px solid var(--input-border);
  border-radius:6px;padding:3px 8px;font-size:11px;max-width:150px;cursor:pointer}
#model-sel:focus{outline:none;border-color:var(--accent)}
#new-btn,#clear-btn{background:var(--btn2);border:none;cursor:pointer;color:var(--fg-dim);
  font-size:15px;padding:2px 8px;border-radius:6px;line-height:1;transition:all .15s}
#new-btn:hover,#clear-btn:hover{background:var(--btn);color:var(--btn-fg)}

/* ── messages ── */
#msgs{flex:1;overflow-y:auto;padding:12px 10px;display:flex;flex-direction:column;gap:14px}
#msgs::-webkit-scrollbar{width:6px}
#msgs::-webkit-scrollbar-track{background:transparent}
#msgs::-webkit-scrollbar-thumb{background:#3a3a52;border-radius:3px}
#msgs::-webkit-scrollbar-thumb:hover{background:#4a4a66}

.msg{display:flex;flex-direction:column;gap:4px;animation:fadein .25s ease}
@keyframes fadein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

.row{display:flex;align-items:flex-start;gap:9px}
.av{width:24px;height:24px;border-radius:8px;display:flex;align-items:center;
  justify-content:center;font-size:10px;font-weight:700;flex-shrink:0;margin-top:1px}
.av-ai{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
.av-you{background:#3a3a52;color:#c8c8e0}

.bub{padding:9px 12px;border-radius:var(--r);font-size:12.5px;line-height:1.6;
  word-break:break-word;overflow-wrap:anywhere;flex:1;min-width:0}
.msg-ai   .bub{background:var(--bg2);border:1px solid var(--border)}
.msg-user .bub{background:var(--user-bg);border:1px solid var(--user-border);margin-left:30px}
.msg-err  .bub{background:#3a1520;border:1px solid #6b2030}
.msg-sys  .bub{background:transparent;border:none;color:var(--fg-dim);
  font-size:11px;padding:2px 4px;font-style:italic}

.meta{font-size:10px;color:var(--fg-dim);padding-left:33px}
.meta.u{padding-left:0;text-align:right}

/* ── model badge (shows chosen agent/model/reason) ── */
.model-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(124,58,237,.15);
  border:1px solid rgba(124,58,237,.4);border-radius:20px;padding:3px 10px;font-size:10.5px;
  color:var(--accent);margin-bottom:6px;max-width:100%;flex-wrap:wrap}
.model-badge .mb-ico{font-size:11px}
.model-badge .mb-model{font-weight:600;color:var(--fg)}
.model-badge .mb-why{color:var(--fg-dim);font-style:italic}
.model-badge .mb-tag{background:var(--btn);color:var(--btn-fg);padding:1px 7px;
  border-radius:10px;font-size:9.5px;font-weight:600;text-transform:capitalize}

/* ── inline thinking indicator ── */
.inline-think{display:flex;align-items:center;gap:9px;padding:6px 2px;color:var(--fg-dim);
  font-size:11.5px;margin-bottom:4px}
.typing-dots{display:inline-flex;gap:4px}
.typing-dots span{width:6px;height:6px;border-radius:50%;background:var(--accent);
  animation:typing 1.4s infinite ease-in-out}
.typing-dots span:nth-child(2){animation-delay:.2s}
.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes typing{0%,60%,100%{transform:translateY(0);opacity:.3}30%{transform:translateY(-4px);opacity:1}}
.think-label{font-style:italic}
.think-label b{color:var(--accent);font-style:normal;font-weight:600}

/* ── markdown ── */
.bub p{margin:0 0 6px}.bub p:last-child{margin:0}
.bub strong{font-weight:600;color:#fff}
.bub em{font-style:italic;color:#d0d0e0}
.bub code{font-family:var(--mono);font-size:11.5px;background:rgba(0,0,0,.4);
  border:1px solid #333;border-radius:4px;padding:1px 6px;color:#f0a0c0}
.bub ul,.bub ol{padding-left:1.4em;margin:5px 0}
.bub li{margin:3px 0}

.cblk{position:relative;margin:9px 0;border-radius:8px;overflow:hidden;border:1px solid #333}
.chdr{display:flex;align-items:center;background:#1a1a2a;padding:4px 10px;
  font-size:10.5px;color:#999;border-bottom:1px solid #333;gap:6px}
.clng{flex:1;font-family:var(--mono)}
.cpbtn{background:none;border:1px solid #444;color:#888;border-radius:4px;
  padding:1px 8px;font-size:10px;cursor:pointer;transition:all .15s}
.cpbtn:hover{background:#333;color:#ccc;border-color:#666}
.cpbtn.ok{color:var(--green);border-color:var(--green)}
.cblk pre{margin:0;padding:11px 13px;background:var(--code-bg);overflow-x:auto;
  font-family:var(--mono);font-size:12px;line-height:1.6;color:#d4d4d4;white-space:pre}

/* ── agent activity cards ── */
.ev-card{margin:5px 0;border-radius:7px;font-size:11px;font-family:var(--mono);
  border-left:3px solid #444;padding:6px 10px;background:rgba(0,0,0,.3);
  display:flex;flex-direction:column;gap:3px;word-break:break-all}
.ev-card.ev-tool{border-color:var(--accent)}
.ev-card.ev-file{border-color:var(--green)}
.ev-card.ev-cmd{border-color:#38bdf8}
.ev-card.ev-err{border-color:var(--red)}
.ev-title{font-weight:600;color:#ddd;display:flex;align-items:center;gap:5px}
.ev-detail{color:#999;font-size:10px;white-space:pre-wrap;max-height:100px;overflow:auto}
.ev-detail::-webkit-scrollbar{width:4px}
.ev-detail::-webkit-scrollbar-thumb{background:#444;border-radius:2px}
.ev-ok{color:var(--green)}.ev-bad{color:var(--red)}

/* ── final summary card (Cursor/Kiro style "what changed" recap ── */
.summary-card{margin:10px 0;border-radius:10px;background:linear-gradient(135deg,rgba(124,58,237,.12),rgba(240,36,122,.08));
  border:1px solid rgba(124,58,237,.35);overflow:hidden;font-size:11.5px;word-break:break-all}
.sum-hdr{display:flex;align-items:center;gap:8px;padding:8px 12px;background:rgba(124,58,237,.15);
  border-bottom:1px solid rgba(124,58,237,.25);font-weight:600;color:#fff}
.sum-hdr .sum-ico{font-size:14px}
.sum-hdr .sum-title{flex:1}
.sum-hdr .sum-count{font-size:10px;background:var(--btn);color:var(--btn-fg);padding:2px 9px;
  border-radius:10px;font-weight:700}
.sum-body{padding:8px 12px;display:flex;flex-direction:column;gap:6px}
.sum-grp{display:flex;flex-direction:column;gap:3px}
.sum-grp .sum-label{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--fg-dim);font-weight:600}
.sum-item{display:flex;align-items:center;gap:6px;color:#d0d0e0;font-size:11.5px;padding:2px 0;cursor:pointer}
.sum-item:hover{color:var(--accent)}
.sum-item .si-ico{flex-shrink:0;font-size:12px}
.sum-item .si-path{font-family:var(--mono);font-size:10.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sum-item .si-cmd{font-family:var(--mono);font-size:10.5px;color:#a8c4e8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sum-ok{color:var(--green)}.sum-del{color:var(--red)}

/* ── agent todo/plan card ── */
.todo-card{margin:8px 0;border-radius:9px;background:rgba(30,30,42,.85);
  border:1px solid var(--border);overflow:hidden;font-size:11.5px;word-break:break-word}
.todo-hdr{display:flex;align-items:center;gap:7px;padding:7px 11px;background:rgba(124,58,237,.12);
  border-bottom:1px solid var(--border);font-weight:600;color:#fff}
.todo-hdr .todo-ico{font-size:13px}
.todo-hdr .todo-title{flex:1}
.todo-hdr .todo-prog{font-size:10px;color:var(--fg-dim);font-weight:500}
.todo-body{padding:7px 11px;display:flex;flex-direction:column;gap:5px}
.todo-item{display:flex;align-items:flex-start;gap:8px;padding:3px 0;transition:all .2s}
.todo-item .td-box{width:15px;height:15px;border-radius:4px;flex-shrink:0;margin-top:1px;
  display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;
  transition:all .2s}
.todo-item.pending .td-box{border:1.5px solid #555;background:transparent;color:transparent}
.todo-item.in_progress .td-box{border:1.5px solid var(--accent);background:rgba(124,58,237,.25);
  color:var(--accent);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.todo-item.done .td-box{border:1.5px solid var(--green);background:var(--green);color:#fff}
.todo-item .td-text{flex:1;line-height:1.5}
.todo-item.pending .td-text{color:var(--fg-dim)}
.todo-item.in_progress .td-text{color:#fff;font-weight:500}
.todo-item.done .td-text{color:var(--fg-dim);text-decoration:line-through}

/* ── attach preview bar ── */
#attach-bar{display:none;align-items:center;gap:6px;padding:5px 10px;
  background:rgba(124,58,237,.12);border-top:1px solid rgba(124,58,237,.25);flex-shrink:0}
#attach-bar.on{display:flex}
#attach-preview{display:flex;align-items:center;gap:6px;flex:1;min-width:0}
#attach-img{width:30px;height:30px;object-fit:cover;border-radius:5px;
  border:1px solid #444;display:none}
#attach-name{font-size:11px;color:var(--accent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#attach-type{font-size:10px;color:var(--fg-dim);background:#333;
  border-radius:4px;padding:1px 6px}
#attach-remove{background:none;border:none;cursor:pointer;color:var(--fg-dim);
  font-size:18px;line-height:1;padding:0 4px;flex-shrink:0}
#attach-remove:hover{color:var(--red)}

/* ── input area ── */
#input-wrap{padding:8px 10px;border-top:1px solid var(--border);flex-shrink:0;background:var(--bg2)}
#input-row{display:flex;gap:6px;align-items:flex-end}
#input-box{flex:1;background:var(--input-bg);color:var(--fg);
  border:1px solid var(--input-border);border-radius:var(--r);
  padding:9px 12px;font-size:12.5px;font-family:inherit;resize:none;
  min-height:40px;max-height:160px;overflow-y:auto;line-height:1.5;transition:border-color .15s}
#input-box::placeholder{color:#555}
#input-box:focus{outline:none;border-color:var(--accent)}

.icon-btn{background:var(--btn2);color:var(--btn2-fg);border:none;border-radius:var(--r);
  width:36px;height:36px;cursor:pointer;display:flex;align-items:center;
  justify-content:center;font-size:16px;flex-shrink:0;transition:all .15s}
.icon-btn:hover{filter:brightness(1.25)}
#send-btn{background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--btn-fg)}
#send-btn:disabled{opacity:.4;cursor:default;filter:none}
#hint{font-size:10px;color:#555;margin-top:5px;padding-left:2px;text-align:center}
</style>
</head>
<body>
<div id="shell">

  <!-- top bar -->
  <div id="topbar">
    <div id="dot" title="Agent offline"></div>
    <span id="brand">MyCodeAI</span>
    <span id="ws-info" title=""></span>
    <select id="model-sel" title="AI model"><option value="">Auto</option></select>
    <button id="new-btn" title="New conversation" onclick="newConv()">⊕</button>
    <button id="clear-btn" title="Clear conversation" onclick="clearMsgs()">✕</button>
  </div>

  <!-- messages -->
  <div id="msgs">
    <div class="msg msg-sys">
      <div class="bub">👋 Hello! I am <b>MyCodeAI</b> — your local AI coding agent.
Ask anything, describe what to build, or attach a file. I'll pick the right agent &amp; model and act directly. No cloud. No API keys.</div>
    </div>
  </div>

  <!-- attach preview -->
  <div id="attach-bar">
    <div id="attach-preview">
      <img id="attach-img" alt="preview"/>
      <span id="attach-type"></span>
      <span id="attach-name"></span>
    </div>
    <button id="attach-remove" title="Remove" onclick="removeAttach()">×</button>
  </div>

  <!-- input -->
  <div id="input-wrap">
    <div id="input-row">
      <button class="icon-btn" title="Attach file (code/text)" onclick="post('attachFile')">📎</button>
      <button class="icon-btn" title="Attach image" onclick="post('attachImage')">🖼</button>
      <textarea id="input-box" rows="1"
        placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"></textarea>
      <button id="send-btn" class="icon-btn" title="Send (Enter)" onclick="send()">➤</button>
    </div>
    <div id="hint">Enter · send &nbsp;|&nbsp; Shift+Enter · newline &nbsp;|&nbsp; 📎 file · 🖼 image</div>
  </div>

</div>

<script>
const vscode = acquireVsCodeApi();
const $ = id => document.getElementById(id);

const msgsEl    = $('msgs');
const inputEl   = $('input-box');
const sendBtn   = $('send-btn');
const dot       = $('dot');
const modelSel  = $('model-sel');
const wsInfo    = $('ws-info');
const attachBar = $('attach-bar');
const attachImg = $('attach-img');
const attachName= $('attach-name');
const attachType= $('attach-type');

let sessionId   = null;
let busy        = false;
let attachedFile= null;
let attachedImage=null;
let atBottom    = true;

/* ── scroll ── */
msgsEl.addEventListener('scroll', () => {
  atBottom = msgsEl.scrollHeight - msgsEl.scrollTop - msgsEl.clientHeight < 60;
});
function scrollDown(force){
  if(force || atBottom) msgsEl.scrollTop = msgsEl.scrollHeight;
}

/* ── input resize ── */
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
});
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});

/* ── send ── */
function send() {
  const text = inputEl.value.trim();
  if ((!text && !attachedFile && !attachedImage) || busy) return;
  inputEl.value = '';
  inputEl.style.height = 'auto';
  appendUserMsg(text, attachedFile, attachedImage);
  vscode.postMessage({
    type: 'chat', text,
    attachedFile: attachedFile || '',
    attachedImage: attachedImage || '',
    model: modelSel.value || undefined,
  });
  removeAttach();
  setBusy(true);
}

function post(type, extra){
  vscode.postMessage({ type, ...(extra||{}) });
}

/* ── helpers ── */
function el(tag, cls){ const e=document.createElement(tag); if(cls) e.className=cls; return e; }
function ts(){ return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); }

/* ── messages ── */
function appendUserMsg(text, file, img) {
  const wrap = el('div','msg msg-user');
  let content = text ? escHtml(text) : '';
  if (file) content += \`<br><span style="font-size:10px;color:var(--accent)">📎 \${escHtml(file)}</span>\`;
  if (img)  content += \`<br><span style="font-size:10px;color:#a8c4e8">🖼 \${escHtml(img)}</span>\`;
  wrap.innerHTML = \`<div class="row">
    <div class="bub">\${content}</div>
    <div class="av av-you" style="margin-left:auto">You</div>
  </div>
  <div class="meta u">\${ts()}</div>\`;
  msgsEl.appendChild(wrap);
  scrollDown(true);
}

function appendAiMsg(text) {
  const wrap = el('div','msg msg-ai');
  const bub  = el('div','bub');
  bub.innerHTML = renderMd(text);
  attachCopy(bub);
  const row = el('div','row');
  const av  = el('div','av av-ai'); av.textContent = 'AI';
  row.appendChild(av);
  row.appendChild(bub);
  wrap.appendChild(row);
  const meta = el('div','meta'); meta.textContent = ts();
  wrap.appendChild(meta);
  msgsEl.appendChild(wrap);
  scrollDown();
}

function appendErrMsg(text) {
  const wrap = el('div','msg msg-err');
  wrap.innerHTML = \`<div class="row"><div class="bub">⚠ \${escHtml(text)}</div></div>\`;
  msgsEl.appendChild(wrap);
  scrollDown(true);
}

function appendSysMsg(text) {
  const wrap = el('div','msg msg-sys');
  wrap.innerHTML = \`<div class="bub">\${escHtml(text)}</div>\`;
  msgsEl.appendChild(wrap);
  scrollDown();
}

function clearMsgs() {
  while (msgsEl.firstChild) msgsEl.removeChild(msgsEl.firstChild);
}

function newConv() {
  sessionId = null;
  clearMsgs();
  appendSysMsg('New conversation started.');
  vscode.postMessage({ type: 'newSession' });
}

/* ── busy state ── */
function setBusy(b) {
  busy = b;
  sendBtn.disabled = b;
}

/* ── live streaming ── */
let streamBub  = null;
let streamBuf  = '';
let streamWrap = null;
let streamThink = null;   // inline thinking element
let streamBadge = null;   // model badge element

function startStream(workspace) {
  streamBuf  = '';
  streamWrap = el('div','msg msg-ai');
  streamBadge = null;
  const row  = el('div','row');
  const av   = el('div','av av-ai'); av.textContent='AI';
  streamBub  = el('div','bub');
  streamBub.textContent = '';
  row.appendChild(av);
  row.appendChild(streamBub);
  streamWrap.appendChild(row);
  msgsEl.appendChild(streamWrap);
  scrollDown(true);
}

function ensureModelBadge(m) {
  if (streamBadge || !m) return;
  streamBadge = el('div','model-badge');
  const agent = m.agent || 'agent';
  streamBadge.innerHTML = \`
    <span class="mb-ico">🧠</span>
    <span class="mb-tag">\${escHtml(agent)}</span>
    <span class="mb-model">\${escHtml(m.model || '')}</span>
    \${m.reason ? \`<span class="mb-why">· \${escHtml(m.reason)}</span>\` : ''}
  \`;
  streamWrap.insertBefore(streamBadge, streamWrap.firstChild);
  scrollDown();
}

function ensureThinkEl() {
  if (streamThink || !streamWrap) return;
  streamThink = el('div','inline-think');
  streamThink.innerHTML = \`<span class="typing-dots"><span></span><span></span><span></span></span>
    <span class="think-label"><b>Thinking</b>…</span>\`;
  streamWrap.appendChild(streamThink);
  scrollDown();
}

function setThinkLabel(label) {
  if (streamThink) {
    const l = streamThink.querySelector('.think-label');
    if (l) l.innerHTML = label || '<b>Thinking</b>…';
  }
}

function removeThinkEl() {
  if (streamThink) { streamThink.remove(); streamThink = null; }
}

function appendToken(token) {
  if (!streamBub) return;
  if (streamThink) removeThinkEl();
  streamBuf += token;
  streamBub.textContent = streamBuf;
  scrollDown();
}

function finaliseStream() {
  if (streamBub && streamBuf) {
    streamBub.innerHTML = renderMd(streamBuf);
    attachCopy(streamBub);
    const meta = el('div','meta'); meta.textContent = ts();
    streamWrap.appendChild(meta);
    scrollDown();
  }
  removeThinkEl();
  streamBub  = null;
  streamBuf  = '';
  streamWrap = null;
  streamThink = null;
  streamBadge = null;
  streamTodoCard = null;
}

/* ── agent activity rendering ── */
function appendToolEvent(kind, name, detail) {
  const card = el('div', 'ev-card ev-tool');
  const icon = kind === 'call' ? '🔧' : kind === 'error' ? '❌' : '✅';
  const cls  = kind === 'error' ? 'ev-bad' : kind === 'result' ? 'ev-ok' : '';
  card.innerHTML = \`
    <div class="ev-title">\${icon} \${escHtml(name)}</div>
    <div class="ev-detail \${cls}">\${escHtml(typeof detail === 'object' ? JSON.stringify(detail, null, 2) : String(detail||''))}</div>
  \`;
  _appendToStream(card);
}

function appendFileEvent(kind, path) {
  const card = el('div', 'ev-card ev-file');
  const icon = kind === 'created' ? '📄' : '✏️';
  const name = path.split('/').pop();
  card.innerHTML = \`
    <div class="ev-title ev-ok">\${icon} \${kind}: \${escHtml(name)}</div>
    <div class="ev-detail">\${escHtml(path)}</div>
  \`;
  card.style.cursor = 'pointer';
  card.title = 'Click to open file';
  card.onclick = () => vscode.postMessage({ type: 'openFile', path });
  _appendToStream(card);
}

function appendCommandEvent(command, exitCode, output, ok) {
  const card = el('div', \`ev-card ev-cmd\${ok ? '' : ' ev-err'}\`);
  const icon = ok ? '⚡' : '❌';
  card.innerHTML = \`
    <div class="ev-title \${ok ? 'ev-ok' : 'ev-bad'}">\${icon} \${escHtml(command.slice(0,90))}</div>
    \${output ? \`<div class="ev-detail">\${escHtml(output.slice(0,600))}</div>\` : ''}
  \`;
  _appendToStream(card);
}

function appendSummary(m) {
  const created = m.filesCreated || [];
  const edited  = m.filesEdited  || [];
  const deleted = m.filesDeleted || [];
  const cmds    = m.commandsRun  || [];
  const total   = created.length + edited.length + deleted.length + cmds.length;
  if (!total) return;

  const card = el('div', 'summary-card');
  let body = '';

  if (created.length) {
    body += \`<div class="sum-grp"><div class="sum-label">Created</div>\` +
      created.map(p => \`<div class="sum-item" onclick="post('openFile',{path:'\${escHtml(p)}'})">
        <span class="si-ico">📄</span><span class="si-path">\${escHtml(p)}</span></div>\`).join('') +
      \`</div>\`;
  }
  if (edited.length) {
    body += \`<div class="sum-grp"><div class="sum-label">Edited</div>\` +
      edited.map(p => \`<div class="sum-item" onclick="post('openFile',{path:'\${escHtml(p)}'})">
        <span class="si-ico">✏️</span><span class="si-path">\${escHtml(p)}</span></div>\`).join('') +
      \`</div>\`;
  }
  if (deleted.length) {
    body += \`<div class="sum-grp"><div class="sum-label">Deleted</div>\` +
      deleted.map(p => \`<div class="sum-item sum-del">
        <span class="si-ico">🗑</span><span class="si-path">\${escHtml(p)}</span></div>\`).join('') +
      \`</div>\`;
  }
  if (cmds.length) {
    body += \`<div class="sum-grp"><div class="sum-label">Commands</div>\` +
      cmds.map(c => \`<div class="sum-item">
        <span class="si-ico">⚡</span><span class="si-cmd">\${escHtml(c.slice(0,120))}</span></div>\`).join('') +
      \`</div>\`;
  }

  card.innerHTML = \`
    <div class="sum-hdr">
      <span class="sum-ico">✅</span>
      <span class="sum-title">Done</span>
      <span class="sum-count">\${total} action\${total>1?'s':''}</span>
    </div>
    <div class="sum-body">\${body}</div>
  \`;
  _appendToStream(card);
}

let streamTodoCard = null;

function renderTodo(items) {
  if (!items || !items.length) return;
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;
  const pct = total ? Math.round(done/total*100) : 0;

  if (streamTodoCard) {
    const body = streamTodoCard.querySelector('.todo-body');
    const prog = streamTodoCard.querySelector('.todo-prog');
    if (body) body.innerHTML = items.map(i => todoItemHtml(i)).join('');
    if (prog) prog.textContent = \`\${done}/\${total} · \${pct}%\`;
  } else {
    streamTodoCard = el('div', 'todo-card');
    streamTodoCard.innerHTML = \`
      <div class="todo-hdr">
        <span class="todo-ico">📋</span>
        <span class="todo-title">Plan</span>
        <span class="todo-prog">\${done}/\${total} · \${pct}%</span>
      </div>
      <div class="todo-body">\${items.map(i => todoItemHtml(i)).join('')}</div>
    \`;
    _appendToStream(streamTodoCard);
  }
}

function todoItemHtml(i) {
  const check = i.status === 'done' ? '✓' : (i.status === 'in_progress' ? '◐' : '');
  return \`<div class="todo-item \${i.status}">
    <div class="td-box">\${check}</div>
    <div class="td-text">\${escHtml(i.text)}</div>
  </div>\`;
}

function _appendToStream(node) {
  if (streamThink) removeThinkEl();
  if (streamWrap) {
    streamWrap.appendChild(node);
  } else {
    const wrap = el('div', 'msg msg-ai');
    wrap.appendChild(node);
    msgsEl.appendChild(wrap);
  }
  scrollDown();
}

/* ── attach ── */
function showAttach(name, typeLabel, imgDataUrl) {
  attachBar.classList.add('on');
  attachName.textContent = name;
  attachType.textContent = typeLabel;
  if (imgDataUrl) {
    attachImg.src = imgDataUrl;
    attachImg.style.display = 'block';
  } else {
    attachImg.style.display = 'none';
  }
}

function removeAttach() {
  attachedFile  = null;
  attachedImage = null;
  attachBar.classList.remove('on');
  attachImg.src = '';
  attachImg.style.display = 'none';
}

/* ── workspace display ── */
function setWorkspace(path) {
  if (!path) { wsInfo.textContent = ''; wsInfo.title = ''; return; }
  const name = path.split('/').pop() || path;
  wsInfo.innerHTML = \`📁 <b>\${escHtml(name)}</b>\`;
  wsInfo.title = path;
}

/* ── markdown ── */
function renderMd(text) {
  text = text.replace(/\\\`\\\`\\\`([\\w+-]*)\\n?([\\s\\S]*?)\\\`\\\`\\\`/g, (_, lang, code) => {
    const id = 'c' + Math.random().toString(36).slice(2);
    const l  = lang || 'code';
    return \`<div class="cblk"><div class="chdr"><span class="clng">\${escHtml(l)}</span>
      <button class="cpbtn" onclick="cpCode('\${id}')">Copy</button></div>
      <pre id="\${id}">\${escHtml(code.trimEnd())}</pre></div>\`;
  });

  return text.split(/\\n{2,}/).map(para => {
    if (/^\\s*[-*•]\\s/.test(para)||/^\\s*\\d+\\.\\s/.test(para)) {
      const tag = /^\\s*\\d+\\./.test(para)?'ol':'ul';
      const items = para.split('\\n').filter(Boolean)
        .map(l=>\`<li>\${inlineMd(l.replace(/^\\s*[-*•\\d.]+\\s/,''))}</li>\`).join('');
      return \`<\${tag}>\${items}</\${tag}>\`;
    }
    if (/^#{1,3}\\s/.test(para)) {
      const lv = para.match(/^(#{1,3})/)[1].length;
      const sz = ['1.15em','1.05em','1em'][lv-1];
      return \`<p style="font-weight:600;font-size:\${sz};margin:7px 0 4px">
        \${inlineMd(para.replace(/^#{1,3}\\s+/,''))}</p>\`;
    }
    return \`<p>\${para.split('\\n').map(inlineMd).join('<br>')}</p>\`;
  }).join('');
}

function inlineMd(t) {
  return t
    .replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/__(.+?)__/g,'<strong>$1</strong>')
    .replace(/\\*([^*]+)\\*/g,'<em>$1</em>')
    .replace(/_([^_]+)_/g,'<em>$1</em>')
    .replace(/\\\`([^\\\`]+)\\\`/g,'<code>$1</code>');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function attachCopy(root) {
  root.querySelectorAll('.cpbtn').forEach(b => {
    b.addEventListener('click', () => cpCode(b.getAttribute('onclick').match(/'(.*?)'/)[1]));
  });
}

function cpCode(id) {
  const pre = document.getElementById(id);
  if (!pre) return;
  navigator.clipboard.writeText(pre.textContent || '').then(() => {}).catch(() => {
    const r = document.createRange();
    r.selectNodeContents(pre);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(r);
    document.execCommand('copy');
    sel.removeAllRanges();
  });
  const btn = document.querySelector(\`[onclick="cpCode('\${id}')"]\`);
  if (btn) { btn.textContent='Copied!'; btn.classList.add('ok');
    setTimeout(()=>{ btn.textContent='Copy'; btn.classList.remove('ok'); }, 1800); }
}

/* ── messages from extension ── */
window.addEventListener('message', ({data: m}) => {
  switch(m.type) {
    case 'serverStatus':
      dot.className = m.online ? 'on' : 'off';
      dot.title = m.online ? 'Agent server online' : 'Agent server offline';
      if (!m.online) appendSysMsg('⚠ Agent server offline. Run: mycodeai-server in a terminal.');
      break;

    case 'models':
      modelSel.innerHTML = '';
      const autoOpt = document.createElement('option');
      autoOpt.value = ''; autoOpt.textContent = '🤖 Auto (router picks)';
      modelSel.appendChild(autoOpt);
      (m.models||[]).forEach(md => {
        const o = document.createElement('option');
        o.value = md; o.textContent = md;
        modelSel.appendChild(o);
      });
      if (!m.models || !m.models.length) {
        const o = document.createElement('option');
        o.value=''; o.textContent='No models found';
        modelSel.appendChild(o);
      }
      break;

    case 'selectedModel':
      for (const o of modelSel.options) if (o.value === m.model) { o.selected = true; break; }
      break;

    case 'assistantMessage':
      setBusy(false);
      appendAiMsg(m.text);
      if (m.sessionId) sessionId = m.sessionId;
      break;

    case 'error':
      setBusy(false);
      appendErrMsg(m.text);
      break;

    case 'streamStart':
      setBusy(true);
      setWorkspace(m.workspace);
      startStream(m.workspace);
      ensureThinkEl();
      setThinkLabel('<b>Thinking</b>…');
      break;

    case 'streamToken':
      appendToken(m.token);
      break;

    case 'streamEnd':
      finaliseStream();
      setBusy(false);
      if (m.sessionId) sessionId = m.sessionId;
      break;

    case 'streamError':
      finaliseStream();
      setBusy(false);
      appendErrMsg(m.text || 'Stream error');
      break;

    case 'agentStatus':
      if (!streamThink) ensureThinkEl();
      const raw = (m.text || '').replace(/^(⚡|🔧|🐛|✅|✏️|📄)\s*/, '');
      setThinkLabel(\`<b>\${escHtml(raw)}</b>\`);
      break;

    case 'model_selected':
      ensureModelBadge(m);
      for (const o of modelSel.options) {
        if (o.value === m.model) { o.selected = true; break; }
      }
      break;

    case 'ramStatus': {
      const avail = (m.available||0).toFixed(1);
      const fits  = (m.canRun||[]).map(x => String(x).split(':')[0]).join(', ');
      const nope  = (m.tooBig||[]).map(x => String(x).split(':')[0]).join(', ');
      let msg = \`💾 RAM: \${avail} GB free — fits: \${fits || 'none'}\`;
      if (nope) msg += \` | too big: \${nope}\`;
      appendSysMsg(msg);
      break;
    }

    case 'toolCall':
      appendToolEvent('call', m.name, m.args);
      if (streamThink) removeThinkEl();
      break;

    case 'toolResult':
      if (m.error) appendToolEvent('error', m.name, m.error);
      else appendToolEvent('result', m.name, m.output);
      break;

    case 'fileCreated':
      appendFileEvent('created', m.path);
      break;

    case 'fileEdited':
      appendFileEvent('edited', m.path);
      break;

    case 'commandRun':
      appendCommandEvent(m.command, m.exitCode, m.output, m.exitCode === 0);
      break;

    case 'todo_update':
      renderTodo(m.items);
      break;

    case 'summary':
      appendSummary(m);
      break;

    case 'fileAttached':
      attachedFile = m.name;
      showAttach(m.name, '📄 file', '');
      break;

    case 'imageAttached':
      attachedImage = m.name;
      showAttach(m.name, '🖼 image', m.dataUrl);
      break;

    case 'file_analyzed':
      const icon = m.file_type === 'image' ? '🖼' : m.file_type === 'pdf' ? '📋' : '📄';
      appendSysMsg(\`\${icon} \${m.file} analyzed — \${m.summary || m.file_type}\`);
      break;

    case 'specCreated':
      appendSysMsg('✅ Spec created: "' + m.name + '" — phase: ' + m.phase);
      break;

    case 'taskComplete':
      appendSysMsg('✅ Task ' + m.taskId + ' complete: ' + (m.summary||''));
      break;

    case 'checkpoint':
      appendSysMsg('⬡ Checkpoint saved: ' + m.sha);
      break;
  }
});

/* ── model selector change ── */
modelSel.addEventListener('change', () => {
  vscode.postMessage({ type: 'setModel', model: modelSel.value });
});

/* ── init ── */
vscode.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}

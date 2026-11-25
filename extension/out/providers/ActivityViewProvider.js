"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ActivityViewProvider = void 0;
class ActivityViewProvider {
    constructor(client) {
        this.client = client;
    }
    resolveWebviewView(webviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        this._render('idle', 'Waiting…');
    }
    setActivity(status, message, detail) {
        this._render(status, message, detail);
    }
    _render(status, message, detail) {
        if (!this._view)
            return;
        const icon = status === 'thinking' ? '⏳' : status === 'tool_call' ? '🔧' : status === 'writing' ? '✏️' : '💤';
        this._view.webview.html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { font-family: var(--vscode-font-family, sans-serif); padding: .6rem; font-size: 12px; color: var(--vscode-foreground); }
  .status { font-weight: bold; margin-bottom: .4em; }
  .detail { color: #888; font-size: 11px; word-break: break-all; }
</style>
</head>
<body>
  <div class="status">${icon} ${message}</div>
  ${detail ? `<div class="detail">${detail}</div>` : ''}
</body>
</html>`;
    }
}
exports.ActivityViewProvider = ActivityViewProvider;
//# sourceMappingURL=ActivityViewProvider.js.map
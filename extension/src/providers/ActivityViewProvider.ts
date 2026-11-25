import * as vscode from 'vscode';
import { AgentClient } from '../AgentClient';

export class ActivityViewProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;

    constructor(private client: AgentClient) {}

    resolveWebviewView(webviewView: vscode.WebviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        this._render('idle', 'Waiting…');
    }

    setActivity(status: string, message: string, detail?: string) {
        this._render(status, message, detail);
    }

    private _render(status: string, message: string, detail?: string) {
        if (!this._view) return;
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

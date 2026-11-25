import * as vscode from 'vscode';
import { AgentPanelProvider } from './panels/AgentPanelProvider';
import { SpecTreeProvider } from './providers/SpecTreeProvider';
import { TaskTreeProvider } from './providers/TaskTreeProvider';
import { ActivityViewProvider } from './providers/ActivityViewProvider';
import { AgentClient } from './AgentClient';
import { registerCommands } from './commands/commands';

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('mycodeai');
    const agentUrl: string = config.get('agentUrl', 'http://127.0.0.1:8765');
    const client = new AgentClient(agentUrl);

    // ── View providers ────────────────────────────────────────────────────────
    const agentPanel = new AgentPanelProvider(context.extensionUri, client);
    const specTree = new SpecTreeProvider(client);
    const taskTree = new TaskTreeProvider(client);
    const activityView = new ActivityViewProvider(client);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('mycodeai.agentPanel', agentPanel),
        vscode.window.registerTreeDataProvider('mycodeai.specTree', specTree),
        vscode.window.registerTreeDataProvider('mycodeai.taskTree', taskTree),
        vscode.window.registerWebviewViewProvider('mycodeai.activityView', activityView),
    );

    // ── Commands ──────────────────────────────────────────────────────────────
    registerCommands(context, client, agentPanel, specTree, taskTree);

    // ── Status bar ────────────────────────────────────────────────────────────
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.text = '$(robot) MyCodeAI';
    statusBar.tooltip = 'Open MyCodeAI Agent (Ctrl+Shift+A)';
    statusBar.command = 'mycodeai.openAgent';
    statusBar.show();
    context.subscriptions.push(statusBar);

    // ── Health check ──────────────────────────────────────────────────────────
    client.health().then(ok => {
        if (ok) {
            statusBar.text = '$(robot) MyCodeAI ✓';
        } else {
            statusBar.text = '$(robot) MyCodeAI ✗';
            statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            vscode.window.showWarningMessage(
                'MyCodeAI: Agent server not running.',
                'How to start'
            ).then(action => {
                if (action === 'How to start') {
                    vscode.window.showInformationMessage(
                        'Run in terminal: cd /home/ubuntu/Desktop/MyCodeAI-IDE && PYTHONPATH=. python3 -m agent.core.server'
                    );
                }
            });
        }
    });
}

export function deactivate() {}

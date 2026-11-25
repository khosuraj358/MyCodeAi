import * as vscode from 'vscode';
import { AgentClient } from '../AgentClient';
import { AgentPanelProvider } from '../panels/AgentPanelProvider';
import { SpecTreeProvider } from '../providers/SpecTreeProvider';
import { TaskTreeProvider } from '../providers/TaskTreeProvider';

export function registerCommands(
    context: vscode.ExtensionContext,
    client: AgentClient,
    agentPanel: AgentPanelProvider,
    specTree: SpecTreeProvider,
    taskTree: TaskTreeProvider,
) {
    const reg = (cmd: string, fn: (...args: any[]) => any) =>
        context.subscriptions.push(vscode.commands.registerCommand(cmd, fn));

    // ── Open agent panel ─────────────────────────────────────────────────────
    reg('mycodeai.openAgent', () => {
        vscode.commands.executeCommand('mycodeai.agentPanel.focus');
    });

    // ── New spec ─────────────────────────────────────────────────────────────
    reg('mycodeai.newSpec', async () => {
        const goal = await vscode.window.showInputBox({
            prompt: 'Describe what you want to build',
            placeHolder: 'e.g. Build a REST API for a todo app in Python',
            ignoreFocusOut: true,
        });
        if (!goal) return;

        await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'MyCodeAI: Creating spec…', cancellable: false },
            async () => {
                try {
                    const spec = await client.createSpec(goal);
                    specTree.refresh();
                    agentPanel.notify({ type: 'specCreated', name: spec.name, phase: spec.phase });
                    vscode.window.showInformationMessage(
                        `Spec created: "${spec.name}" — Phase: ${spec.phase}`,
                        'Open Spec'
                    ).then(action => {
                        if (action === 'Open Spec') {
                            vscode.commands.executeCommand('mycodeai.openSpec', spec.id);
                        }
                    });
                } catch (e: any) {
                    vscode.window.showErrorMessage(`Failed to create spec: ${e.message}`);
                }
            }
        );
    });

    // ── Open spec panel ───────────────────────────────────────────────────────
    reg('mycodeai.openSpec', async (specId?: string) => {
        if (!specId) {
            const specs = await client.listSpecs().catch(() => []);
            if (specs.length === 0) {
                vscode.window.showInformationMessage('No specs yet. Use "MyCodeAI: New Spec" to create one.');
                return;
            }
            const pick = await vscode.window.showQuickPick(
                specs.map(s => ({ label: s.name, description: s.phase, detail: s.goal, id: s.id })),
                { placeHolder: 'Select a spec to open' }
            );
            if (!pick) return;
            specId = (pick as any).id;
        }
        SpecWebviewPanel.createOrShow(context.extensionUri, client, specId!);
    });

    // ── Approve current phase ─────────────────────────────────────────────────
    reg('mycodeai.approvePhase', async (specId?: string) => {
        if (!specId) {
            const specs = await client.listSpecs().catch(() => []);
            const pick = await vscode.window.showQuickPick(
                specs.map(s => ({ label: s.name, description: `Phase: ${s.phase}`, id: s.id })),
                { placeHolder: 'Select spec to approve' }
            );
            if (!pick) return;
            specId = (pick as any).id;
        }
        const feedback = await vscode.window.showInputBox({
            prompt: 'Any feedback? (leave blank to approve as-is)',
            placeHolder: 'Optional feedback for revision',
        });
        const approved = feedback === undefined ? false : true;
        if (feedback === undefined) return;

        await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'MyCodeAI: Advancing spec…' },
            async () => {
                try {
                    const spec = await client.approvePhase(specId!, approved, feedback ?? '');
                    specTree.refresh();
                    taskTree.refresh();
                    vscode.window.showInformationMessage(`Spec advanced to phase: ${spec.phase}`);
                } catch (e: any) {
                    vscode.window.showErrorMessage(`Failed to advance spec: ${e.message}`);
                }
            }
        );
    });

    // ── Run next task ─────────────────────────────────────────────────────────
    reg('mycodeai.runNextTask', async (specId?: string) => {
        if (!specId) {
            const specs = await client.listSpecs().catch(() => []);
            const impl = specs.filter(s => s.phase === 'implementation');
            if (impl.length === 0) {
                vscode.window.showInformationMessage('No specs in implementation phase.');
                return;
            }
            const pick = await vscode.window.showQuickPick(
                impl.map(s => ({ label: s.name, id: s.id })),
                { placeHolder: 'Select spec to run next task' }
            );
            if (!pick) return;
            specId = (pick as any).id;
        }
        await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'MyCodeAI: Running next task…', cancellable: false },
            async () => {
                try {
                    const result = await client.runNextTask(specId!);
                    taskTree.refresh();
                    if (result.status === 'all_tasks_complete') {
                        agentPanel.notify({ type: 'taskComplete', taskId: 'all', summary: 'All tasks complete' });
                        vscode.window.showInformationMessage('All tasks complete! Moving to review phase.');
                    } else {
                        agentPanel.notify({ type: 'taskComplete', taskId: result.task_id, summary: result.summary });
                        vscode.window.showInformationMessage(
                            `Task ${result.task_id} complete: ${result.summary?.slice(0, 80)}`
                        );
                    }
                } catch (e: any) {
                    vscode.window.showErrorMessage(`Task failed: ${e.message}`);
                }
            }
        );
    });

    // ── Git checkpoint ────────────────────────────────────────────────────────
    reg('mycodeai.checkpoint', async () => {
        const msg = await vscode.window.showInputBox({
            prompt: 'Checkpoint message',
            placeHolder: 'e.g. after implementing login module',
        });
        if (!msg) return;
        try {
            const result = await client.checkpoint(msg);
            agentPanel.notify({ type: 'checkpoint', sha: result.sha });
            vscode.window.showInformationMessage(`Checkpoint created: ${result.sha}`);
        } catch (e: any) {
            vscode.window.showErrorMessage(`Checkpoint failed: ${e.message}`);
        }
    });

    // ── Rewind ────────────────────────────────────────────────────────────────
    reg('mycodeai.rewind', async () => {
        vscode.window.showWarningMessage(
            'Rewind will restore the workspace to a previous checkpoint. Open the terminal and run: git log --oneline',
            'Open Terminal'
        ).then(a => {
            if (a === 'Open Terminal') {
                vscode.commands.executeCommand('workbench.action.terminal.new');
            }
        });
    });

    // ── Compact context ───────────────────────────────────────────────────────
    reg('mycodeai.compact', async () => {
        vscode.window.showInformationMessage(
            'Context compaction runs automatically when the session grows large. It summarises previous work so the agent can continue longer sessions.',
        );
    });
}

// ── Minimal spec webview panel ────────────────────────────────────────────────

class SpecWebviewPanel {
    static panels = new Map<string, vscode.WebviewPanel>();

    static createOrShow(extensionUri: vscode.Uri, client: AgentClient, specId: string) {
        const existing = this.panels.get(specId);
        if (existing) { existing.reveal(); return; }

        const panel = vscode.window.createWebviewPanel(
            'mycodeaiSpec',
            'Spec',
            vscode.ViewColumn.Beside,
            { enableScripts: true, retainContextWhenHidden: true }
        );
        this.panels.set(specId, panel);
        panel.onDidDispose(() => this.panels.delete(specId));

        panel.webview.html = `<!DOCTYPE html><html><body><p style="font-family:sans-serif;padding:1rem">Loading spec ${specId}…</p></body></html>`;

        client.getSpec(specId).then(spec => {
            panel.title = `Spec: ${spec.name}`;
            panel.webview.html = buildSpecHtml(spec);
        }).catch(e => {
            panel.webview.html = `<!DOCTYPE html><html><body><p style="color:red">Error: ${e.message}</p></body></html>`;
        });
    }
}

function buildSpecHtml(spec: any): string {
    const tasks = (spec.tasks as any[]).map(t =>
        `<li class="${t.status}"><strong>${t.id}</strong> ${t.title} <em>(${t.status})</em></li>`
    ).join('');

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { font-family: var(--vscode-font-family, sans-serif); padding: 1rem; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
  h1 { font-size: 1.3em; border-bottom: 1px solid #555; padding-bottom: .4em; }
  h2 { font-size: 1em; margin-top: 1.5em; color: #aaa; text-transform: uppercase; letter-spacing: .05em; }
  pre { background: #1e1e1e; padding: .8em; border-radius: 4px; overflow: auto; font-size: 12px; white-space: pre-wrap; }
  .phase { display: inline-block; background: #0078d4; color: #fff; border-radius: 3px; padding: 2px 8px; font-size: .85em; }
  li.completed { color: #4ec94e; }
  li.in_progress { color: #d4a443; }
  li.failed { color: #f44; }
  li.pending { color: #aaa; }
  ul { padding-left: 1.5em; line-height: 1.8; }
</style>
</head>
<body>
<h1>${spec.name}</h1>
<p><span class="phase">${spec.phase}</span></p>
<p><em>${spec.goal}</em></p>

<h2>Requirements</h2>
<pre>${spec.requirements_md || '(not yet generated)'}</pre>

<h2>Design</h2>
<pre>${spec.design_md || '(not yet generated)'}</pre>

<h2>Tasks</h2>
<ul>${tasks || '<li>(not yet generated)</li>'}</ul>
</body>
</html>`;
}

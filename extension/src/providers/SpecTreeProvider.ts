import * as vscode from 'vscode';
import { AgentClient, SpecSummary } from '../AgentClient';

export class SpecTreeProvider implements vscode.TreeDataProvider<SpecTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<SpecTreeItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor(private client: AgentClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: SpecTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: SpecTreeItem): Promise<SpecTreeItem[]> {
        if (element) return [];
        try {
            const specs = await this.client.listSpecs();
            return specs.map(s => new SpecTreeItem(s));
        } catch {
            return [new SpecTreeItem({ id: '', name: '(agent offline)', goal: '', phase: '', created_at: '' })];
        }
    }
}

class SpecTreeItem extends vscode.TreeItem {
    constructor(public readonly spec: SpecSummary) {
        super(spec.name || '(unnamed)', vscode.TreeItemCollapsibleState.None);
        this.description = spec.phase;
        this.tooltip = spec.goal;
        this.iconPath = phaseIcon(spec.phase);
        this.contextValue = 'spec';
        if (spec.id) {
            this.command = {
                command: 'mycodeai.openSpec',
                title: 'Open Spec',
                arguments: [spec.id],
            };
        }
    }
}

function phaseIcon(phase: string): vscode.ThemeIcon {
    switch (phase) {
        case 'requirements': return new vscode.ThemeIcon('list-unordered');
        case 'design':       return new vscode.ThemeIcon('symbol-class');
        case 'tasks':        return new vscode.ThemeIcon('checklist');
        case 'implementation': return new vscode.ThemeIcon('tools');
        case 'review':       return new vscode.ThemeIcon('eye');
        case 'done':         return new vscode.ThemeIcon('pass-filled');
        default:             return new vscode.ThemeIcon('circle-outline');
    }
}

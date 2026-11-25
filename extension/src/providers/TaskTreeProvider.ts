import * as vscode from 'vscode';
import { AgentClient, SpecTask } from '../AgentClient';

type TaskNode = { specId: string; specName: string; tasks?: SpecTask[] };

export class TaskTreeProvider implements vscode.TreeDataProvider<TaskTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<TaskTreeItem | undefined | void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    constructor(private client: AgentClient) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: TaskTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: TaskTreeItem): Promise<TaskTreeItem[]> {
        if (!element) {
            // Root: list specs that are in implementation phase
            try {
                const specs = await this.client.listSpecs();
                const active = specs.filter(s =>
                    ['tasks', 'implementation', 'review'].includes(s.phase)
                );
                return active.map(s => new TaskTreeItem(s.name, s.id, undefined, true));
            } catch {
                return [];
            }
        }

        // Children: tasks of the spec
        if (element.specId && element.collapsibleState === vscode.TreeItemCollapsibleState.Collapsed) {
            try {
                const spec = await this.client.getSpec(element.specId);
                return spec.tasks.map(t => new TaskTreeItem(t.title, element.specId, t, false));
            } catch {
                return [];
            }
        }
        return [];
    }
}

class TaskTreeItem extends vscode.TreeItem {
    constructor(
        label: string,
        public readonly specId: string,
        public readonly task?: SpecTask,
        isSpec: boolean = false,
    ) {
        super(
            label,
            isSpec
                ? vscode.TreeItemCollapsibleState.Collapsed
                : vscode.TreeItemCollapsibleState.None,
        );

        if (task) {
            this.description = task.id;
            this.iconPath = statusIcon(task.status);
            this.tooltip = task.description;
            this.contextValue = `task-${task.status}`;
        } else {
            this.iconPath = new vscode.ThemeIcon('project');
            this.contextValue = 'spec-tasks';
        }
    }
}

function statusIcon(status: string): vscode.ThemeIcon {
    switch (status) {
        case 'completed':   return new vscode.ThemeIcon('pass', new vscode.ThemeColor('testing.iconPassed'));
        case 'in_progress': return new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.yellow'));
        case 'failed':      return new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
        case 'skipped':     return new vscode.ThemeIcon('debug-step-over');
        default:            return new vscode.ThemeIcon('circle-outline', new vscode.ThemeColor('foreground'));
    }
}

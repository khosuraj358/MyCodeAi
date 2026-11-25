"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.TaskTreeProvider = void 0;
const vscode = __importStar(require("vscode"));
class TaskTreeProvider {
    constructor(client) {
        this.client = client;
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    async getChildren(element) {
        if (!element) {
            // Root: list specs that are in implementation phase
            try {
                const specs = await this.client.listSpecs();
                const active = specs.filter(s => ['tasks', 'implementation', 'review'].includes(s.phase));
                return active.map(s => new TaskTreeItem(s.name, s.id, undefined, true));
            }
            catch {
                return [];
            }
        }
        // Children: tasks of the spec
        if (element.specId && element.collapsibleState === vscode.TreeItemCollapsibleState.Collapsed) {
            try {
                const spec = await this.client.getSpec(element.specId);
                return spec.tasks.map(t => new TaskTreeItem(t.title, element.specId, t, false));
            }
            catch {
                return [];
            }
        }
        return [];
    }
}
exports.TaskTreeProvider = TaskTreeProvider;
class TaskTreeItem extends vscode.TreeItem {
    constructor(label, specId, task, isSpec = false) {
        super(label, isSpec
            ? vscode.TreeItemCollapsibleState.Collapsed
            : vscode.TreeItemCollapsibleState.None);
        this.specId = specId;
        this.task = task;
        if (task) {
            this.description = task.id;
            this.iconPath = statusIcon(task.status);
            this.tooltip = task.description;
            this.contextValue = `task-${task.status}`;
        }
        else {
            this.iconPath = new vscode.ThemeIcon('project');
            this.contextValue = 'spec-tasks';
        }
    }
}
function statusIcon(status) {
    switch (status) {
        case 'completed': return new vscode.ThemeIcon('pass', new vscode.ThemeColor('testing.iconPassed'));
        case 'in_progress': return new vscode.ThemeIcon('sync~spin', new vscode.ThemeColor('charts.yellow'));
        case 'failed': return new vscode.ThemeIcon('error', new vscode.ThemeColor('testing.iconFailed'));
        case 'skipped': return new vscode.ThemeIcon('debug-step-over');
        default: return new vscode.ThemeIcon('circle-outline', new vscode.ThemeColor('foreground'));
    }
}
//# sourceMappingURL=TaskTreeProvider.js.map
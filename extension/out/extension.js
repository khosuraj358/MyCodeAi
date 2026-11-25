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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const AgentPanelProvider_1 = require("./panels/AgentPanelProvider");
const SpecTreeProvider_1 = require("./providers/SpecTreeProvider");
const TaskTreeProvider_1 = require("./providers/TaskTreeProvider");
const ActivityViewProvider_1 = require("./providers/ActivityViewProvider");
const AgentClient_1 = require("./AgentClient");
const commands_1 = require("./commands/commands");
function activate(context) {
    const config = vscode.workspace.getConfiguration('mycodeai');
    const agentUrl = config.get('agentUrl', 'http://127.0.0.1:8765');
    const client = new AgentClient_1.AgentClient(agentUrl);
    // ── View providers ────────────────────────────────────────────────────────
    const agentPanel = new AgentPanelProvider_1.AgentPanelProvider(context.extensionUri, client);
    const specTree = new SpecTreeProvider_1.SpecTreeProvider(client);
    const taskTree = new TaskTreeProvider_1.TaskTreeProvider(client);
    const activityView = new ActivityViewProvider_1.ActivityViewProvider(client);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider('mycodeai.agentPanel', agentPanel), vscode.window.registerTreeDataProvider('mycodeai.specTree', specTree), vscode.window.registerTreeDataProvider('mycodeai.taskTree', taskTree), vscode.window.registerWebviewViewProvider('mycodeai.activityView', activityView));
    // ── Commands ──────────────────────────────────────────────────────────────
    (0, commands_1.registerCommands)(context, client, agentPanel, specTree, taskTree);
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
        }
        else {
            statusBar.text = '$(robot) MyCodeAI ✗';
            statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
            vscode.window.showWarningMessage('MyCodeAI: Agent server not running.', 'How to start').then(action => {
                if (action === 'How to start') {
                    vscode.window.showInformationMessage('Run in terminal: cd /home/ubuntu/Desktop/MyCodeAI-IDE && PYTHONPATH=. python3 -m agent.core.server');
                }
            });
        }
    });
}
function deactivate() { }
//# sourceMappingURL=extension.js.map
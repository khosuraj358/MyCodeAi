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
exports.AgentPanelProvider = void 0;
const vscode = __importStar(require("vscode"));
const agentPanelHtml_1 = require("../webviews/agentPanelHtml");
class AgentPanelProvider {
    constructor(_extensionUri, _client) {
        this._extensionUri = _extensionUri;
        this._client = _client;
    }
    resolveWebviewView(webviewView, _ctx, _token) {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };
        webviewView.webview.html = (0, agentPanelHtml_1.getAgentPanelHtml)();
        webviewView.webview.onDidReceiveMessage(async (msg) => {
            switch (msg.type) {
                case "ready":
                    await this._onReady();
                    break;
                case "chat":
                    await this._handleChat(msg);
                    break;
                case "newSession":
                    this._sessionId = undefined;
                    break;
                case "setModel":
                    this._currentModel = msg.model;
                    break;
                case "attachFile":
                    await this._pickAndAttachFile();
                    break;
                case "attachImage":
                    await this._pickAndAttachImage();
                    break;
                case "newSpec":
                    vscode.commands.executeCommand("mycodeai.newSpec");
                    break;
                case "approve":
                    vscode.commands.executeCommand("mycodeai.approvePhase");
                    break;
                case "runTask":
                    vscode.commands.executeCommand("mycodeai.runNextTask");
                    break;
                case "checkpoint":
                    vscode.commands.executeCommand("mycodeai.checkpoint");
                    break;
                case "openFile":
                    await this._openFile(msg.path);
                    break;
            }
        });
    }
    // ── Init ──────────────────────────────────────────────────────────────────
    async _onReady() {
        const online = await this._client.health();
        this._post({ type: "serverStatus", online });
        if (!online)
            return;
        const models = await this._client.listModels().catch(() => []);
        this._post({ type: "models", models });
        // Default to "Auto" — let the router pick the best model per query.
        // Only override when the user explicitly selects a model from the dropdown.
        if (models.length && !this._currentModel) {
            this._currentModel = "";
        }
        // Show RAM status — which models can run right now
        const ram = await this._client.getRam().catch(() => null);
        if (ram) {
            this._post({
                type: "ramStatus",
                available: ram.available_ram_gb,
                canRun: (ram.can_run || []).map((m) => m.model),
                tooBig: (ram.too_big_for_ram || []).map((m) => m.model),
            });
        }
    }
    // ── Chat handler ──────────────────────────────────────────────────────────
    async _handleChat(msg) {
        const text = msg.text ?? "";
        const attachedFile = msg.attachedFile ?? "";
        const attachedImage = msg.attachedImage ?? "";
        const modelOverride = msg.model ?? "";
        if (!text.trim() && !attachedFile && !attachedImage)
            return;
        const model = modelOverride || this._currentModel;
        // Resolve the absolute path for any attachment
        let absolutePath;
        const attachment = attachedImage || attachedFile;
        if (attachment) {
            if (attachment.startsWith("/") || attachment.startsWith("~")) {
                absolutePath = attachment.replace(/^~/, require("os").homedir());
            }
            else {
                const folders = require("vscode").workspace.workspaceFolders;
                if (folders?.length) {
                    absolutePath = require("path").join(folders[0].uri.fsPath, attachment);
                }
            }
        }
        // The open workspace folder — the agent should write files here by default
        const folders = vscode.workspace.workspaceFolders;
        const workspace = folders?.length ? folders[0].uri.fsPath : undefined;
        this._post({ type: "streamStart", workspace });
        try {
            await this._streamSSE(text || "Analyze this", model, absolutePath, workspace);
        }
        catch (e) {
            this._post({ type: "streamError", text: `${e.message ?? e}` });
        }
    }
    // ── SSE streaming — passes file_path to server for image/PDF handling ──────
    _streamSSE(prompt, model, filePath, workspace) {
        const params = new URLSearchParams({ message: prompt });
        if (this._sessionId)
            params.set("session_id", this._sessionId);
        if (model)
            params.set("model", model);
        if (filePath)
            params.set("file_path", filePath);
        if (workspace)
            params.set("workspace", workspace);
        const url = `${this._client.baseUrl}/chat/stream?${params}`;
        const http = url.startsWith("https") ? require("https") : require("http");
        return new Promise((resolve, reject) => {
            const req = http.get(url, (res) => {
                res.setEncoding("utf8");
                let buf = "";
                res.on("data", (chunk) => {
                    buf += chunk;
                    const frames = buf.split("\n\n");
                    buf = frames.pop() ?? "";
                    for (const frame of frames) {
                        for (const line of frame.split("\n")) {
                            if (!line.startsWith("data:"))
                                continue;
                            const payload = line.slice(5).trim();
                            if (!payload || payload === "[DONE]")
                                continue;
                            try {
                                const ev = JSON.parse(payload);
                                this._handleEvent(ev);
                            }
                            catch {
                                /* skip */
                            }
                        }
                    }
                });
                res.on("end", resolve);
                res.on("error", reject);
            });
            req.on("error", reject);
            req.setTimeout(600000, () => {
                req.destroy();
                reject(new Error("Stream timeout"));
            });
        });
    }
    _handleEvent(ev) {
        switch (ev.type) {
            case "model_selected":
                this._post({
                    type: "model_selected",
                    model: ev.model,
                    reason: ev.reason,
                    agent: ev.agent,
                    intent: ev.intent,
                    via: ev.via,
                });
                break;
            case "token":
                this._post({ type: "streamToken", token: ev.content });
                break;
            case "status":
                this._post({ type: "agentStatus", text: ev.text });
                break;
            case "tool_call":
                this._post({ type: "toolCall", name: ev.name, args: ev.args });
                break;
            case "tool_result":
                this._post({
                    type: "toolResult",
                    name: ev.name,
                    output: ev.output,
                    error: ev.error,
                });
                break;
            case "file_created":
                this._post({ type: "fileCreated", path: ev.path });
                // Refresh the VS Code file explorer
                vscode.commands.executeCommand("workbench.files.action.refreshFilesExplorer");
                // Optionally open the new file in the editor
                this._openFile(ev.path).catch(() => { });
                break;
            case "file_edited":
                this._post({ type: "fileEdited", path: ev.path });
                vscode.commands.executeCommand("workbench.files.action.refreshFilesExplorer");
                break;
            case "command_run":
                this._post({
                    type: "commandRun",
                    command: ev.command,
                    exitCode: ev.exit_code,
                    output: ev.output,
                });
                break;
            case "todo_update":
                this._post({ type: "todo_update", items: ev.items });
                break;
            case "summary":
                this._post({
                    type: "summary",
                    filesCreated: ev.files_created,
                    filesEdited: ev.files_edited,
                    filesDeleted: ev.files_deleted,
                    commandsRun: ev.commands_run,
                });
                break;
            case "done":
                this._sessionId = ev.session_id;
                this._post({ type: "streamEnd", sessionId: ev.session_id });
                break;
            case "error":
                this._post({ type: "streamError", text: ev.message });
                break;
        }
    }
    // ── Open a file in the editor ─────────────────────────────────────────────
    async _openFile(filePath) {
        if (!filePath)
            return;
        try {
            const uri = vscode.Uri.file(filePath);
            await vscode.workspace.fs.stat(uri); // confirm it exists
            await vscode.window.showTextDocument(uri, {
                preview: false,
                preserveFocus: true,
            });
        }
        catch {
            /* file may not exist yet */
        }
    }
    // ── File / image pickers ──────────────────────────────────────────────────
    async _pickAndAttachFile() {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            this._post({
                type: "fileAttached",
                name: vscode.workspace.asRelativePath(editor.document.uri),
            });
            return;
        }
        const uris = await vscode.window.showOpenDialog({
            canSelectMany: false,
            openLabel: "Attach file",
            filters: {
                "Code & Text": [
                    "py",
                    "ts",
                    "js",
                    "tsx",
                    "jsx",
                    "dart",
                    "go",
                    "rs",
                    "java",
                    "kt",
                    "swift",
                    "c",
                    "cpp",
                    "h",
                    "cs",
                    "rb",
                    "php",
                    "sh",
                    "md",
                    "txt",
                    "json",
                    "yaml",
                    "toml",
                ],
                All: ["*"],
            },
        });
        if (uris?.length)
            this._post({
                type: "fileAttached",
                name: vscode.workspace.asRelativePath(uris[0]),
            });
    }
    async _pickAndAttachImage() {
        const uris = await vscode.window.showOpenDialog({
            canSelectMany: false,
            openLabel: "Attach image",
            filters: { Images: ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"] },
        });
        if (!uris?.length)
            return;
        const rel = vscode.workspace.asRelativePath(uris[0]);
        try {
            const bytes = await vscode.workspace.fs.readFile(uris[0]);
            const b64 = Buffer.from(bytes).toString("base64");
            const ext = rel.split(".").pop() ?? "png";
            this._post({
                type: "imageAttached",
                name: rel,
                dataUrl: `data:image/${ext};base64,${b64}`,
            });
        }
        catch {
            this._post({ type: "imageAttached", name: rel, dataUrl: "" });
        }
    }
    async _readFile(rel) {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders)
            return null;
        try {
            const uri = vscode.Uri.joinPath(folders[0].uri, rel);
            const bytes = await vscode.workspace.fs.readFile(uri);
            return Buffer.from(bytes).toString("utf8");
        }
        catch {
            return null;
        }
    }
    _post(message) {
        this._view?.webview.postMessage(message);
    }
    notify(message) {
        this._post(message);
    }
}
exports.AgentPanelProvider = AgentPanelProvider;
AgentPanelProvider.viewType = "mycodeai.agentPanel";
//# sourceMappingURL=AgentPanelProvider.js.map
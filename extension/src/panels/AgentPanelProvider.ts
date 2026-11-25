import * as vscode from "vscode";
import { AgentClient } from "../AgentClient";
import { getAgentPanelHtml } from "../webviews/agentPanelHtml";

export class AgentPanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "mycodeai.agentPanel";
  private _view?: vscode.WebviewView;
  private _sessionId?: string;
  private _currentModel?: string;

  constructor(
    private readonly _extensionUri: vscode.Uri,
    private readonly _client: AgentClient,
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _ctx: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ) {
    this._view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };
    webviewView.webview.html = getAgentPanelHtml();

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
  private async _onReady() {
    const online = await this._client.health();
    this._post({ type: "serverStatus", online });
    if (!online) return;

    const models = await this._client.listModels().catch(() => [] as string[]);
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
        canRun: (ram.can_run || []).map((m: any) => m.model),
        tooBig: (ram.too_big_for_ram || []).map((m: any) => m.model),
      });
    }
  }

  // ── Chat handler ──────────────────────────────────────────────────────────
  private async _handleChat(msg: any) {
    const text: string = msg.text ?? "";
    const attachedFile: string = msg.attachedFile ?? "";
    const attachedImage: string = msg.attachedImage ?? "";
    const modelOverride: string = msg.model ?? "";

    if (!text.trim() && !attachedFile && !attachedImage) return;

    const model = modelOverride || this._currentModel;

    // Resolve the absolute path for any attachment
    let absolutePath: string | undefined;
    const attachment = attachedImage || attachedFile;

    if (attachment) {
      if (attachment.startsWith("/") || attachment.startsWith("~")) {
        absolutePath = attachment.replace(/^~/, require("os").homedir());
      } else {
        const folders = require("vscode").workspace.workspaceFolders;
        if (folders?.length) {
          absolutePath = require("path").join(
            folders[0].uri.fsPath,
            attachment,
          );
        }
      }
    }

    // The open workspace folder — the agent should write files here by default
    const folders = vscode.workspace.workspaceFolders;
    const workspace = folders?.length ? folders[0].uri.fsPath : undefined;

    this._post({ type: "streamStart", workspace });
    try {
      await this._streamSSE(text || "Analyze this", model, absolutePath, workspace);
    } catch (e: any) {
      this._post({ type: "streamError", text: `${e.message ?? e}` });
    }
  }

  // ── SSE streaming — passes file_path to server for image/PDF handling ──────
  private _streamSSE(
    prompt: string,
    model?: string,
    filePath?: string,
    workspace?: string,
  ): Promise<void> {
    const params = new URLSearchParams({ message: prompt });
    if (this._sessionId) params.set("session_id", this._sessionId);
    if (model) params.set("model", model);
    if (filePath) params.set("file_path", filePath);
    if (workspace) params.set("workspace", workspace);
    const url = `${this._client.baseUrl}/chat/stream?${params}`;

    const http = url.startsWith("https") ? require("https") : require("http");

    return new Promise<void>((resolve, reject) => {
      const req = http.get(url, (res: any) => {
        res.setEncoding("utf8");
        let buf = "";

        res.on("data", (chunk: string) => {
          buf += chunk;
          const frames = buf.split("\n\n");
          buf = frames.pop() ?? "";

          for (const frame of frames) {
            for (const line of frame.split("\n")) {
              if (!line.startsWith("data:")) continue;
              const payload = line.slice(5).trim();
              if (!payload || payload === "[DONE]") continue;
              try {
                const ev = JSON.parse(payload);
                this._handleEvent(ev);
              } catch {
                /* skip */
              }
            }
          }
        });

        res.on("end", resolve);
        res.on("error", reject);
      });

      req.on("error", reject);
      req.setTimeout(600_000, () => {
        req.destroy();
        reject(new Error("Stream timeout"));
      });
    });
  }

  private _handleEvent(ev: any) {
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
        vscode.commands.executeCommand(
          "workbench.files.action.refreshFilesExplorer",
        );
        // Optionally open the new file in the editor
        this._openFile(ev.path).catch(() => {});
        break;

      case "file_edited":
        this._post({ type: "fileEdited", path: ev.path });
        vscode.commands.executeCommand(
          "workbench.files.action.refreshFilesExplorer",
        );
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
  private async _openFile(filePath: string) {
    if (!filePath) return;
    try {
      const uri = vscode.Uri.file(filePath);
      await vscode.workspace.fs.stat(uri); // confirm it exists
      await vscode.window.showTextDocument(uri, {
        preview: false,
        preserveFocus: true,
      });
    } catch {
      /* file may not exist yet */
    }
  }

  // ── File / image pickers ──────────────────────────────────────────────────
  private async _pickAndAttachFile() {
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

  private async _pickAndAttachImage() {
    const uris = await vscode.window.showOpenDialog({
      canSelectMany: false,
      openLabel: "Attach image",
      filters: { Images: ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"] },
    });
    if (!uris?.length) return;
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
    } catch {
      this._post({ type: "imageAttached", name: rel, dataUrl: "" });
    }
  }

  private async _readFile(rel: string): Promise<string | null> {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders) return null;
    try {
      const uri = vscode.Uri.joinPath(folders[0].uri, rel);
      const bytes = await vscode.workspace.fs.readFile(uri);
      return Buffer.from(bytes).toString("utf8");
    } catch {
      return null;
    }
  }

  private _post(message: Record<string, unknown>) {
    this._view?.webview.postMessage(message);
  }
  public notify(message: Record<string, unknown>) {
    this._post(message);
  }
}

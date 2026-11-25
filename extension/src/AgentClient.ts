/**
 * AgentClient — HTTP client that talks to the Python FastAPI agent server.
 * All methods map 1:1 to server endpoints.
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  session_id: string;
  message: ChatMessage;
}

export interface SpecSummary {
  id: string;
  name: string;
  goal: string;
  phase: string;
  created_at: string;
}

export interface SpecTask {
  id: string;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped";
  dependencies: string[];
  files_modified: string[];
  checkpoint_sha?: string;
}

export interface SpecDetail {
  id: string;
  name: string;
  goal: string;
  phase: string;
  requirements_md: string;
  design_md: string;
  tasks: SpecTask[];
  created_at: string;
  updated_at: string;
}

export interface TaskRunResult {
  task_id?: string;
  status: string;
  summary?: string;
  files?: string[];
}

export class AgentClient {
  public readonly baseUrl: string;

  constructor(baseUrl: string = "http://127.0.0.1:8765") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async health(): Promise<boolean> {
    try {
      const r = await fetch(`${this.baseUrl}/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return r.ok;
    } catch {
      return false;
    }
  }

  async listModels(): Promise<string[]> {
    const r = await this._get("/models");
    return r.models ?? [];
  }

  // ── Chat ─────────────────────────────────────────────────────────────────

  async chat(
    message: string,
    sessionId?: string,
    specId?: string,
    model?: string,
  ): Promise<ChatResponse> {
    return this._post("/chat", {
      message,
      session_id: sessionId,
      spec_id: specId,
      model,
    });
  }

  // ── Specs ─────────────────────────────────────────────────────────────────

  async createSpec(goal: string, name?: string): Promise<SpecDetail> {
    return this._post("/spec", { goal, name });
  }

  async listSpecs(): Promise<SpecSummary[]> {
    return this._get("/specs");
  }

  async getSpec(specId: string): Promise<SpecDetail> {
    return this._get(`/spec/${specId}`);
  }

  async approvePhase(
    specId: string,
    approved: boolean = true,
    feedback: string = "",
  ): Promise<SpecDetail> {
    return this._post("/spec/advance", { spec_id: specId, approved, feedback });
  }

  async runNextTask(specId: string): Promise<TaskRunResult> {
    return this._post("/task/run", { spec_id: specId });
  }

  // ── Git ───────────────────────────────────────────────────────────────────

  async checkpoint(message: string): Promise<{ sha: string; message: string }> {
    return this._post(
      "/checkpoint",
      undefined,
      `?message=${encodeURIComponent(message)}`,
    );
  }

  // ── Sessions ──────────────────────────────────────────────────────────────

  async listSessions(): Promise<
    { id: string; spec_id: string; created_at: string }[]
  > {
    return this._get("/sessions");
  }

  // ── WebSocket URL for streaming ───────────────────────────────────────────
  wsUrl(sessionId?: string): string {
    const wsBase = this.baseUrl.replace(/^http/, "ws");
    const sid = sessionId ?? "new";
    return `${wsBase}/ws/${sid}`;
  }

  // ── Context / RAM status ──────────────────────────────────────────────────
  async getContext(sessionId?: string): Promise<{ context: string }> {
    const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
    return this._get(`/context${qs}`);
  }

  async getRam(): Promise<{
    available_ram_gb: number;
    can_run: any[];
    too_big_for_ram: any[];
  }> {
    return this._get("/ram");
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private async _get(path: string): Promise<any> {
    const r = await fetch(`${this.baseUrl}${path}`);
    if (!r.ok) {
      throw new Error(`GET ${path} → ${r.status} ${r.statusText}`);
    }
    return r.json();
  }

  private async _post(
    path: string,
    body?: any,
    queryString: string = "",
  ): Promise<any> {
    const r = await fetch(`${this.baseUrl}${path}${queryString}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`POST ${path} → ${r.status}: ${text}`);
    }
    return r.json();
  }
}

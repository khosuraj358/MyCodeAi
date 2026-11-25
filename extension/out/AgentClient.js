"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.AgentClient = void 0;
class AgentClient {
    constructor(baseUrl = "http://127.0.0.1:8765") {
        this.baseUrl = baseUrl.replace(/\/$/, "");
    }
    async health() {
        try {
            const r = await fetch(`${this.baseUrl}/health`, {
                signal: AbortSignal.timeout(3000),
            });
            return r.ok;
        }
        catch {
            return false;
        }
    }
    async listModels() {
        const r = await this._get("/models");
        return r.models ?? [];
    }
    // ── Chat ─────────────────────────────────────────────────────────────────
    async chat(message, sessionId, specId, model) {
        return this._post("/chat", {
            message,
            session_id: sessionId,
            spec_id: specId,
            model,
        });
    }
    // ── Specs ─────────────────────────────────────────────────────────────────
    async createSpec(goal, name) {
        return this._post("/spec", { goal, name });
    }
    async listSpecs() {
        return this._get("/specs");
    }
    async getSpec(specId) {
        return this._get(`/spec/${specId}`);
    }
    async approvePhase(specId, approved = true, feedback = "") {
        return this._post("/spec/advance", { spec_id: specId, approved, feedback });
    }
    async runNextTask(specId) {
        return this._post("/task/run", { spec_id: specId });
    }
    // ── Git ───────────────────────────────────────────────────────────────────
    async checkpoint(message) {
        return this._post("/checkpoint", undefined, `?message=${encodeURIComponent(message)}`);
    }
    // ── Sessions ──────────────────────────────────────────────────────────────
    async listSessions() {
        return this._get("/sessions");
    }
    // ── WebSocket URL for streaming ───────────────────────────────────────────
    wsUrl(sessionId) {
        const wsBase = this.baseUrl.replace(/^http/, "ws");
        const sid = sessionId ?? "new";
        return `${wsBase}/ws/${sid}`;
    }
    // ── Context / RAM status ──────────────────────────────────────────────────
    async getContext(sessionId) {
        const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
        return this._get(`/context${qs}`);
    }
    async getRam() {
        return this._get("/ram");
    }
    // ── Helpers ───────────────────────────────────────────────────────────────
    async _get(path) {
        const r = await fetch(`${this.baseUrl}${path}`);
        if (!r.ok) {
            throw new Error(`GET ${path} → ${r.status} ${r.statusText}`);
        }
        return r.json();
    }
    async _post(path, body, queryString = "") {
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
exports.AgentClient = AgentClient;
//# sourceMappingURL=AgentClient.js.map
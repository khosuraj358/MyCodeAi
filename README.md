# MyCodeAI IDE

A fully local, open-source AI coding IDE inspired by Other IDE's workflow. No API keys, no cloud, no monthly quota.

## Core Philosophy

**Spec → Plan → Tasks → Code → Test → Review → Checkpoint**

The agent never jumps straight to writing code. It first creates requirements, then a design, then a task breakdown — then implements one task at a time with validation at each step.

## Features

| Kiro Feature | MyCodeAI Equivalent |
|---|---|
| Spec-driven development | Requirements → Design → Tasks → Implementation |
| Agentic coding | Read, write, edit, execute, test via tool harness |
| Steering files | `./steering/*.md` — project rules and standards |
| Custom agents | Developer, Planner, Reviewer, Debugger roles |
| Hooks | Auto-actions on save, task complete, test pass |
| Checkpoint / rewind | Git-based snapshots with restore |
| Context compaction | Session summarisation for long runs |
| Agent permissions | Allow / Deny / Ask per tool |
| Sub-agents | Delegate tasks to specialised agent roles |
| Project memory | SQLite-backed local index |

## Stack

- **VSCodium / VS Code** — IDE frontend (extension)
- **Python 3.11+** — Agent orchestration engine
- **Ollama** — Local LLM inference
- **SQLite** — Task and session memory
- **Git** — Checkpoints and rewind
- **Qwen2.5-Coder / Deepseek-Coder** — Default coding models

## Quick Start

```bash
# 1. Install Ollama and pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# 2. Install Python dependencies
cd agent && pip install -r requirements.txt

# 3. Start the agent server
python -m core.server

# 4. Install the VS Code extension
cd extension && npm install && npm run compile
# Then press F5 in VS Code to launch the extension host
```

## Project Structure

```
MyCodeAI-IDE/
├── agent/                  # Python orchestration engine
│   ├── core/               # Server, session manager, context engine
│   ├── tools/              # File, shell, git, search tools
│   ├── agents/             # Planner, Developer, Reviewer, Debugger
│   ├── memory/             # SQLite task + session memory
│   ├── hooks/              # Hook runner and event system
│   ├── permissions/        # Tool permission manager
│   └── compaction/         # Context compaction / summarisation
├── extension/              # VS Code extension (TypeScript)
│   └── src/
│       ├── panels/         # Spec panel, agent panel, activity panel
│       ├── commands/       # Command palette entries
│       ├── providers/      # Tree view, status bar providers
│       └── webviews/       # Spec editor, task board webviews
├── specs/                  # Spec templates and examples
├── steering/               # Default steering file templates
├── docs/                   # Architecture and usage docs
└── scripts/                # Install, setup, dev scripts
```

## Spec-Driven Workflow

When you type a goal like "Build an Android document scanner":

1. **Requirements phase** — Agent produces `specs/<name>/requirements.md`
2. **Design phase** — Agent produces `specs/<name>/design.md`
3. **Tasks phase** — Agent produces `specs/<name>/tasks.md` with numbered, dependent tasks
4. **Implementation** — Agent works through tasks one-by-one, committing after each
5. **Review** — Reviewer agent checks each completed task
6. **Checkpoint** — Git tag created at each milestone

You approve each phase before the next begins.

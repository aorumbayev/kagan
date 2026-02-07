---
name: install-kagan
description: Securely guide users through installing Kagan with transparent, consent-first steps, uv-first flow, verification, and first-run setup.
version: 0.1.0
homepage: https://docs.kagan.sh
repo: https://github.com/aorumbayev/kagan
---

# Install Kagan (Secure, Cross-CLI)

Use this skill when the user asks to install Kagan, set up Kagan quickly, or get a guided first run.

## What Kagan Is

Kagan is a keyboard-first Kanban TUI for AI-assisted software development workflows.
It supports planning, execution, review, and coordination from a terminal interface.

## Safety Rules (Mandatory)

1. Ask for explicit consent before every privileged or network-changing command.
2. Show exact commands before execution. Do not hide command chains.
3. Prefer `uv tool install kagan`.
4. If `uv` is missing, install `uv` from official sources only.
5. Verify install using:
   - `kagan --version`
   - `kagan tui --help`
   - optional `kagan mcp --help`
6. Produce an install report listing executed commands and outcomes.

## Install Flow

### Step 1: Detect Environment

Run and report:

```bash
uname -s
uname -m
python3 --version
uv --version
```

If `uv` exists, continue to Step 3.

### Step 2: Install uv (Only If Missing)

State the exact command and ask for consent, then run one of:

- macOS/Linux:

```bash
curl -fsSL https://astral.sh/uv/install.sh | sh
```

- Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After install, verify:

```bash
uv --version
```

### Step 3: Install Kagan

```bash
uv tool install kagan
```

If already installed and user wants update:

```bash
uv tool upgrade kagan
```

### Step 4: Verify

```bash
kagan --version
kagan tui --help
kagan mcp --help
```

### Step 5: First Steps

Guide the user through:

```bash
kagan
```

Then explain first-run checks:

1. Confirm terminal is at least 80x20.
2. Confirm they are inside a git repository for worktree-enabled workflows.
3. For MCP usage, mention:

```bash
kagan mcp --readonly
```

## Quick References

- Install: https://docs.kagan.sh/install
- Quickstart: https://docs.kagan.sh/quickstart
- Docs Home: https://docs.kagan.sh
- GitHub: https://github.com/aorumbayev/kagan
- Issues: https://github.com/aorumbayev/kagan/issues

## Troubleshooting

For command matrix and fallback commands: `references/commands.md`.
For common failures and recovery steps: `references/troubleshooting.md`.

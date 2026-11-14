# Context Engine Specification: CodeMind CLI

## 1. Problem Statement

A naive agent loads entire codebases into prompts, quickly exhausting the model's context window, increasing latency, and introducing distraction. CodeMind CLI's Context Engine assembles bounded, relevant context tailored to the user's specific request.

---

## 2. Context Retrieval Pipeline

```text
[Workspace Root]
       │
       ▼
[1. Project Discovery]
       Identify repository type (Python, Node, Rust, Go, etc.),
       build configuration (pyproject.toml, package.json, Cargo.toml),
       and standard documentation (README.md, CONTRIBUTING.md).
       │
       ▼
[2. Ignore & Shield Filter]
       Filter files using:
       - .gitignore patterns
       - .codemindignore patterns
       - Built-in sensitive patterns (.env, *.pem, *.key, id_rsa, secrets.yaml)
       - Build and cache directories (__pycache__, node_modules, target, .git)
       │
       ▼
[3. File Tree Summarization]
       Generate compact hierarchical view of significant project directories.
       │
       ▼
[4. Targeted Excerpt Retrieval]
       Fetch requested or relevant file slices with line numbers and source citations.
       │
       ▼
[5. Context Budget Allocator]
       Enforce strict character/token ceilings per prompt section:
       - System instructions: 15%
       - Project summary & tree: 20%
       - Excerpts & relevant docs: 35%
       - Conversation & recent observations: 30%
```

---

## 3. Secret Exclusion & Shielding

The context engine will never inject matching secret files or credential patterns into prompt context:
- Environment files: `.env`, `.env.*`, `*.env`
- Private keys: `id_rsa`, `id_ed25519`, `*.pem`, `*.key`
- Credentials: `credentials.json`, `token.json`, `auth.json`
- In-memory redaction: Regex scanners redact inline API keys (`sk-[a-zA-Z0-9]{32,}`, `ghp_[a-zA-Z0-9]{36}`) from all tool observations before they enter prompt context.

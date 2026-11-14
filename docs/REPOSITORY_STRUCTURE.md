# Repository Structure: CodeMind CLI

```text
codemind-cli/
├── README.md                           # Product overview & quickstart
├── pyproject.toml                      # Package definitions and dependencies
├── run_tests.py                        # Hermetic offline test runner
├── docs/                               # Complete architecture & design specs
│   ├── PRODUCT_VISION.md
│   ├── SYSTEM_ARCHITECTURE.md
│   ├── AGENT_LOOP.md
│   ├── MODEL_ADAPTER.md
│   ├── CONTEXT_ENGINE.md
│   ├── TOOL_SYSTEM.md
│   ├── SECURITY.md
│   ├── SESSIONS_AND_MEMORY.md
│   ├── SKILLS.md
│   ├── MCP_INTEGRATION.md
│   ├── VERIFICATION.md
│   ├── CLI_UX.md
│   ├── MASCOT_BRANDING.md
│   ├── REPOSITORY_STRUCTURE.md
│   ├── IMPLEMENTATION_ROADMAP.md
│   ├── EVALUATION.md
│   └── WORKFLOW_EXAMPLES.md
├── src/
│   └── codemind/
│       ├── __init__.py                 # Version & public export
│       ├── config.py                   # Pydantic v2 application settings
│       ├── cli/                        # Terminal user interface
│       │   ├── __init__.py
│       │   ├── main.py                 # Typer command entry points
│       │   ├── ui.py                   # Rich rendering & formatters
│       │   └── branding.py             # Banner & Milo prompts
│       ├── models/                     # Model adapters & protocol
│       │   ├── __init__.py
│       │   ├── base.py                 # Abstract ModelAdapter & CapabilityProfile
│       │   ├── codemind_local.py       # OpenAI-compatible local server adapter
│       │   ├── ollama.py               # Native Ollama API adapter
│       │   ├── mock.py                 # Offline deterministic test adapter
│       │   └── protocol.py             # Versioned envelope parser & validator
│       ├── runtime/                    # Core agent orchestration
│       │   ├── __init__.py
│       │   ├── agent.py                # High-level CodeMindAgent
│       │   ├── loop.py                 # Bounded turn executor
│       │   ├── events.py               # Agent event dispatching
│       │   └── state.py                # Runtime context & turn history
│       ├── security/                   # Sandboxing & permissions
│       │   ├── __init__.py
│       │   ├── permissions.py          # Mode & policy checkers
│       │   ├── sandbox.py              # Path traversal & symlink shield
│       │   └── redaction.py            # Secret & API key masking
│       ├── tools/                      # Tool implementations
│       │   ├── __init__.py
│       │   ├── base.py                 # BaseTool contract & ToolResult
│       │   ├── registry.py             # Tool collection & lookup
│       │   ├── filesystem.py           # read_file, list_dir, create_file
│       │   ├── search.py               # search_files, search_text
│       │   ├── patch.py                # apply_patch with diff preview
│       │   ├── terminal.py             # run_command with sandbox
│       │   └── git.py                  # git_status, git_diff, git_log
│       ├── context/                    # Context retrieval & management
│       │   ├── __init__.py
│       │   ├── discovery.py            # Project type & manifest analysis
│       │   ├── ignore.py               # Ignore rules (.gitignore, .codemindignore)
│       │   └── budget.py               # Token & character window allocator
│       ├── planning/                   # Structured task plans
│       │   ├── __init__.py
│       │   ├── task.py                 # TaskItem, TaskStatus, TaskDAG
│       │   └── planner.py              # Plan authoring and transitions
│       ├── sessions/                   # Session persistence
│       │   ├── __init__.py
│       │   ├── store.py                # Disk serialization (.codemind/sessions/)
│       │   └── manager.py              # Checkpointing & resumption
│       ├── memory/                     # Project memory store
│       │   ├── __init__.py
│       │   └── store.py                # Scoped facts (.codemind/memory/)
│       ├── verification/               # Test discovery & validation
│       │   ├── __init__.py
│       │   ├── runner.py               # Automated test execution
│       │   └── reporter.py             # Honest completion report generator
│       ├── skills/                     # Skill loader & registry
│       │   ├── __init__.py
│       │   └── loader.py               # SKILL.md scanner & matcher
│       └── telemetry/                  # Event tracing & audits
│           ├── __init__.py
│           └── trace.py                # Redacted event stream logging
├── tests/
│   ├── __init__.py
│   ├── base.py                         # Test fixtures & temp workspace
│   ├── unit/                           # Isolated component tests
│   │   ├── test_cli.py
│   │   ├── test_config.py
│   │   ├── test_protocol.py
│   │   ├── test_models.py
│   │   ├── test_sandbox.py
│   │   ├── test_redaction.py
│   │   ├── test_tools.py
│   │   ├── test_context.py
│   │   ├── test_planner.py
│   │   └── test_sessions.py
│   ├── integration/                    # Multi-component interaction tests
│   │   ├── test_agent_loop.py
│   │   └── test_verification.py
│   └── security/                       # Dedicated safety & boundary tests
│       ├── test_traversal_prevention.py
│       └── test_secret_shield.py
└── examples/
    └── sample_project/                 # Sample project for demo/testing
```

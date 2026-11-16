"""Interactive REPL engine powered by prompt_toolkit (Phase C Workstream G & H).

Features:
- Persistent command history (~/.codemind/history or <workspace>/.codemind/history)
- Slash command auto-completion (/help, /status, /doctor, /models, etc.)
- Dynamic workspace-relative @file fuzzy auto-completion
- Clean Ctrl+C (cancel prompt) and Ctrl+D (exit) handling
- Graceful degradation to standard input() in non-interactive or plain modes
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from codemind.context.ignore import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_EXTS, IgnoreEngine

SLASH_COMMANDS = [
    ("/help", "Show comprehensive command guide and keybindings"),
    ("/status", "Display active session status, turn counts, and budget"),
    ("/doctor", "Run system, dependency, and model diagnostics"),
    ("/models", "List discovered local models and active provider"),
    ("/memory", "Inspect persistent SQLite project memory records"),
    ("/skills", "List available engineering skills and active selection"),
    ("/agents", "Display multi-agent worker roles and sidecar status"),
    ("/task", "Display the structured execution task plan"),
    ("/diff", "Show git working-tree status and uncommitted diffs"),
    ("/mcp", "Inspect and manage Model Context Protocol (MCP) servers"),
    ("/connectors", "Inspect, connect, and manage universal app connectors (YouTube, Gmail, Drive, etc.)"),
    ("/permissions", "Inspect active declarative security permission rules"),
    ("/compact", "Compact active conversation context to conserve tokens"),
    ("/resume", "Resume latest paused workflow task"),
    ("/clear", "Clear the terminal screen"),
    ("/exit", "Exit CodeMind companion"),
]


class CodeMindCompleter(Completer):
    """Auto-completer for slash commands and workspace-relative @file mentions."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.ignore_engine = IgnoreEngine(self.workspace_root)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        # 1. Slash command completion at start of line
        if text.startswith("/"):
            query = text.lower()
            for cmd, desc in SLASH_COMMANDS:
                if cmd.lower().startswith(query):
                    yield Completion(
                        text=cmd,
                        start_position=-len(text),
                        display=f"{cmd:12} : {desc}",
                    )
            return

        # 2. @file mention completion
        at_pos = text.rfind("@")
        if at_pos != -1:
            prefix = text[at_pos + 1 :].lower()
            # Scan workspace for matching relative files
            yielded = 0
            max_matches = 25

            for root, dirs, files in os.walk(self.workspace_root):
                # Filter ignored directories in-place
                dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORED_DIRS and not d.startswith(".")]

                for fname in files:
                    if any(fname.endswith(ext) for ext in DEFAULT_IGNORED_EXTS):
                        continue
                    full_p = Path(root) / fname
                    try:
                        rel_p = str(full_p.relative_to(self.workspace_root))
                    except ValueError:
                        continue

                    if self.ignore_engine.should_ignore(rel_p):
                        continue

                    if not prefix or prefix in rel_p.lower():
                        yield Completion(
                            text=f"@{rel_p}",
                            start_position=-(len(text) - at_pos),
                            display=f"@{rel_p}",
                        )
                        yielded += 1
                        if yielded >= max_matches:
                            return


class CodeMindInteractiveSession:
    """Manages the interactive terminal prompt session with history and completion."""

    def __init__(self, workspace_root: Path, plain_mode: bool = False):
        self.workspace_root = workspace_root.resolve()
        self.plain_mode = plain_mode

        history_dir = self.workspace_root / ".codemind"
        history_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = history_dir / "history"

        self.completer = CodeMindCompleter(self.workspace_root)
        self.style = Style.from_dict({
            "prompt": "bold #FF9E3B",
            "symbol": "#61AFEF",
        })

        try:
            self.session: PromptSession | None = PromptSession(
                history=FileHistory(str(self.history_file)),
                completer=self.completer,
                auto_suggest=AutoSuggestFromHistory(),
                style=self.style,
            )
        except Exception:
            self.session = None

    def prompt(self) -> str:
        """Prompt the user for input, using prompt_toolkit or falling back cleanly."""
        import sys
        if self.plain_mode or not self.session or not sys.stdin.isatty():
            symbol = "codemind> " if self.plain_mode else "▟●▙ > "
            return input(symbol).strip()

        try:
            return self.session.prompt([
                ("class:prompt", "▟●▙"),
                ("class:symbol", " > "),
            ]).strip()
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception:
            symbol = "codemind> " if self.plain_mode else "▟●▙ > "
            return input(symbol).strip()

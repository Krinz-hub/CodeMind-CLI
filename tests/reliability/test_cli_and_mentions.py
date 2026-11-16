"""Hermetic regression tests for CLI Ergonomics and File Mentions (Phase C).

Covers:
- REL-07: Interactive REPL, persistent history, auto-completion, and slash command dispatch
- REL-08: File mentions (@file), sandbox boundary validation, secret blocking, and context injection
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from prompt_toolkit.document import Document

from codemind.cli.main import handle_slash_command
from codemind.cli.repl import CodeMindCompleter, CodeMindInteractiveSession, SLASH_COMMANDS
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig
from codemind.context.mentions import FileMentionProcessor, MAX_MENTION_LINES
from codemind.runtime.agent import CodeMindAgent
from tests.base import BaseAgentTestCase


class TestCliAndMentions(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = CodeMindConfig.load(
            self.workspace_root,
            overrides={"plain_mode": True, "model": {"provider": "mock"}},
        )
        self.ui = TerminalUI(plain_mode=True)
        self.mention_processor = FileMentionProcessor(self.workspace_root)

    def test_extract_mentions_syntax(self) -> None:
        """Verify mention parser extracts valid paths and removes duplicates."""
        text = "Check @src/calc.py and review @tests/test_calc.py or @src/calc.py again."
        mentions = self.mention_processor.extract_mentions(text)
        self.assertEqual(mentions, ["src/calc.py", "tests/test_calc.py"])

    def test_mention_sandbox_boundary_enforcement(self) -> None:
        """Verify @mentions outside the authorized workspace are blocked."""
        text = "Inspect @../../secret/credentials.json now."
        augmented, contexts = self.mention_processor.process_mentions(text)
        self.assertEqual(len(contexts), 1)
        self.assertIn("Access blocked", contexts[0].warning or "")
        self.assertIn("outside the authorized workspace", contexts[0].warning or "")
        self.assertIn("Access blocked", augmented)

    def test_mention_secret_file_blocking(self) -> None:
        """Verify @mentions of sensitive and secret files are rejected."""
        self.create_file(".env", "DATABASE_PASSWORD=supersecret\n")
        text = "Read @.env configuration."
        augmented, contexts = self.mention_processor.process_mentions(text)
        self.assertEqual(len(contexts), 1)
        self.assertIn("Security violation", contexts[0].warning or "")
        self.assertIn("blocked", contexts[0].warning or "")
        self.assertNotIn("DATABASE_PASSWORD", augmented)

    def test_mention_missing_file_handling(self) -> None:
        """Verify mentioning non-existent files returns helpful warning without error."""
        text = "Analyze @src/nonexistent.py for errors."
        augmented, contexts = self.mention_processor.process_mentions(text)
        self.assertEqual(len(contexts), 1)
        self.assertIn("File not found", contexts[0].warning or "")
        self.assertIn("File not found", augmented)

    def test_mention_context_injection_and_budget_truncation(self) -> None:
        """Verify valid files are injected and large files are strictly truncated."""
        # 1. Normal file
        self.create_file("src/hello.py", "def hello():\n    return 'world'\n")
        text = "Please examine @src/hello.py"
        augmented, contexts = self.mention_processor.process_mentions(text)
        self.assertEqual(len(contexts), 1)
        self.assertFalse(contexts[0].truncated)
        self.assertEqual(contexts[0].line_count, 2)
        self.assertIn("--- INJECTED CONTEXT (FILE MENTIONS) ---", augmented)
        self.assertIn("def hello():", augmented)

        # 2. Large file exceeding MAX_MENTION_LINES
        long_content = "\n".join(f"line_{i} = {i}" for i in range(MAX_MENTION_LINES + 50))
        self.create_file("src/large.py", long_content)
        text_large = "Check @src/large.py please"
        augmented_large, contexts_large = self.mention_processor.process_mentions(text_large)
        self.assertEqual(len(contexts_large), 1)
        self.assertTrue(contexts_large[0].truncated)
        self.assertIn("truncated to budget", augmented_large)

    def test_completer_slash_commands(self) -> None:
        """Verify completer suggests all registered slash commands."""
        completer = CodeMindCompleter(self.workspace_root)
        doc = Document("/")
        completions = list(completer.get_completions(doc, MagicMock()))
        texts = [c.text for c in completions]
        for cmd, _ in SLASH_COMMANDS:
            self.assertIn(cmd, texts)

        # Prefix matching
        doc_pref = Document("/st")
        completions_pref = list(completer.get_completions(doc_pref, MagicMock()))
        pref_texts = [c.text for c in completions_pref]
        self.assertIn("/status", pref_texts)
        self.assertNotIn("/help", pref_texts)

    def test_completer_file_mentions(self) -> None:
        """Verify completer discovers workspace files on @ prefix."""
        self.create_file("src/component.tsx", "export const C = () => <div/>;")
        self.create_file("tests/test_comp.py", "def test(): pass")

        completer = CodeMindCompleter(self.workspace_root)
        doc = Document("Inspect @comp")
        completions = list(completer.get_completions(doc, MagicMock()))
        texts = [c.text for c in completions]
        self.assertTrue(any("component.tsx" in t for t in texts))

    def test_slash_command_dispatch(self) -> None:
        """Verify handle_slash_command dispatches core commands without error."""
        agent = CodeMindAgent(self.config, self.ui)
        asyncio.run(agent.initialize())

        # /exit
        handled, should_exit = asyncio.run(handle_slash_command("/exit", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertTrue(should_exit)

        # /status
        handled, should_exit = asyncio.run(handle_slash_command("/status", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /models
        handled, should_exit = asyncio.run(handle_slash_command("/models", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /memory
        handled, should_exit = asyncio.run(handle_slash_command("/memory", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /skills
        handled, should_exit = asyncio.run(handle_slash_command("/skills", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /agents
        handled, should_exit = asyncio.run(handle_slash_command("/agents", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /diff
        handled, should_exit = asyncio.run(handle_slash_command("/diff", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)

        # /budget 45
        handled, should_exit = asyncio.run(handle_slash_command("/budget 45", agent, self.config, self.ui))
        self.assertTrue(handled)
        self.assertFalse(should_exit)
        self.assertEqual(self.config.runtime.max_turns, 45)

        # non-command
        handled, should_exit = asyncio.run(handle_slash_command("Build a website", agent, self.config, self.ui))
        self.assertFalse(handled)
        self.assertFalse(should_exit)

    def test_interactive_session_fallback_mode(self) -> None:
        """Verify CodeMindInteractiveSession handles plain mode gracefully."""
        session = CodeMindInteractiveSession(self.workspace_root, plain_mode=True)
        with patch("builtins.input", return_value="hello test"):
            val = session.prompt()
            self.assertEqual(val, "hello test")

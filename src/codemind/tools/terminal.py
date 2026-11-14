"""Controlled terminal and subprocess execution tool."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionLevel
from codemind.security.redaction import redact_secrets
from codemind.security.sandbox import SecurityViolationError
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


class RunCommandInput(BaseModel):
    command: str = Field(description="Shell command line to execute")
    cwd: str = Field(default=".", description="Working directory relative to workspace root (default '.')")
    timeout_seconds: int = Field(default=60, description="Execution timeout in seconds")


class RunCommandTool(BaseTool):
    name = "run_command"
    description = (
        "Execute a terminal shell command within the workspace. "
        "Enforces working directory sandbox, execution timeouts, output capping, and approval."
    )
    permission_level = PermissionLevel.EXECUTE
    args_schema = RunCommandInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = RunCommandInput.model_validate(arguments)
            target_cwd = context.sandbox.validate_path_access(inp.cwd, is_write=False)
            if not target_cwd.is_dir():
                return ToolResult.error(f"Working directory does not exist: '{inp.cwd}'")

            # Check for banned or destructive patterns
            cmd_lower = inp.command.strip().lower()
            if cmd_lower.startswith("sudo ") or "rm -rf /" in cmd_lower or ":(){ :|:& };:" in cmd_lower:
                return ToolResult.error("Forbidden command pattern detected.", error_code="SECURITY_VIOLATION")

            # Show command preview to user if UI is active
            if context.ui and hasattr(context.ui, "print_command_preview"):
                rel_cwd = target_cwd.relative_to(context.workspace_root)
                context.ui.print_command_preview(inp.command, str(rel_cwd))

            timeout = min(inp.timeout_seconds, context.timeout_seconds)

            # Spawn process in new process group for clean cancellation
            process = await asyncio.create_subprocess_shell(
                inp.command,
                cwd=str(target_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=float(timeout),
                )
            except asyncio.TimeoutError:
                # Terminate entire process group
                if hasattr(os, "killpg"):
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except Exception:
                        process.kill()
                else:
                    process.kill()

                await process.wait()
                return ToolResult.error(
                    f"Command execution timed out after {timeout} seconds: '{inp.command}'",
                    error_code="TIMEOUT",
                    exit_code=-1,
                )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            # Redact sensitive secrets from outputs
            stdout_clean = redact_secrets(stdout_str)
            stderr_clean = redact_secrets(stderr_str)

            combined = ""
            if stdout_clean:
                combined += stdout_clean
            if stderr_clean:
                if combined:
                    combined += "\n[STDERR]\n"
                combined += stderr_clean

            truncated_output, is_trunc = context.truncate_output(combined)
            ok = exit_code == 0

            return ToolResult(
                ok=ok,
                content=truncated_output if truncated_output else f"(Command exited with code {exit_code})",
                stdout=stdout_clean,
                stderr=stderr_clean,
                exit_code=exit_code,
                truncated=is_trunc,
                metadata={"command": inp.command, "exit_code": exit_code},
            )

        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error executing command: {ex}")

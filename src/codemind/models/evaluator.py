"""Model capability and agent compatibility evaluation harness."""

from __future__ import annotations

import ast
import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from codemind.models.base import ChatMessage, ModelAdapter
from codemind.models.protocol import ProtocolParser, ToolCallAction


class ProbeResult(BaseModel):
    dimension: str
    passed: bool
    latency_seconds: float
    output_snippet: str
    details: str = ""


class CapabilityEvaluationResult(BaseModel):
    model_name: str
    provider: str
    endpoint: str
    connection_status: str = "Available"
    probes: list[ProbeResult] = Field(default_factory=list)
    compatibility_rating: str = "Evaluated"
    recommended_for_agent: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    def format_report(self) -> str:
        """Render a readable capability evaluation report."""
        lines = [
            f"Model: {self.model_name}",
            f"Provider: {self.provider} ({self.endpoint})",
            f"Connection: {self.connection_status}\n",
        ]

        for p in self.probes:
            status_str = "Passed" if p.passed else "Failed"
            lines.append(f"{p.dimension}: {status_str} ({p.latency_seconds:.2f}s)")
            if not p.passed and p.details:
                lines.append(f"  └─ Issue: {p.details}")

        lines.append(f"\nAgent Compatibility: {self.compatibility_rating}")
        rec = "Yes (Recommended for autonomous tasks)" if self.recommended_for_agent else "No (Limited agent support)"
        lines.append(f"Recommended for Agent Tasks: {rec}")

        return "\n".join(lines)


class ModelCapabilityTester:
    """Executes live, non-destructive capability benchmarks against a local model."""

    def __init__(self, adapter: ModelAdapter):
        self.adapter = adapter

    async def evaluate_all(self) -> CapabilityEvaluationResult:
        """Run the comprehensive 7-probe agent capability suite."""
        # 1. Connection check
        health = await self.adapter.check_health()
        if not health.healthy:
            return CapabilityEvaluationResult(
                model_name=self.adapter.model_name,
                provider=self.adapter.endpoint,
                endpoint=self.adapter.endpoint,
                connection_status=f"Failed ({health.error or 'Unreachable'})",
                compatibility_rating="Incompatible",
                recommended_for_agent=False,
            )

        probes: list[ProbeResult] = []

        # Probe 1: Instruction following
        p1 = await self._probe_instruction_following()
        probes.append(p1)

        # Probe 2: Structured JSON generation
        p2 = await self._probe_structured_json()
        probes.append(p2)

        # Probe 3: Tool-call formatting (Protocol v1)
        p3 = await self._probe_tool_calling()
        probes.append(p3)

        # Probe 4: Multi-step reasoning
        p4 = await self._probe_reasoning()
        probes.append(p4)

        # Probe 5: Context handling
        p5 = await self._probe_context_handling()
        probes.append(p5)

        # Probe 6: Code generation
        p6 = await self._probe_code_generation()
        probes.append(p6)

        # Probe 7: Error interpretation
        p7 = await self._probe_error_interpretation()
        probes.append(p7)

        # Calculate agent compatibility
        passed_dims = {p.dimension: p.passed for p in probes}
        tool_call_ok = passed_dims.get("Tool calling", False)
        json_ok = passed_dims.get("Structured JSON", False)
        instruct_ok = passed_dims.get("Instruction following", False)
        reason_ok = passed_dims.get("Multi-step reasoning", False)
        code_ok = passed_dims.get("Code generation", False)

        total_passed = sum(1 for p in probes if p.passed)

        if tool_call_ok and json_ok and (total_passed >= 6):
            rating = "Full (Autonomous agent ready)"
            recommended = True
        elif tool_call_ok and (json_ok or instruct_ok):
            rating = "High (Capable of structured agent cycles)"
            recommended = True
        elif json_ok:
            rating = "Partial (Structured output supported; tool calling may need retries)"
            recommended = False
        elif instruct_ok:
            rating = "Basic (Text generation only; limited agent capability)"
            recommended = False
        else:
            rating = "Incompatible (Failed core agent requirements)"
            recommended = False

        return CapabilityEvaluationResult(
            model_name=self.adapter.model_name,
            provider=type(self.adapter).__name__,
            endpoint=self.adapter.endpoint,
            connection_status="Available",
            probes=probes,
            compatibility_rating=rating,
            recommended_for_agent=recommended,
            details={"total_passed": total_passed, "total_probes": len(probes)},
        )

    async def _probe_instruction_following(self) -> ProbeResult:
        dim = "Instruction following"
        prompt = "Reply with the single exact token 'CODEMIND_OK' and absolutely nothing else."
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            passed = "CODEMIND_OK" in resp.content
            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details="" if passed else f"Token 'CODEMIND_OK' not found in: {resp.content[:100]}",
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_structured_json(self) -> ProbeResult:
        dim = "Structured JSON"
        prompt = (
            "Generate a valid JSON object with exact keys 'status' ('success') and 'code' (200). "
            "Output JSON only."
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            passed = False
            details = ""
            try:
                candidate = ProtocolParser._extract_json(resp.content)
                if candidate and candidate.get("status") == "success" and candidate.get("code") == 200:
                    passed = True
                else:
                    details = f"Parsed JSON did not match expected keys/values: {candidate}"
            except Exception as jerr:
                details = f"JSON decode failed: {jerr}"

            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details=details,
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_tool_calling(self) -> ProbeResult:
        dim = "Tool calling"
        prompt = (
            "You are Milo. Output a single JSON envelope to read 'src/main.py'.\n"
            "Format:\n"
            '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", '
            '"arguments": {"path": "src/main.py"}, "reason": "Inspect application entrypoint"}'
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate(
                [
                    ChatMessage(role="system", content="You are Milo, an AI agent. Emit protocol v1 envelopes."),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=1024,
            )
            elapsed = time.time() - t0
            action = ProtocolParser.parse(resp.content)
            passed = isinstance(action, ToolCallAction) and action.tool == "read_file" and action.arguments.get("path") == "src/main.py"
            details = "" if passed else f"Expected ToolCallAction for read_file, got: {type(action).__name__}"
            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details=details,
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_reasoning(self) -> ProbeResult:
        dim = "Multi-step reasoning"
        prompt = (
            "Given 3 modules: Alpha, Beta, and Gamma.\n"
            "Beta depends on Alpha.\n"
            "Gamma depends on Beta.\n"
            "Which module must be compiled first in the dependency order? "
            "End your answer with: COMPILED_FIRST: <name>."
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            content = resp.content.lower()
            passed = "compiled_first: alpha" in content or ("alpha" in content and "first" in content)
            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details="" if passed else "Correct compilation order was not identified",
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_context_handling(self) -> ProbeResult:
        dim = "Context handling"
        prompt = (
            "Context: The internal database port is 5432, redis port is 6379, and the backend auth secret port is 9988.\n"
            "Question: What is the backend auth secret port? Answer with the port number only."
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            passed = "9988" in resp.content
            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details="" if passed else f"Port 9988 not found in: {resp.content[:100]}",
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_code_generation(self) -> ProbeResult:
        dim = "Code generation"
        prompt = (
            "Write a Python function named `calculate_factorial(n: int) -> int` that computes the factorial of n. "
            "Output valid Python code only."
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            content = resp.content
            passed = False
            details = ""

            # Extract python code block if present
            code_to_parse = content
            if "```python" in content:
                code_to_parse = content.split("```python", 1)[1].split("```", 1)[0]
            elif "```" in content:
                code_to_parse = content.split("```", 1)[1].split("```", 1)[0]

            code_clean = code_to_parse.strip()
            if "def calculate_factorial" in code_clean:
                try:
                    ast.parse(code_clean)
                    passed = True
                except SyntaxError as syn_err:
                    details = f"Syntax error in generated code: {syn_err}"
            else:
                details = "Function 'def calculate_factorial' not found in response"

            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=content.strip()[:100],
                details=details,
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

    async def _probe_error_interpretation(self) -> ProbeResult:
        dim = "Error interpretation"
        prompt = (
            "Diagnose this error traceback:\n"
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 14, in <module>\n"
            "    users[5]\n"
            "IndexError: list index out of range\n\n"
            "What type of error occurred? State: 'ERROR_TYPE: <error>'."
        )
        t0 = time.time()
        try:
            resp = await self.adapter.generate([ChatMessage(role="user", content=prompt)], max_tokens=1024)
            elapsed = time.time() - t0
            passed = "indexerror" in resp.content.lower()
            return ProbeResult(
                dimension=dim,
                passed=passed,
                latency_seconds=elapsed,
                output_snippet=resp.content.strip()[:100],
                details="" if passed else "Failed to diagnose IndexError",
            )
        except Exception as ex:
            return ProbeResult(dimension=dim, passed=False, latency_seconds=time.time() - t0, output_snippet="", details=str(ex))

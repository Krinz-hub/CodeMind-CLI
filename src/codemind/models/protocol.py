"""Versioned agent response protocol and validation engine (v1)."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

CURRENT_PROTOCOL_VERSION = "1"


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    PLAN = "plan"
    FINAL = "final"
    MALFORMED = "malformed"


class ToolCallAction(BaseModel):
    protocol_version: str = CURRENT_PROTOCOL_VERSION
    type: Literal["tool_call"] = "tool_call"
    tool: str = Field(description="Name of tool to execute")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool invocation parameters")
    reason: str = Field(default="", description="Reasoning or motivation for calling this tool")


class TaskPlanItem(BaseModel):
    id: str
    title: str
    status: str = Field(default="pending", description="pending, in_progress, completed, failed, blocked, skipped")
    notes: str = ""


class PlanAction(BaseModel):
    protocol_version: str = CURRENT_PROTOCOL_VERSION
    type: Literal["plan"] = "plan"
    plan: list[TaskPlanItem] = Field(description="List of plan tasks")
    reason: str = Field(default="", description="Reasoning for plan creation or modification")


class FinalAction(BaseModel):
    protocol_version: str = CURRENT_PROTOCOL_VERSION
    type: Literal["final"] = "final"
    content: str = Field(description="Final answer, explanation, or outcome statement")
    summary: list[str] = Field(default_factory=list, description="Bullet summary of actions completed")


class MalformedAction(BaseModel):
    protocol_version: str = CURRENT_PROTOCOL_VERSION
    type: Literal["malformed"] = "malformed"
    raw_content: str
    validation_error: str
    correction_prompt: str


ParsedAction = ToolCallAction | PlanAction | FinalAction | MalformedAction


class ProtocolParser:
    """Parses and validates model text output into structured envelopes."""

    @staticmethod
    def parse(raw_text: str) -> ParsedAction:
        """Parse raw model response string into a typed protocol action."""
        cleaned = raw_text.strip()
        if not cleaned:
            return MalformedAction(
                raw_content="",
                validation_error="Empty model response",
                correction_prompt="Response was empty. Please provide a valid JSON envelope adhering to protocol v1.",
            )

        # 1. Direct JSON parse attempt
        json_obj = ProtocolParser._extract_json(cleaned)
        if json_obj is None:
            # Fallback check: if model output contains prose with no JSON, check if it's purely conversational final text
            # But the spec says: "Never execute an unvalidated action extracted from ordinary assistant prose."
            # If there's no action or JSON, we treat it safely as a conversational final response or malformed depending on structure.
            return MalformedAction(
                raw_content=cleaned,
                validation_error="Could not locate valid JSON envelope in model response",
                correction_prompt=(
                    "Your response did not contain a valid JSON envelope. You must format your response as JSON "
                    "with 'protocol_version': '1' and 'type': 'tool_call' | 'plan' | 'final'."
                ),
            )

        # 2. Check protocol version
        version = str(json_obj.get("protocol_version", ""))
        if version != CURRENT_PROTOCOL_VERSION:
            return MalformedAction(
                raw_content=cleaned,
                validation_error=f"Unsupported protocol_version '{version}'. Expected '{CURRENT_PROTOCOL_VERSION}'.",
                correction_prompt=f"Please use 'protocol_version': '{CURRENT_PROTOCOL_VERSION}'.",
            )

        action_type = json_obj.get("type")
        try:
            if action_type == ActionType.TOOL_CALL.value:
                return ToolCallAction.model_validate(json_obj)
            elif action_type == ActionType.PLAN.value:
                return PlanAction.model_validate(json_obj)
            elif action_type == ActionType.FINAL.value:
                return FinalAction.model_validate(json_obj)
            else:
                return MalformedAction(
                    raw_content=cleaned,
                    validation_error=f"Unknown action type '{action_type}'. Expected 'tool_call', 'plan', or 'final'.",
                    correction_prompt="The 'type' field must be one of: 'tool_call', 'plan', or 'final'.",
                )
        except ValidationError as err:
            return MalformedAction(
                raw_content=cleaned,
                validation_error=f"Schema validation error: {err}",
                correction_prompt=f"Your JSON payload failed schema validation: {err}. Please correct the structure.",
            )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Extract valid JSON envelope object, supporting code blocks and stripping thinking tags."""
        # Strip <think>...</think> blocks from reasoning models
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        if not cleaned:
            cleaned = text.strip()

        # Check for ```json ... ``` fenced blocks
        for match in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned):
            try:
                candidate = json.loads(match.group(1))
                if isinstance(candidate, dict) and ("protocol_version" in candidate or "type" in candidate):
                    return candidate
            except json.JSONDecodeError:
                continue

        # Look for JSON substrings by scanning balanced curly braces
        start_indices = [m.start() for m in re.finditer(r"\{", cleaned)]
        for s_idx in start_indices:
            brace_count = 0
            for i in range(s_idx, len(cleaned)):
                if cleaned[i] == "{":
                    brace_count += 1
                elif cleaned[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        candidate_str = cleaned[s_idx : i + 1]
                        try:
                            candidate = json.loads(candidate_str)
                            if isinstance(candidate, dict) and ("protocol_version" in candidate or "type" in candidate):
                                return candidate
                        except json.JSONDecodeError:
                            pass
                        break

        # Fallback to direct parse of cleaned string
        try:
            candidate = json.loads(cleaned)
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            pass

        return None

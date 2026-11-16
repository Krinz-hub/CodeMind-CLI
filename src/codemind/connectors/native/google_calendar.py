"""Official Google Calendar REST API v3 connector (Phase 1)."""

from __future__ import annotations

import datetime
from typing import Any
import httpx

from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectorAction,
    ConnectorManifest,
)
from codemind.connectors.native.google_base import GoogleBaseConnector
from codemind.tools.base import ExecutionContext, ToolResult


GCAL_BASE_URL = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarConnector(GoogleBaseConnector):
    """Integrates official Google Calendar API for schedule inspection, free/busy checks, and event management."""

    manifest = ConnectorManifest(
        connector_id="google_calendar",
        name="Google Calendar",
        description="List schedule events, check availability, create appointments, and manage calendar events.",
        category="productivity",
        version="1.0.0",
        icon="📅",
        auth_method=AuthMethod.OAUTH2,
        required_scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        actions=[
            ConnectorAction(
                name="list_events",
                description="List upcoming calendar events in a specified date/time range.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "time_min": {"type": "string", "description": "ISO 8601 start timestamp (defaults to current time)"},
                        "time_max": {"type": "string", "description": "ISO 8601 end timestamp"},
                        "max_results": {"type": "integer", "description": "Maximum events to return", "default": 10},
                    },
                },
            ),
            ConnectorAction(
                name="check_availability",
                description="Query free/busy slots across a date range to check calendar availability.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "time_min": {"type": "string", "description": "ISO 8601 start timestamp"},
                        "time_max": {"type": "string", "description": "ISO 8601 end timestamp"},
                    },
                    "required": ["time_min", "time_max"],
                },
            ),
            ConnectorAction(
                name="create_event",
                description="Schedule a new meeting or event on your primary Google Calendar.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Title or summary of the event"},
                        "start_time": {"type": "string", "description": "ISO 8601 start time (e.g. '2026-11-20T10:00:00Z')"},
                        "end_time": {"type": "string", "description": "ISO 8601 end time (e.g. '2026-11-20T11:00:00Z')"},
                        "description": {"type": "string", "description": "Optional event details/agenda"},
                        "location": {"type": "string", "description": "Optional meeting location or link"},
                        "attendees": {"type": "array", "items": {"type": "string"}, "description": "Optional list of attendee emails"},
                    },
                    "required": ["summary", "start_time", "end_time"],
                },
            ),
            ConnectorAction(
                name="update_event",
                description="Modify an existing Google Calendar event's timing, summary, or details.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID"},
                        "summary": {"type": "string", "description": "New event title"},
                        "start_time": {"type": "string", "description": "New ISO start time"},
                        "end_time": {"type": "string", "description": "New ISO end time"},
                        "description": {"type": "string", "description": "New event description"},
                    },
                    "required": ["event_id"],
                },
            ),
            ConnectorAction(
                name="delete_event",
                description="Delete an event from Google Calendar (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Google Calendar event ID to remove"},
                    },
                    "required": ["event_id"],
                },
            ),
        ],
    )

    async def execute_action(
        self,
        action_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        headers = await self.get_auth_headers()

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                if action_name == "list_events":
                    return await self._list_events(client, headers, arguments)
                elif action_name == "check_availability":
                    return await self._check_availability(client, headers, arguments)
                elif action_name == "create_event":
                    return await self._create_event(client, headers, arguments)
                elif action_name == "update_event":
                    return await self._update_event(client, headers, arguments)
                elif action_name == "delete_event":
                    return await self._delete_event(client, headers, arguments)
                else:
                    return ToolResult.error(f"Unknown Google Calendar action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Google Calendar API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"Google Calendar action failed: {str(e)}")

    async def _list_events(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        time_min = args.get("time_min") or now_iso
        max_results = min(int(args.get("max_results", 10)), 50)

        params: dict[str, Any] = {
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if "time_max" in args:
            params["timeMax"] = args["time_max"]

        resp = await client.get(
            f"{GCAL_BASE_URL}/calendars/primary/events",
            headers=headers,
            params=params,
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to list calendar events ({resp.status_code}): {resp.text}")

        items = resp.json().get("items", [])
        if not items:
            return ToolResult.success("No calendar events found for the requested interval.")

        lines = [f"Found {len(items)} upcoming event(s):"]
        for ev in items:
            eid = ev.get("id")
            summary = ev.get("summary", "(No Title)")
            start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            end = ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date")
            location = f" @ {ev['location']}" if "location" in ev else ""
            lines.append(f"• [{eid}] {summary} : {start} -> {end}{location}")

        return ToolResult.success("\n".join(lines))

    async def _check_availability(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        time_min = args.get("time_min")
        time_max = args.get("time_max")

        payload = {
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": "primary"}],
        }
        resp = await client.post(f"{GCAL_BASE_URL}/freeBusy", headers=headers, json=payload)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to check calendar availability ({resp.status_code}): {resp.text}")

        data = resp.json()
        busy_slots = data.get("calendars", {}).get("primary", {}).get("busy", [])
        if not busy_slots:
            return ToolResult.success(f"Calendar is completely FREE between {time_min} and {time_max}.")

        lines = [f"Busy periods between {time_min} and {time_max} ({len(busy_slots)} slot(s)):"]
        for b in busy_slots:
            lines.append(f"• BUSY: {b.get('start')} to {b.get('end')}")

        return ToolResult.success("\n".join(lines))

    async def _create_event(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        payload: dict[str, Any] = {
            "summary": args.get("summary"),
            "start": {"dateTime": args.get("start_time")},
            "end": {"dateTime": args.get("end_time")},
        }
        if "description" in args:
            payload["description"] = args["description"]
        if "location" in args:
            payload["location"] = args["location"]
        if "attendees" in args:
            payload["attendees"] = [{"email": a} for a in args["attendees"]]

        resp = await client.post(
            f"{GCAL_BASE_URL}/calendars/primary/events",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to create calendar event ({resp.status_code}): {resp.text}")

        created = resp.json()
        return ToolResult.success(
            f"Calendar event '{args.get('summary')}' created successfully. Event ID: {created.get('id')}"
        )

    async def _update_event(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        event_id = args.get("event_id", "")
        payload: dict[str, Any] = {}
        if "summary" in args:
            payload["summary"] = args["summary"]
        if "description" in args:
            payload["description"] = args["description"]
        if "start_time" in args:
            payload["start"] = {"dateTime": args["start_time"]}
        if "end_time" in args:
            payload["end"] = {"dateTime": args["end_time"]}

        resp = await client.patch(
            f"{GCAL_BASE_URL}/calendars/primary/events/{event_id}",
            headers=headers,
            json=payload,
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to update calendar event '{event_id}' ({resp.status_code}): {resp.text}")

        return ToolResult.success(f"Calendar event '{event_id}' updated successfully.")

    async def _delete_event(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        event_id = args.get("event_id", "")
        resp = await client.delete(
            f"{GCAL_BASE_URL}/calendars/primary/events/{event_id}",
            headers=headers,
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to delete event '{event_id}' ({resp.status_code}): {resp.text}")

        return ToolResult.success(f"Permanently removed event '{event_id}' from primary calendar.")

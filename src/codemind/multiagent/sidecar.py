"""Sidecar runtime managing worker lifecycle, IPC message delivery, and bounded inference."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codemind.multiagent.models import (
    AgentRole,
    InterAgentMessage,
    MessageType,
    MultiAgentConfig,
    WorkerStatus,
)
from codemind.multiagent.protocol import MessageRouter, ProtocolViolationError
from codemind.multiagent.workers import WorkerAgent


class InferenceGate:
    """Regulates local model inference concurrency to respect host GPU and unified memory."""

    def __init__(self, max_concurrent: int = 1):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.inferences_in_flight: int = 0
        self.total_inferences_serviced: int = 0

    async def acquire(self) -> None:
        """Acquire an inference slot in the bounded queue."""
        await self._semaphore.acquire()
        self.inferences_in_flight += 1

    def release(self) -> None:
        """Release an inference slot."""
        self.inferences_in_flight = max(0, self.inferences_in_flight - 1)
        self.total_inferences_serviced += 1
        self._semaphore.release()


class SidecarRuntime:
    """Local asynchronous runtime managing worker agents, IPC routing, and resource bounds."""

    def __init__(self, config: MultiAgentConfig | None = None):
        self.config = config or MultiAgentConfig()
        self.router = MessageRouter()
        self.inference_gate = InferenceGate(max_concurrent=self.config.max_concurrent_inferences)
        self._workers: dict[str, WorkerAgent] = {}
        self.is_running: bool = True
        self.started_at: str = datetime.now(timezone.utc).isoformat()

    def register_worker(self, worker: WorkerAgent) -> str:
        """Register a worker agent with the sidecar."""
        wid = worker.config.worker_id
        self._workers[wid] = worker
        worker.log(f"Worker {wid} ({worker.config.role.value}) registered with sidecar.")
        return wid

    def get_worker(self, worker_id: str) -> WorkerAgent | None:
        """Retrieve registered worker by identifier."""
        return self._workers.get(worker_id)

    def list_workers(self) -> list[dict[str, Any]]:
        """List metadata and status of all registered worker agents."""
        return [
            {
                "worker_id": w.config.worker_id,
                "role": w.config.role.value,
                "status": w.status.value,
                "assigned_task": w.assigned_task_id,
                "read_only": w.config.read_only,
                "workspace": str(w.workspace_path),
            }
            for w in self._workers.values()
        ]

    async def dispatch_task(self, assignment: InterAgentMessage) -> InterAgentMessage:
        """Validate and dispatch a task assignment to the designated worker agent."""
        if not self.is_running:
            return InterAgentMessage(
                task_id=assignment.task_id,
                sender_agent="sidecar",
                recipient="coordinator",
                message_type=MessageType.FAILURE,
                correlation_id=assignment.message_id,
                payload={"error": "Sidecar runtime is stopped."},
            )

        # Validate message routing invariants
        try:
            self.router.validate_and_route(assignment)
        except ProtocolViolationError as pve:
            return InterAgentMessage(
                task_id=assignment.task_id,
                sender_agent="sidecar",
                recipient="coordinator",
                message_type=MessageType.FAILURE,
                correlation_id=assignment.message_id,
                payload={"error": str(pve)},
            )

        target_worker_id = assignment.recipient
        worker = self.get_worker(target_worker_id)
        if not worker:
            return InterAgentMessage(
                task_id=assignment.task_id,
                sender_agent="sidecar",
                recipient="coordinator",
                message_type=MessageType.FAILURE,
                correlation_id=assignment.message_id,
                payload={"error": f"Worker '{target_worker_id}' not found."},
            )

        # Bounded inference queue: acquire inference gate before worker generation
        await self.inference_gate.acquire()
        try:
            result_message: InterAgentMessage = await worker.execute_task_assignment(assignment)
        finally:
            self.inference_gate.release()

        # Validate result message
        self.router.validate_and_route(result_message)
        return result_message

    def stop_worker(self, worker_id: str) -> bool:
        """Stop and terminate a specific worker agent."""
        worker = self._workers.get(worker_id)
        if not worker:
            return False
        worker.status = WorkerStatus.TERMINATED
        worker.log("Worker terminated by sidecar.")
        return True

    def stop_all(self) -> None:
        """Gracefully stop all workers and shutdown sidecar."""
        self.is_running = False
        for w in self._workers.values():
            w.status = WorkerStatus.TERMINATED
            w.log("Sidecar runtime shutdown.")

    def get_status(self) -> dict[str, Any]:
        """Return sidecar health and concurrency telemetry."""
        return {
            "status": "running" if self.is_running else "stopped",
            "started_at": self.started_at,
            "registered_workers": len(self._workers),
            "active_inferences": self.inference_gate.inferences_in_flight,
            "total_inferences_serviced": self.inference_gate.total_inferences_serviced,
            "max_concurrent_inferences": self.inference_gate.max_concurrent,
            "workers": self.list_workers(),
        }

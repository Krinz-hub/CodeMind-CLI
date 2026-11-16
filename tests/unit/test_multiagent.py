"""Unit tests for Multi-Agent Collaboration and Sidecar Runtime."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from codemind.cli.agents_cli import agents_app
from codemind.cli.sidecar_cli import sidecar_app
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.multiagent.models import (
    AgentRole,
    ChangeProposal,
    InterAgentMessage,
    MessageType,
    MultiAgentConfig,
    WorkerConfig,
    WorkerStatus,
)
from codemind.multiagent.protocol import MessageRouter, ProtocolViolationError
from codemind.multiagent.sidecar import InferenceGate, SidecarRuntime
from codemind.multiagent.workers import CodingWorker, DebuggingWorker, ResearchWorker, TestingWorker
from codemind.multiagent.workspace import WorkerWorkspaceManager


class TestMultiAgentUnit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="codemind_ma_test_")
        self.workspace_root = Path(self.temp_dir)
        (self.workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "src" / "math_lib.py").write_text("def multiply(a, b): return a * b\n")

        self.global_config = CodeMindConfig(
            workspace_root=str(self.workspace_root),
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock-model"},
        )
        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_iacp_protocol_and_mediation(self):
        """Verify coordinator-mediated routing invariants and protocol validation."""
        router = MessageRouter()

        # 1. Valid: Coordinator -> Worker
        msg1 = InterAgentMessage(
            task_id="t-1",
            sender_agent="coordinator",
            recipient="worker-coding-1",
            message_type=MessageType.TASK_ASSIGNMENT,
            payload={"instruction": "Implement divide function"},
        )
        routed1 = router.validate_and_route(msg1)
        self.assertEqual(routed1.sender_agent, "coordinator")

        # 2. Valid: Worker -> Coordinator
        msg2 = InterAgentMessage(
            task_id="t-1",
            sender_agent="worker-coding-1",
            recipient="coordinator",
            message_type=MessageType.TASK_COMPLETED,
            payload={"summary": "Function implemented"},
        )
        routed2 = router.validate_and_route(msg2)
        self.assertEqual(routed2.recipient, "coordinator")

        # 3. Violation: Worker -> Worker directly (unauthorized bypass)
        msg_viol1 = InterAgentMessage(
            task_id="t-1",
            sender_agent="worker-coding-1",
            recipient="worker-testing-2",
            message_type=MessageType.PROGRESS_UPDATE,
            payload={"info": "Direct message"},
        )
        with self.assertRaises(ProtocolViolationError):
            router.validate_and_route(msg_viol1)

        # 4. Violation: Worker attempting to issue TASK_ASSIGNMENT
        msg_viol2 = InterAgentMessage(
            task_id="t-1",
            sender_agent="worker-coding-1",
            recipient="coordinator",
            message_type=MessageType.TASK_ASSIGNMENT,
            payload={"instruction": "Delegate"},
        )
        with self.assertRaises(ProtocolViolationError):
            router.validate_and_route(msg_viol2)

        # 5. History retrieval
        history_task = router.get_messages_for_task("t-1")
        self.assertEqual(len(history_task), 2)
        history_worker = router.get_messages_for_worker("worker-coding-1")
        self.assertEqual(len(history_worker), 2)

    def test_worker_workspace_isolation_and_containment(self):
        """Verify workspace mirroring, diff computation, and isolation boundary."""
        mgr = WorkerWorkspaceManager(self.workspace_root)
        worker_id = "worker-coding-1"
        worker_ws = mgr.provision_worker_workspace(worker_id)

        # Check mirror created with cloned files
        self.assertTrue(worker_ws.exists())
        worker_math_lib = worker_ws / "src" / "math_lib.py"
        self.assertTrue(worker_math_lib.exists())
        self.assertIn("multiply", worker_math_lib.read_text())

        # Modify file inside isolated worker workspace
        worker_math_lib.write_text("def multiply(a, b): return a * b\ndef divide(a, b): return a / b\n")

        # Create new file inside worker workspace
        new_file = worker_ws / "src" / "utils.py"
        new_file.write_text("def is_positive(x): return x > 0\n")

        # Ensure primary workspace was NOT modified yet (strict isolation)
        primary_math_lib = self.workspace_root / "src" / "math_lib.py"
        self.assertNotIn("divide", primary_math_lib.read_text())
        self.assertFalse((self.workspace_root / "src" / "utils.py").exists())

        # Extract proposal
        proposal = mgr.extract_change_proposal(worker_id, "task-1")
        self.assertIn("src/math_lib.py", proposal.modified_files)
        self.assertIn("src/utils.py", proposal.created_files)
        self.assertIn("divide", proposal.diffs["src/math_lib.py"])
        self.assertIn("is_positive", proposal.diffs["src/utils.py"])

        # Merge proposal into primary workspace
        ok, msg = mgr.apply_proposal_to_primary(proposal)
        self.assertTrue(ok)
        self.assertIn("divide", primary_math_lib.read_text())
        self.assertTrue((self.workspace_root / "src" / "utils.py").exists())

        # Cleanup
        mgr.cleanup_worker_workspace(worker_id)
        self.assertFalse(worker_ws.exists())

    def test_conflict_detection_on_overlapping_files(self):
        """Verify coordinator conflict detector catches concurrent modifications to same files."""
        mgr = WorkerWorkspaceManager(self.workspace_root)

        prop1 = ChangeProposal(
            worker_id="worker-coding-1",
            task_id="t-1",
            modified_files=["src/math_lib.py"],
            created_files=[],
        )
        prop2 = ChangeProposal(
            worker_id="worker-debugging-2",
            task_id="t-2",
            modified_files=["src/math_lib.py"],
            created_files=[],
        )
        prop3 = ChangeProposal(
            worker_id="worker-testing-3",
            task_id="t-3",
            modified_files=[],
            created_files=["tests/test_math.py"],
        )

        # Detect conflict between prop1 and prop2
        conflicts = mgr.detect_conflicts([prop1, prop2])
        self.assertEqual(len(conflicts), 1)
        self.assertIn("Conflict on 'src/math_lib.py'", conflicts[0])

        # No conflict between prop1 and prop3
        no_conflicts = mgr.detect_conflicts([prop1, prop3])
        self.assertEqual(len(no_conflicts), 0)

    def test_inference_gate_concurrency_bounds(self):
        """Verify InferenceGate semaphore bounds concurrency for local model safety."""
        gate = InferenceGate(max_concurrent=2)
        self.assertEqual(gate.inferences_in_flight, 0)

        async def worker_sim():
            await gate.acquire()
            try:
                self.assertLessEqual(gate.inferences_in_flight, 2)
                await asyncio.sleep(0.01)
            finally:
                gate.release()

        async def run_batch():
            await asyncio.gather(*(worker_sim() for _ in range(5)))

        asyncio.run(run_batch())
        self.assertEqual(gate.inferences_in_flight, 0)
        self.assertEqual(gate.total_inferences_serviced, 5)

    def test_specialized_worker_role_instantiations(self):
        """Verify role-based permission scoping and configuration."""
        mgr = WorkerWorkspaceManager(self.workspace_root)

        # Research Worker
        r_cfg = WorkerConfig(
            worker_id="worker-res-1",
            role=AgentRole.RESEARCH,
            workspace_path=str(self.workspace_root),
            read_only=True,
        )
        r_worker = ResearchWorker(r_cfg, self.global_config, mgr)
        self.assertEqual(r_worker.agent_config.security.permission_mode, PermissionMode.READ_ONLY)

        # Coding Worker
        c_cfg = WorkerConfig(
            worker_id="worker-code-1",
            role=AgentRole.CODING,
            workspace_path=str(self.workspace_root),
            read_only=False,
        )
        c_worker = CodingWorker(c_cfg, self.global_config, mgr)
        self.assertEqual(c_worker.agent_config.security.permission_mode, PermissionMode.TRUSTED)

    def test_sidecar_runtime_lifecycle_and_dispatch(self):
        """Verify SidecarRuntime worker registration, status telemetry, and stop lifecycle."""
        sidecar = SidecarRuntime(MultiAgentConfig(max_workers=2, max_concurrent_inferences=1))
        self.assertTrue(sidecar.is_running)

        mgr = WorkerWorkspaceManager(self.workspace_root)
        c_cfg = WorkerConfig(
            worker_id="worker-code-1",
            role=AgentRole.CODING,
            workspace_path=str(self.workspace_root),
        )
        c_worker = CodingWorker(c_cfg, self.global_config, mgr)
        sidecar.register_worker(c_worker)

        workers = sidecar.list_workers()
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]["worker_id"], "worker-code-1")

        status = sidecar.get_status()
        self.assertEqual(status["status"], "running")
        self.assertEqual(status["registered_workers"], 1)

        sidecar.stop_worker("worker-code-1")
        self.assertEqual(c_worker.status, WorkerStatus.TERMINATED)

        sidecar.stop_all()
        self.assertFalse(sidecar.is_running)

    def test_agents_and_sidecar_cli_commands(self):
        """Verify CLI subcommands for agents and sidecar."""
        # agents list
        res_list = self.runner.invoke(agents_app, ["list"])
        self.assertEqual(res_list.exit_code, 0)
        self.assertIn("research", res_list.output)
        self.assertIn("coding", res_list.output)

        # agents status
        res_status = self.runner.invoke(agents_app, ["status"])
        self.assertEqual(res_status.exit_code, 0)
        self.assertIn("Runtime State", res_status.output)

        # agents config
        res_cfg = self.runner.invoke(agents_app, ["config"])
        self.assertEqual(res_cfg.exit_code, 0)
        self.assertIn("max_workers", res_cfg.output)

        # sidecar status
        res_sc_status = self.runner.invoke(sidecar_app, ["status"])
        self.assertEqual(res_sc_status.exit_code, 0)
        self.assertIn("Runtime Status", res_sc_status.output)

        # sidecar start & stop
        res_sc_start = self.runner.invoke(sidecar_app, ["start"])
        self.assertEqual(res_sc_start.exit_code, 0)
        res_sc_stop = self.runner.invoke(sidecar_app, ["stop"])
        self.assertEqual(res_sc_stop.exit_code, 0)


if __name__ == "__main__":
    unittest.main()

# Evaluation & Telemetry: CodeMind CLI

## 1. Metrics & Quality Gates

The agent runtime includes an evaluation framework capable of assessing agent performance independently of model scale:

1. **Protocol Compliance Rate:** Percentage of model turns successfully parsed as valid v1 envelopes without syntax or schema errors.
2. **Tool Selection Accuracy:** Ratio of correct tools chosen for specific task objectives.
3. **Sandbox Enforcement Rate:** Must be 100%. Zero unauthorized accesses outside workspace or secret file leaks.
4. **Verification Integrity:** Must be 100%. Zero unverified claims of test success.
5. **Turn Efficiency:** Average model turns consumed per completed task milestone.

---

## 2. Redacted Event Telemetry

Traces are recorded locally to `.codemind/sessions/<session-id>.events.jsonl`:
- Every event records timestamp, phase, action type, tool name, and exit code.
- Arguments and outputs are scrubbed through the secret shield before disk persistence.
- Zero external analytics or telemetry endpoints are contacted.

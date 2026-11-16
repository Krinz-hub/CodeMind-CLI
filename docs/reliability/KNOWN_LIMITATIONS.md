# CodeMind CLI — Known Limitations & Operational Boundaries (Phase E)

> **Document Version:** 1.0.0  
> **Status:** Current Technical Assessment  
> **Target Release:** CodeMind CLI v0.1.0  

---

## 1. Local Model Context Windows & Inferences

1. **Context Window Saturation:**
   - Local models (e.g., Qwen 2.5 / 3.6 7B-35B, Llama 3.1 8B) typically operate within 8K to 32K context windows depending on VRAM allocations.
   - While `ContextCompactor` compacts older conversation turns, extremely large codebases (thousands of files) must rely on targeted `@file` mentions, `search_files`, and `search_text` rather than dumping full directories into context.
2. **JSON Format Adherence on Smaller Quantized Weights:**
   - 4-bit and small (7B-8B) models may occasionally generate JSON formatting errors or conversational preambles.
   - `ProtocolNormalizer` extracts embedded markdown codeblocks and fixes trailing commas, and the dedicated 3-attempt repair budget isolates format retries. However, smaller models (<7B) may struggle with complex nested tool arguments compared to 14B+ models.

---

## 2. Multi-Agent & VRAM Concurrency

1. **Sequential GPU Inference Lock:**
   - To prevent Out-Of-Memory (OOM) crashes on local GPUs (e.g. 16GB-32GB Apple Silicon or RTX 4080/4090), CodeMind enforces `max_concurrent_inferences=1`.
   - Multi-agent collaboration (Coordinator, Research, Coding, Debugging, Testing) executes sequentially when querying local models. Parallel worker execution is supported for file reads and tool operations, but model inferences are queued.
2. **Subprocess Isolation Overhead:**
   - Worker workspaces are cloned into `.codemind/workspaces/<worker-id>`. For extremely large git repositories (>5GB), disk usage will increase proportionally with the number of spawned workers until cleaned up.

---

## 3. Tool & Protocol Boundaries

1. **MCP Transport Scope:**
   - The current MCP client implementation supports local `stdio` processes. Remote HTTP / SSE transports are intentionally deferred to future versions until secure authentication and mutual TLS boundaries are formalized.
2. **Terminal Shell Redirections in Security Policies:**
   - `PermissionPolicyEngine` tokenizes shell command strings via `shlex`. Commands utilizing complex shell chaining (`&&`, `||`, pipes `|`) must be matched carefully or run through supervised interactive approval.
3. **Git Workflows & External Remotes:**
   - CodeMind CLI provides safe local git operations (`git_branch`, `git_commit`, `git_diff`, `git_status`, `git_log`). Remote push/pull operations with GitHub/GitLab require configured SSH keys or credential helpers on the host system and remain gated under interactive approval.

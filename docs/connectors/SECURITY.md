# Security Architecture & Risk Tiering

## 1. Declarative Risk Classification

Every action exposed by a connector declares a static `ActionRiskLevel`:

| Risk Tier | Characteristics | Default Policy | Examples |
|---|---|---|---|
| `READ` | Read-only operations, searches, and metadata inspection. No side effects. | Auto-approved in Supervised and Trusted modes. | `gmail__search_emails`, `youtube__search_videos`, `google_drive__search_files`, `spotify__search` |
| `WRITE` | Resource creation or non-destructive mutations. Modifies user libraries or records. | Requires user confirmation in Supervised mode. Auto-approved in Trusted mode. Blocked in Read-Only mode. | `google_drive__create_file`, `google_calendar__create_event`, `spotify__create_playlist`, `notion__update_page` |
| `SENSITIVE` | Irreversible, destructive, or public communication actions. High potential for harm if triggered erroneously. | **Strictly requires interactive user approval** across all operational modes before network dispatch. | `gmail__send_email`, `slack__send_message`, `discord__send_message`, `youtube__upload_video`, `google_drive__delete_file`, `google_calendar__delete_event` |

---

## 2. Interactive Approval Flow

For any action evaluated as `SENSITIVE` (or `WRITE` in supervised mode):
1. The tool pauses execution before dispatching the request.
2. The user is presented with the explicit target action, connector name, and parameter summary:
   ```text
   [Action Approval Required]
   Connector : Gmail (gmail)
   Action    : send_email [SENSITIVE]
   To        : teammate@example.com
   Subject   : Project Status Update
   Execute this action? [y/N]:
   ```
3. If the user declines (`n` or Enter), execution is immediately aborted with `APPROVAL_REJECTED`, the adapter is not invoked, and the cancellation is recorded in the audit log.

---

## 3. Connector Permissions Management

Users have granular, persistent control over each connector via `.codemind/connectors_policy.json`:

```json
{
  "gmail": {
    "enabled": true,
    "read_only": false,
    "disabled_actions": [],
    "supervised_actions": ["send_email"],
    "allowed_actions": ["search_emails", "read_thread"]
  },
  "google_drive": {
    "enabled": true,
    "read_only": true,
    "disabled_actions": ["delete_file"]
  }
}
```

CLI controls:
```bash
# Lock a connector to read-only mode (blocks all WRITE and SENSITIVE actions)
codemind connectors permissions google_drive --read-only

# Disable a connector entirely
codemind connectors permissions discord --disable

# Re-enable
codemind connectors permissions discord --enable
```

---

## 4. Secret Scrubbing & Data Shielding

CodeMind utilizes `redact_secrets()` at multiple security boundaries:
1. **Output redaction**: All output strings produced by connectors or external MCP tools are scrubbed before returning to the model or terminal.
2. **Audit logging**: `ConnectorAuditLogger` scrubs parameters, tokens, and exception strings before writing to disk.
3. **Regex patterns enforced**:
   - Bearer tokens (`Bearer [REDACTED_TOKEN]`)
   - OpenAI API keys (`sk-[REDACTED_OPENAI_KEY]`)
   - Google tokens (`ya29.[REDACTED_GOOGLE_TOKEN]`, `1//[REDACTED_GOOGLE_REFRESH_TOKEN]`)
   - Discord bot tokens (`[REDACTED_DISCORD_TOKEN]`)
   - Slack bot tokens (`xoxb-[REDACTED_TOKEN]`)
   - GitHub Personal Access Tokens (`ghp_[REDACTED_GITHUB_TOKEN]`)
   - AWS Access Keys (`AKIA[REDACTED_AWS_KEY]`)
   - Private key blocks (`[REDACTED_PRIVATE_KEY_BLOCK]`)

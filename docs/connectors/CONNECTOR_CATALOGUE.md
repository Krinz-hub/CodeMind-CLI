# CodeMind Connector Catalogue

Complete specification of all built-in Phase 1 and Phase 2 application connectors, their capabilities, risk levels, and authentication methods.

---

## 1. Phase 1: Google Cloud Ecosystem

### 1.1 YouTube (`youtube`)
- **Icon**: ▶️
- **Category**: `media`
- **Auth Method**: `OAUTH2` (PKCE)
- **Scopes**: `https://www.googleapis.com/auth/youtube.readonly`, `https://www.googleapis.com/auth/youtube.upload`
- **Actions**:
  - `search_videos` (`READ`): Search public YouTube videos by keyword or query.
  - `get_channel_info` (`READ`): Retrieve channel statistics, title, and subscriber metrics.
  - `get_video_metadata` (`READ`): Retrieve view counts, likes, tags, and description for a specific video ID.
  - `get_analytics` (`READ`): Retrieve high-level views, watch time, and subscriber counts.
  - `manage_playlists` (`WRITE`): List, create, or add videos to authorized YouTube playlists.
  - `upload_video` (`SENSITIVE`): Upload local video file to YouTube with title, description, tags, and privacy status. Requires explicit user approval.

### 1.2 Gmail (`gmail`)
- **Icon**: ✉️
- **Category**: `communication`
- **Auth Method**: `OAUTH2` (PKCE)
- **Scopes**: `https://www.googleapis.com/auth/gmail.readonly`, `https://www.googleapis.com/auth/gmail.compose`, `https://www.googleapis.com/auth/gmail.send`
- **Actions**:
  - `search_emails` (`READ`): Search inbox messages matching query syntax.
  - `read_thread` (`READ`): Read complete email thread history with sender and dates.
  - `summarize_conversations` (`READ`): Retrieve recent thread messages and compile summary context.
  - `create_draft` (`WRITE`): Create an email draft in Gmail.
  - `send_email` (`SENSITIVE`): Send an email to recipient(s). Requires explicit human approval.

### 1.3 Google Drive (`google_drive`)
- **Icon**: 📁
- **Category**: `storage`
- **Auth Method**: `OAUTH2` (PKCE)
- **Scopes**: `https://www.googleapis.com/auth/drive.readonly`, `https://www.googleapis.com/auth/drive.file`
- **Actions**:
  - `search_files` (`READ`): Search files and folders matching filename or mimeType queries.
  - `read_document` (`READ`): Read or export document content (text/markdown/plain).
  - `create_file` (`WRITE`): Create a new text/code document in Google Drive.
  - `upload_file` (`WRITE`): Upload a local workspace file to Google Drive.
  - `organize_folders` (`WRITE`): Create folders or move files between directories.
  - `delete_file` (`SENSITIVE`): Permanently delete a file or folder from Google Drive. Requires explicit user approval.

### 1.4 Google Calendar (`google_calendar`)
- **Icon**: 📅
- **Category**: `productivity`
- **Auth Method**: `OAUTH2` (PKCE)
- **Scopes**: `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/calendar.events`
- **Actions**:
  - `list_events` (`READ`): List calendar events within a time range.
  - `check_availability` (`READ`): Check schedule busy/free intervals.
  - `create_event` (`WRITE`): Schedule a new event with title, start, end, and attendees.
  - `update_event` (`WRITE`): Reschedule or update an existing event.
  - `delete_event` (`SENSITIVE`): Remove an event from the calendar. Requires explicit user approval.

---

## 2. Phase 2: Communication, Productivity, and Media

### 2.1 Discord (`discord`)
- **Icon**: 💬
- **Category**: `communication`
- **Auth Method**: `BOT_TOKEN`
- **Actions**:
  - `read_channel` (`READ`): Read recent message history from a Discord channel.
  - `search_messages` (`READ`): Search channel history for keyword matches.
  - `send_message` (`SENSITIVE`): Post a message to a Discord channel. Requires explicit user approval.

### 2.2 Slack (`slack`)
- **Icon**: 💼
- **Category**: `communication`
- **Auth Method**: `BOT_TOKEN`
- **Actions**:
  - `list_channels` (`READ`): List public and private workspace channels.
  - `read_channel` (`READ`): Read recent messages from a channel.
  - `search_messages` (`READ`): Search conversation history for keywords.
  - `send_message` (`SENSITIVE`): Post a message or reply to a thread in Slack. Requires explicit user approval.

### 2.3 Notion (`notion`)
- **Icon**: 📓
- **Category**: `productivity`
- **Auth Method**: `API_KEY`
- **Actions**:
  - `search_pages` (`READ`): Search pages and databases in the connected workspace.
  - `read_page` (`READ`): Retrieve page metadata and block hierarchy.
  - `create_page` (`WRITE`): Create a new page under a parent page or database.
  - `update_page` (`WRITE`): Update page properties or archive records.
  - `query_database` (`READ`): Query structured database rows with filter criteria.

### 2.4 Spotify (`spotify`)
- **Icon**: 🎵
- **Category**: `media`
- **Auth Method**: `OAUTH2`
- **Scopes**: `playlist-read-private`, `playlist-modify-public`, `playlist-modify-private`, `user-modify-playback-state`, `user-read-playback-state`
- **Actions**:
  - `search` (`READ`): Search music catalog for tracks, albums, or artists.
  - `get_playlists` (`READ`): Retrieve current user's library playlists.
  - `create_playlist` (`WRITE`): Create a new playlist.
  - `manage_tracks` (`WRITE`): Add or remove tracks from a playlist.
  - `playback_control` (`SENSITIVE`): Trigger play, pause, next, or previous playback commands. Requires explicit user approval.

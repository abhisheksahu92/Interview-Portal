# SPEC: Automated Jules Bug-Fixing Pipeline & Slack Dispatch

## Status: FINALIZED

## 1. Problem Statement
When unhandled 500 runtime errors or worker task failures occur, developers currently must manually review logs, formulate a bug fix, create a branch, write tests, and raise a pull request.
With the Google Jules integration (`core.jules`) and Slack integration (`core.slack`), we can automate this entire remediation loop.

## 2. Solution Overview
1. **Trigger**:
   - HTTP 500 (`core.views.server_error`)
   - Background worker task failure (`core.management.commands.run_worker`)
2. **Jules Session Creation**:
   - `core.jules.dispatch_bug_fix_task(title, error_summary, traceback_str, path)` creates a Jules task session with strict Ponytail/GSD instructions (minimal diff, root cause fix, test coverage).
3. **Async Polling Task**:
   - `core.jules.poll_jules_session(session_id, channel="system_errors")` is enqueued onto the Redis `default` queue.
   - Polls session activities every 30 seconds (up to 15 minutes).
4. **Resolution & Slack Notification**:
   - If Jules asks a question / requires input: sends a Slack notification with the question.
   - When Jules completes the session (`sessionCompleted` with patch/PR artifact):
     - Sends a Slack alert to `#ip-system-errors`:
       `:robot_face: *Jules AI Proposed a Fix for*: <Title>\n• Session: <url>\n• Suggested Commit: <commit message>`
     - (Optionally applies patch to a branch or posts PR link).

## 3. Invariants & Ponytail Rules
- **Non-blocking**: Must never block the HTTP response cycle or crash if Jules API fails.
- **Deduplication**: Do not create duplicate Jules sessions for the same error path/type within a 1-hour window (using Django cache).
- **YAGNI / Minimal Diff**: Reuses existing `core.jules`, `core.slack`, and `core.queue`.


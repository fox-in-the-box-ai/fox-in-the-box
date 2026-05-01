# Task 09 — WebUI Queue Response Display Fix

**Priority:** P1 (User Experience Bug)  
**Assignee:** Agent H  
**Dependencies:** Task 08 (CI/CD needs to pass with fixes)  
**Estimated Effort:** 4-6 hours  

---

## Problem Statement

Messages queued in Fox in the Box WebUI are properly queued and drained by the system, but **user responses are not visible** after queue processing completes. The queue mechanism works (messages get dequeued), but the UI fails to display the assistant's responses, making it appear like messages are "lost in queue."

**Root Cause:** When a queued message is drained and sent via `setBusy(false)` → `send()`, the response handling may not be properly updating the visible chat history.

---

## Technical Analysis

**Working Components:**
- `queueSessionMessage()` correctly stores messages in `SESSION_QUEUES`
- `setBusy(false)` correctly drains one message via `shiftQueuedSessionMessage()` 
- Queue countdown/display works correctly
- Message is populated into input and `send()` is called

**Failing Component:**
- Response from queued message doesn't appear in chat history
- User sees message sent but no response visible

**Files Involved:**
- `/forks/hermes-webui/static/ui.js` (lines 1685-1715) — `setBusy()` and queue drain
- `/forks/hermes-webui/static/messages.js` — response handling and rendering
- Potentially session state management in message flow

---

## Acceptance Criteria

### AC1: Visual Queue Flow Test
- **Setup:** Agent is processing a message (busy state)
- **Action:** Send a second message → should show "Queued: message..." toast and queue chip
- **Expected:** Queue chip displays "1 message queued"
- **Test Command:** Manual browser test

### AC2: Queue Drain and Response Display
- **Setup:** Continue from AC1 when agent finishes first response
- **Action:** Agent completes → queue should drain automatically  
- **Expected:** 
  1. Queued message appears in chat history as user message
  2. Agent's response to queued message appears immediately after
  3. Queue chip disappears
  4. Chat shows natural conversation flow: [first Q&A, then queued Q&A]
- **Test Command:** Manual browser test + automated test for response rendering

### AC3: Multiple Queue Drain
- **Setup:** Queue 3 messages while agent is busy
- **Action:** Agent completes initial response
- **Expected:** Only first queued message drains and gets response, others remain queued for next cycle
- **Test Command:** `pytest tests/integration/test_queue_response_display.py::test_multiple_queue_drain`

### AC4: Session Switching with Queue
- **Setup:** Session A has queued messages, switch to Session B, then back to A  
- **Action:** Agent completes response in Session A
- **Expected:** Queue drains correctly in Session A regardless of current session view
- **Test Command:** `pytest tests/integration/test_queue_response_display.py::test_cross_session_queue`

### AC5: Page Refresh with Active Queue
- **Setup:** Messages queued, page refresh while agent still processing
- **Action:** Agent completes after page load  
- **Expected:** Queue restores from `sessionStorage`, drains correctly, response displays
- **Test Command:** Browser automation test with page refresh simulation

---

## Implementation Approach

### Phase 1: Diagnosis (1-2h)
1. **Trace the response flow** for queued vs normal messages
   - Compare normal `send()` response handling vs queue-drained `send()`
   - Check if `INFLIGHT` state differs between the two paths
   - Verify SSE stream handling for queued messages

2. **Identify the gap**
   - Does queued message get proper session context?
   - Is response SSE stream connecting to right session?
   - Are responses getting lost in cross-session bleed?

### Phase 2: Fix (2-3h)
**Likely fixes based on common patterns:**
- Ensure `activeSid` is correctly set when draining queue
- Fix session context in `send()` when called from queue drain path
- Update SSE stream handlers to respect queue session context
- Ensure `renderMessages()` is called after response completes

### Phase 3: Testing (1h)
- Write automated tests covering ACs 3-4
- Manual validation of ACs 1-2, 5
- Edge case testing (multiple queues, session switches, refresh)

---

## Files to Modify

**Primary:**
- `/forks/hermes-webui/static/ui.js` — queue drain mechanism may need session context fixes
- `/forks/hermes-webui/static/messages.js` — response rendering for queued messages
- `/forks/hermes-webui/static/sessions.js` — session state management during queue processing

**Testing:**
- `tests/integration/test_queue_response_display.py` — new test file
- `tests/integration/test_setup_api.py` — update existing response tests if needed

**IMPORTANT:** This requires **submodule modifications** to `/forks/hermes-webui/`. Use the submodule workflow in AGENTS.md section 6a.

---

## Success Metrics

- **Functional:** All 5 ACs pass
- **User Experience:** Seamless conversation flow with no "lost" responses
- **Performance:** Queue processing adds <200ms latency to response display
- **Reliability:** Queue system works consistently across session switches and page refreshes

---

## Risk Assessment

**Low Risk:**
- Queue storage/retrieval mechanism already works
- Core `send()` functionality is proven  
- Fix likely involves session context, not core streaming

**Medium Risk:**
- SSE response handling may be complex to debug
- Cross-session queue management has edge cases

**Mitigation:**
- Start with detailed tracing/logging to isolate the exact failure point
- Test each fix incrementally rather than large rewrites
- Preserve existing queue behavior that works correctly

---

## Handoff Notes

**For Agent H:**
1. **Start by adding debug logging** to `setBusy(false)` and the queue drain path to trace where responses get lost
2. **Focus on response SSE handling** — compare working vs broken response paths  
3. **The queue mechanism itself works** — don't rewrite storage/retrieval logic
4. **Test early and often** — this is a UX-critical bug users hit frequently

**For Supervisor:**
- Expect submodule changes to `/forks/hermes-webui/`
- Priority: get this into next release, it's affecting user experience daily
- If fix is complex, consider interim workaround (force page refresh after queue completes)
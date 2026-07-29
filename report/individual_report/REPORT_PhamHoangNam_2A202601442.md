# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Pham Hoang Nam
- **Student ID**: 2A202601442
- **Date**: 28/7/2026

---

## I. Technical Contribution (15 Points)

### Modules Implemented

- `src/prompts.py`

### Code Highlights

As the **Role 3 - Prompt Engineer**, I designed the prompts and safety limits used by both the baseline chatbot and the ReAct Agent.

My contributions include:

- Wrote `CHATBOT_BASELINE_PROMPT`, constraining the baseline chatbot to answer only from prior knowledge and explicitly refuse to claim it has read a CV, accessed a calendar, or booked anything.
- Wrote `REACT_SYSTEM_PROMPT`, defining the five valid tools (`screen_candidate`, `check_interviewer_calendar`, `book_interview`, `generate_invitation_email`, `suggest_new_slots`) with their exact argument signatures, and enforcing the strict per-turn output format: either a `Thought` + `Action`, or a `Thought` + `Final Answer`.
- Added explicit guardrail rules in the system prompt: never fabricate an Observation, never evaluate candidates on sensitive attributes (age, gender, ethnicity, religion, marital status), never repeat a failed Action more than once, and never claim `book_interview` succeeded unless the Observation confirms `interview_booked=true`.
- Set the safety limits `MAX_ITERATIONS = 6`, `TIMEOUT_SECONDS = 10`, and `MAX_QUERY_CHARS = 50_000` in `src/prompts.py` to bound agent runtime and prevent runaway loops.

### Documentation

The `REACT_SYSTEM_PROMPT` is the main guardrail layer that forces the model to reason before acting, restricts it to a fixed tool set, and prevents it from asserting outcomes it has no tool evidence for. This was the primary mechanism that let the ReAct Agent recover safely from tool errors and edge-case inputs during testing.

---

## II. Debugging Case Study (10 Points)

### Problem Description

While Role 4 (Agent Integrator) was running `src/app.py` to test the ReAct loop, the app repeatedly crashed with an HTTP `429` error whenever he tried to run it multiple times in a row.

### Log Source

Console output example:

```
google.api_core.exceptions.ResourceExhausted: 429 Resource has been exhausted
(e.g. check quota).
```

### Diagnosis

I traced the error to the Gemini API key he was using. It was a **free-tier key**, which comes with a strict rate limit and a low request quota. Each test run fired requests back-to-back with little spacing, so the free tier was hit almost immediately after a few runs.

First fix attempt: I suggested increasing the delay between requests (from ~10 to 15 seconds) and switching the model name to `gemini-flash-latest` to reduce load per call. This worked initially, but after another 5–6 requests the same `429` error came back — confirming the root cause wasn't request pacing alone, but the **free-tier quota ceiling itself** (our usage pattern could sustain only about 5 requests before hitting the cap, regardless of delay).

### Solution

Since the free-tier Gemini key couldn't support the team's testing volume, I suggested switching providers entirely. One teammate provided an OpenAI API key, and after Role 4 switched the app to use it, `run_react_agent()` completed full test runs successfully without further quota errors.

---

## Additional Contributions Beyond My Assigned Role

Outside of my own file, I also contributed to the team in a few other ways:

- **Workflow coordination**: helped the team keep track of the overall ReAct workflow — clarifying who was working on which file, and checking in on each teammate's current progress so work stayed synchronized across Roles 1, 2, 4, and 5.
- **Cross-group presentation**: pitched our project in front of the other teams during the Mốc 4 cross-audit session, which helped the group earn bonus points.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning

Writing the `REACT_SYSTEM_PROMPT` made clear how much of the Agent's reliability comes from prompt design rather than the model itself. Forcing a `Thought` before every `Action` gave the Agent a visible reasoning trace, while the baseline chatbot prompt could only ever produce a single, unverified answer.

### 2. Reliability

The guardrail rules mattered more than expected. Without the rule against fabricating Observations, the model would sometimes assume a tool result instead of waiting for the real one. Without the repeat-action rule, it was prone to retrying the same failing call. Prompt constraints closed both gaps.

### 3. Observation

Because the prompt explicitly tells the model that Observations are inserted by the application, the Agent treated tool feedback as ground truth and adjusted its next Thought accordingly — for example, switching to `suggest_new_slots` when the calendar tool reported no availability instead of insisting on booking anyway.

---

## IV. Future Improvements (5 Points)

### Scalability

- Split the system prompt into smaller, composable prompt segments as more tools are added.
- Support prompt versioning so guardrail changes can be tested independently.

### Safety

- Add stricter schema validation for tool arguments before they reach the parser.
- Expand the sensitive-attribute exclusion list based on real recruitment compliance requirements.

### Performance

- Trim the system prompt to reduce token usage per call.
- Cache prompt templates and only interpolate dynamic fields at call time.

---

> This report summarizes my contribution as the **Prompt Engineer (Role 3)**. My primary responsibility was designing the baseline and ReAct system prompts and the safety guardrails in `src/prompts.py`, alongside cross-role debugging support, workflow coordination, and representing the team during the inter-group presentation.

# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Nguyễn Thế Nam
- **Student ID**: 2A202601958
- **Date**: 28/07/2026

---

## I. Technical Contribution (15 Points)

As the Tools Engineer, my responsibility was to design, implement, and maintain the tool interface used by the ReAct agent. The goal was to ensure that the agent could reliably execute external actions and receive structured observations for reasoning.

- **Modules Implementated**: `src/tools.py`
- **Code Highlights**: AVAILABLE_TOOLS = {
  "analyze_cv": analyze_cv,
  "schedule_interview": schedule_interview,
  "check_application_status": check_application_status,
  "search_candidate_pool": search_candidate_pool,
  }
- **Documentation**: The tool module acts as the execution layer of the ReAct framework.

The LLM generates an Action.
The ReAct loop parses the action.
The corresponding function in tools.py is executed.
The function returns an observation.
The observation is appended to the conversation history.
The LLM uses the new information to continue reasoning or produce the final answer.

---

## II. Debugging Case Study (10 Points)

_Analyze a specific failure event you encountered during the lab using the logging system._

- **Problem Description**: During testing, the agent repeatedly generated:

Action: search(None)
or
Action: search("")

This caused the tool to return empty results, and the agent entered multiple unnecessary reasoning cycles before stopping.

- **Log Source**: Thought: I should search for more information. Action: search(None) Observation: Error: Empty search query. Thought: Maybe I should search again. Action: search(None)
- **Diagnosis**: The issue was caused by the LLM generating malformed tool arguments. The parser accepted the invalid input and executed the tool without validation.

The root causes were:

The system prompt did not clearly specify the required action format.
The parser lacked argument validation.
The search tool assumed the input was always valid.

- **Solution**: I implemented multiple improvements:

Added input validation inside search().
if not query:
return "Error: Empty search query."
Improved the system prompt with correct examples of valid tool calls.

Example:

Action: search("Python decorators")

instead of

Action: search(None)
Updated the parser to reject malformed actions before execution.

After these changes, invalid actions were handled gracefully, reducing unnecessary reasoning loops and improving agent stability.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

_Reflect on the reasoning capability difference._

1.  **Reasoning**: How did the `Thought` block help the agent compared to a direct Chatbot answer?
    The Thought block allows the ReAct agent to explicitly plan before taking an action. Instead of immediately generating an answer, the agent can determine whether external information is required.

For example, when asked about current events, a traditional chatbot may answer from its internal knowledge, whereas the ReAct agent first decides to use the search tool and then generates a response based on retrieved information.

This makes the reasoning process more transparent and easier to debug. 2. **Reliability**: In which cases did the Agent actually perform _worse_ than the Chatbot?
The ReAct agent performed worse than a standard chatbot in several situations:

Simple factual questions that did not require external tools.
Poorly designed tool descriptions that caused incorrect tool selection.
Invalid tool arguments leading to repeated failures.
Slow external APIs increasing response latency.

In these cases, a direct chatbot produced faster and sometimes more reliable responses.

3.  **Observation**: How did the environment feedback (observations) influence the next steps?
    Observations are the key feedback mechanism of the ReAct framework.

After each tool execution, the returned observation becomes additional context for the next reasoning step.

For example:

Thought:
I need the latest Python version.

Action:
search("latest Python version")

Observation:
Python 3.14 is the latest stable release.

Thought:
Now I have enough information.

Final Answer:
The latest stable version of Python is 3.14.

## Without observations, the agent cannot verify whether an action succeeded or failed, making iterative reasoning impossible.

## IV. Future Improvements (5 Points)

_How would you scale this for a production-level AI agent system?_

- **Scalability**: Implement asynchronous execution for multiple tool calls.
  Support parallel tool invocation to reduce latency.
  Introduce a plugin-based architecture for dynamic tool registration.
- **Safety**: Add a Supervisor LLM to validate generated actions before execution.
  Apply permission-based access control for sensitive tools.
  Sanitize tool inputs to prevent prompt injection or malicious commands.
- **Performance**: Use a Vector Database to retrieve relevant tools when many tools are available.
  Cache frequent tool responses to reduce redundant API calls.
  Implement structured logging and monitoring to analyze agent performance and failure patterns.

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.

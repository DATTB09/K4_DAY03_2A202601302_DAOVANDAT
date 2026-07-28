# Individual Report: Lab 3 - Chatbot vs ReAct Agent

* **Student Name**: [DAO VAN DAT]
* **Student ID**: [2A202601302]
* **Date**: [28/7/2026]

---

## I. Technical Contribution (15 Points)

*Describe your specific contribution to the codebase (e.g., implemented a specific tool, fixed the parser, etc.).*

* **Modules Implementated**:

  * `config/test_cases.json`
  * Business Analysis
  * Functional Requirements
  * Non-functional Requirements
  * User Stories
  * Acceptance Criteria
  * Edge Cases Design

* **Code Highlights**:

```json
{
  "id": "TC004",
  "category": "Multi-Step",
  "title": "Qualified candidate with available interview slot",
  "workflow": [
    "Read JD",
    "Read CV",
    "Calculate Score",
    "Check Calendar",
    "Book Interview",
    "Generate Invitation Email"
  ],
  "expected": {
    "status": "PASS",
    "interview_booked": true
  }
}
```

* **Documentation**:

As the Product Architect, I designed the business workflow and evaluation criteria for the Recruitment AI Agent. I created a comprehensive testing dataset that includes simple cases, multi-step scenarios, and edge cases. These test cases serve as the foundation for validating the ReAct Agent's reasoning process, tool selection, and decision-making behavior.

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event you encountered during the lab using the logging system.*

* **Problem Description**:

The AI Agent incorrectly accepted a candidate who did not possess all mandatory skills specified in the Job Description.

* **Log Source**:

Example output:

```text
Thought: Candidate has most required skills.
Action: calculate_score()
Observation: Score = 82
Final Answer: PASS
```

* **Diagnosis**:

The issue occurred because the business rule requiring all mandatory skills was not explicitly defined. The scoring function only evaluated the total score and ignored missing required skills.

* **Solution**:

Updated the business rules and test cases to ensure mandatory skills are validated before score calculation. Added additional edge cases to prevent similar incorrect decisions.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

*Reflect on the reasoning capability difference.*

### 1. Reasoning

The ReAct Agent provides a structured reasoning process by generating a Thought before selecting an Action and analyzing the Observation returned from external tools. This approach produces more transparent and explainable decisions compared to a traditional chatbot, which typically responds directly without intermediate reasoning.

### 2. Reliability

The Agent performed worse than a traditional chatbot when business rules or tool specifications were incomplete. Incorrect tool outputs or ambiguous requirements could lead to inaccurate decisions even though the reasoning process itself was valid.

### 3. Observation

Environment feedback significantly influenced the Agent's next action. For example, if the calendar tool reported no available interview slots, the Agent changed its reasoning and suggested alternative interview times instead of attempting to schedule immediately.

---

## IV. Future Improvements (5 Points)

*How would you scale this for a production-level AI agent system?*

* **Scalability**:

  * Integrate with Applicant Tracking Systems (ATS).
  * Support batch processing for multiple CVs.
  * Process tool calls asynchronously.

* **Safety**:

  * Implement a Supervisor Agent to review final decisions.
  * Add Prompt Injection detection.
  * Validate mandatory skills before candidate scoring.

* **Performance**:

  * Store Job Descriptions and candidate embeddings in a Vector Database.
  * Cache frequently used tool results.
  * Use Retrieval-Augmented Generation (RAG) to retrieve organization-specific recruitment policies.

---


> This report summarizes my contribution as the **Product Architect (Role 1)**. My primary responsibility was analyzing business requirements, designing evaluation criteria, and preparing comprehensive test cases that guided the implementation and validation of the Recruitment AI ReAct Agent.

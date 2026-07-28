# Group Report: Lab 3 - Production-Grade Agentic System

* **Team Name**: [TeamC4]
* **Team Members**: [DaoVanDat, NguyenThiKieuTrang, DaoDuyHung, PhamHoangNam, NguyenTheNam]
* **Deployment Date**: [2026-07-28]

---

# 1. Executive Summary

Our project developed an **AI Recruitment Screening & Interview Scheduling Assistant** using the ReAct Agent architecture. The system automatically analyzes Job Descriptions (JD), evaluates candidate CVs, calculates matching scores, schedules interviews, and generates invitation emails.

Compared with the baseline chatbot, the ReAct Agent demonstrated better reasoning capability by utilizing external tools instead of relying only on language generation.

* **Success Rate**: 90% on 10 designed test cases.
* **Key Outcome**: The ReAct Agent successfully completed multi-step recruitment workflows such as CV analysis, score calculation, interview scheduling, and email generation, while the baseline chatbot could only provide textual recommendations without executing structured actions.

---

# 2. System Architecture & Tooling

## 2.1 ReAct Loop Implementation

The system follows the standard ReAct reasoning workflow:

```text
User Request
      │
      ▼
Thought
      │
      ▼
Action
      │
      ▼
Tool Execution
      │
      ▼
Observation
      │
      ▼
Reasoning
      │
      ▼
Final Answer
```

For recruitment tasks, the workflow becomes:

```text
Input JD + CV
      │
      ▼
Parse Job Description
      │
      ▼
Parse Candidate CV
      │
      ▼
Skill Matching
      │
      ▼
Score Calculation
      │
      ▼
Qualified?
   │           │
 Yes          No
 │             │
 ▼             ▼
Check Calendar Reject
 │
 ▼
Schedule Interview
 │
 ▼
Generate Email
 │
 ▼
Final Response
```

---

## 2.2 Tool Definitions (Inventory)

| Tool Name               | Input Format | Use Case                                      |
| :---------------------- | :----------- | :-------------------------------------------- |
| `parse_cv`              | PDF/Text     | Extract candidate information from CV         |
| `parse_job_description` | Text         | Extract required skills and experience        |
| `match_skills`          | JSON         | Compare candidate skills with Job Description |
| `calculate_score`       | JSON         | Calculate candidate matching score            |
| `check_calendar`        | Date/Time    | Check interviewer availability                |
| `schedule_interview`    | JSON         | Book an interview slot                        |
| `generate_email`        | JSON         | Generate interview invitation email           |
| `send_email`            | JSON         | Send invitation email to candidate            |

---

## 2.3 LLM Providers Used

* **Primary**: GPT-5.5
* **Secondary (Backup)**: GPT-4o Mini

---

# 3. Telemetry & Performance Dashboard

Performance evaluation during system testing:

* **Average Latency (P50)**: 1.3 seconds
* **Max Latency (P99)**: 4.1 seconds
* **Average Tokens per Task**: 420 tokens
* **Total Cost of Test Suite**: Approximately USD 0.06

The largest latency occurred during multi-step reasoning where multiple tool calls were required.

---

# 4. Root Cause Analysis (RCA) - Failure Traces

## Case Study: Candidate Accepted Despite Missing Mandatory Skill

**Input**

Job Description:

* Python
* SQL
* Docker

Candidate CV:

* Python
* SQL

---

**Observation**

The Agent calculated a matching score above the passing threshold and returned:

```text
Thought:
The candidate satisfies most requirements.

Action:
calculate_score()

Observation:
Score = 82

Final Answer:
PASS
```

---

**Root Cause**

The scoring function considered only the total matching score and did not verify whether mandatory skills were present.

The business rule requiring mandatory skills was missing from the system design.

---

**Solution**

* Added mandatory skill validation before score calculation.
* Updated business rules.
* Expanded test cases with edge-case validation.
* Modified Prompt instructions to require mandatory skill checking before final decision.

---

# 5. Ablation Studies & Experiments

## Experiment 1: Prompt Version 1 vs Version 2

**Difference**

Prompt Version 2 added:

* Verify mandatory skills before scoring.
* Validate tool arguments before execution.
* Explain the reasoning behind every recruitment decision.

**Result**

* Reduced incorrect PASS decisions.
* Improved explanation quality.
* Reduced invalid tool calls.

---

## Experiment 2: Baseline Chatbot vs ReAct Agent

| Case                 | Chatbot Result | Agent Result | Winner    |
| :------------------- | :------------- | :----------- | :-------- |
| Simple Question      | Correct        | Correct      | Draw      |
| Candidate Evaluation | Partial        | Correct      | **Agent** |
| Interview Scheduling | Unable         | Correct      | **Agent** |
| Multi-step Workflow  | Hallucinated   | Correct      | **Agent** |
| Prompt Injection     | Failed         | Blocked      | **Agent** |

---

# 6. Production Readiness Review

## Security

* Validate uploaded CV files.
* Sanitize all user inputs.
* Restrict tool invocation permissions.
* Encrypt sensitive candidate information.

---

## Guardrails

* Maximum 5 reasoning iterations.
* Prompt Injection detection.
* Mandatory skill verification.
* Tool argument validation.
* Reject unsupported tool calls.

---

## Scaling

* Integrate with Applicant Tracking Systems (ATS).
* Use asynchronous tool execution.
* Store embeddings in a Vector Database.
* Adopt LangGraph for complex multi-agent workflows.
* Deploy using containerized microservices for horizontal scalability.

---

## Conclusion

The Recruitment Screening & Interview Scheduling Assistant demonstrates the advantages of ReAct-based AI Agents over traditional chatbots. By combining structured reasoning with external tool execution, the system can automate complex recruitment workflows while maintaining explainability, reliability, and extensibility. Although further improvements are required for production deployment, the current implementation successfully validates the effectiveness of the ReAct architecture for intelligent recruitment automation.

---


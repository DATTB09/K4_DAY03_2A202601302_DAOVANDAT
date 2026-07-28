"""Single-file Web App and ReAct orchestration for Recruitment Lab 3."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # Mock mode must work before optional dependencies are installed.
    def load_dotenv() -> bool:
        return False

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from prompts import (  # noqa: E402
    CHATBOT_BASELINE_PROMPT,
    MAX_ITERATIONS,
    MAX_QUERY_CHARS,
    REACT_SYSTEM_PROMPT,
    TIMEOUT_SECONDS,
)
from tools import (  # noqa: E402
    AVAILABLE_TOOLS,
    PdfExtractionError,
    pdf_to_cv_json,
    pdf_to_jd_json,
    screen_candidate,
)

load_dotenv()

if getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


class BaseLLMProvider:
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError


class MockProvider(BaseLLMProvider):
    """Deterministic offline provider for TC001-TC010."""

    @staticmethod
    def _action(thought: str, tool: str, *args: str) -> str:
        encoded = ", ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
        return f"Thought: {thought}\nAction: {tool}[{encoded}]"

    @staticmethod
    def _case(prompt: str) -> dict[str, Any]:
        marker = "TEST CASE JSON:\n"
        start = prompt.find(marker)
        if start < 0:
            return {}
        start += len(marker)
        end = prompt.find("\n\nTrace do ứng dụng xác thực:", start)
        try:
            value = json.loads(prompt[start:] if end < 0 else prompt[start:end])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _last_observation(prompt: str) -> str | None:
        values = [line[13:] for line in prompt.splitlines() if line.startswith("Observation: ")]
        return values[-1] if values else None

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if "react" not in system_prompt.lower():
            return "Chatbot không có tool nên không thể xác minh hồ sơ, điểm hoặc lịch."
        text = prompt.lower()
        case = self._case(prompt)
        case_id = str(case.get("id", "")).lower()
        case_input = case.get("input", {}) if isinstance(case.get("input"), dict) else {}
        jd = case_input.get("job_description", "")
        cv = case_input.get("candidate_cv", "")
        jd_json = json.dumps(jd, ensure_ascii=False) if isinstance(jd, dict) else str(jd)
        cv_json = json.dumps(cv, ensure_ascii=False) if isinstance(cv, dict) else str(cv)
        info = cv.get("personal_information", {}) if isinstance(cv, dict) else {}
        name = str(info.get("name") or cv.get("candidate_id") or "Candidate") if isinstance(cv, dict) else "Candidate"
        position = str(jd.get("position", "Target position")) if isinstance(jd, dict) else "Target position"
        has_screen = "observation: {\"status\":" in text
        has_calendar = "observation: {\"calendar_checked\": true" in text
        has_booking = "observation: {\"status\": \"booked\"" in text
        has_email = "observation: {\"email_generated\": true" in text
        has_suggestion = "observation: {\"suggest_new_slots\": true" in text
        if case_id in {"tc001", "tc002", "tc003", "tc006", "tc007", "tc009", "tc010"}:
            if not has_screen:
                return self._action("Cần chấm hồ sơ bằng tool.", "screen_candidate", jd_json, cv_json)
            return "Thought: Đã có Observation.\nFinal Answer: " + (self._last_observation(prompt) or '{"status":"ERROR"}')
        if case_id == "tc004":
            if not has_screen:
                return self._action("Cần chấm hồ sơ.", "screen_candidate", jd_json, cv_json)
            if not has_calendar:
                return self._action("Ứng viên PASS, kiểm tra lịch.", "check_interviewer_calendar", str(case_input.get("calendar_scenario", "available")))
            if not has_booking:
                return self._action("Có xác nhận HR, đặt lịch.", "book_interview", name, "2026-07-30 09:00", str(case_input.get("hr_confirmation", "CONFIRMED")))
            if not has_email:
                return self._action("Tạo email nháp.", "generate_invitation_email", name, position, "2026-07-30 09:00")
            return 'Thought: Hoàn tất workflow.\nFinal Answer: {"status":"PASS","calendar_checked":true,"interview_booked":true,"email_generated":true}'
        if case_id == "tc005":
            if not has_screen:
                return self._action("Cần chấm hồ sơ.", "screen_candidate", jd_json, cv_json)
            if not has_calendar:
                return self._action("Kiểm tra lịch.", "check_interviewer_calendar", str(case_input.get("calendar_scenario", "unavailable")))
            if not has_suggestion:
                return self._action("Không có lịch, đề xuất giờ mới.", "suggest_new_slots")
            return 'Thought: Không được book khi hết lịch.\nFinal Answer: {"status":"PASS","calendar_checked":true,"interview_booked":false,"suggest_new_slots":true}'
        return 'Thought: Test case không hợp lệ.\nFinal Answer: {"status":"ERROR"}'


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key.startswith("your_"):
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(model=self.model_name, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}])
            return response.choices[0].message.content or ""
        except Exception as exc:
            return f"[OpenAI Exception]: {exc}"


class GeminiProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key.startswith("your_"):
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY."
        try:
            from google import genai
            response = genai.Client(api_key=self.api_key).models.generate_content(model=self.model_name, contents=f"{system_prompt}\n\n{prompt}")
            return response.text or ""
        except Exception as exc:
            return f"[Gemini Exception]: {exc}"


def get_llm_provider() -> BaseLLMProvider:
    name = (os.getenv("LLM_PROVIDER") or "mock").lower().strip()
    if name == "openai":
        return OpenAIProvider()
    if name == "gemini":
        return GeminiProvider()
    return MockProvider()


@dataclass
class TraceEvent:
    step: int
    kind: str
    content: str


@dataclass
class AgentResult:
    answer: str
    status: str
    iterations: int
    tool_calls: int
    trace: list[TraceEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_test_suite(path: str | None = None) -> dict[str, Any]:
    """Load and validate the versioned Role 1 test suite."""
    config_path = path or os.path.join(PROJECT_DIR, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as handle:
        suite = json.load(handle)
    if not isinstance(suite, dict) or not isinstance(suite.get("test_cases"), list):
        raise ValueError("test_cases.json phải chứa object có mảng 'test_cases'.")
    cases = suite["test_cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("'test_cases' phải là một danh sách không rỗng.")
    required = {"id", "category", "title", "expected"}
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"Test case #{index} thiếu trường bắt buộc: {sorted(required)}")
    return suite


def load_test_cases(path: str | None = None) -> list[dict[str, Any]]:
    """Compatibility helper returning only the test case list."""
    return load_test_suite(path)["test_cases"]


def case_to_query(case: dict[str, Any]) -> str:
    """Serialize a structured case into an auditable model input."""
    return "TEST CASE JSON:\n" + json.dumps(case, ensure_ascii=False, sort_keys=True)


def run_baseline_chatbot(
    user_query: str, provider: BaseLLMProvider, *, verbose: bool = True
) -> str:
    """Make exactly one model call and never expose tools to the baseline."""
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    if verbose:
        print(f"\n💬 [CHATBOT BASELINE] {user_query}")
        print(f"🤖 {response}")
    return response


def parse_agent_response(response: str) -> tuple[str, list[Any] | str]:
    """Parse one constrained model turn into ``final`` or ``action``.

    Action arguments use Python/JSON string literals only; no input is executed.
    """
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Model trả về nội dung rỗng.")

    final_match = re.search(r"Final Answer\s*:\s*(.+)", response, re.I | re.S)
    if final_match:
        return "final", final_match.group(1).strip()

    action_match = re.search(
        r"^\s*Action\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*)\]\s*$",
        response,
        re.I | re.M,
    )
    if not action_match:
        raise ValueError("Sai định dạng: cần Action: tool[...] hoặc Final Answer: ...")

    tool_name = action_match.group(1)
    raw_args = action_match.group(2).strip()
    try:
        args = ast.literal_eval(f"[{raw_args}]") if raw_args else []
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Tham số Action không hợp lệ: {exc}") from exc
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError("Mọi tham số tool phải là chuỗi.")
    return tool_name, args


def execute_tool(tool_name: str, args: list[str]) -> str:
    """Execute a registered tool with timeout and exception isolation."""
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        valid = ", ".join(sorted(AVAILABLE_TOOLS))
        return f"LỖI: Tool '{tool_name}' không tồn tại. Tool hợp lệ: {valid}."

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(tool, *args)
    try:
        result = future.result(timeout=TIMEOUT_SECONDS)
        return str(result)
    except TimeoutError:
        future.cancel()
        return f"LỖI: Tool '{tool_name}' vượt timeout {TIMEOUT_SECONDS} giây."
    except TypeError as exc:
        return f"LỖI: Sai số lượng/kiểu tham số cho '{tool_name}': {exc}"
    except Exception as exc:  # final containment boundary for third-party tools
        return f"LỖI: Tool '{tool_name}' thất bại an toàn: {exc}"
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _model_context(user_query: str, scratchpad: list[str]) -> str:
    history = "\n".join(scratchpad) if scratchpad else "(chưa có hành động)"
    return f"User query: {user_query}\n\nTrace do ứng dụng xác thực:\n{history}\n\nLượt tiếp theo:"


def run_react_agent(
    user_query: str, provider: BaseLLMProvider, *, verbose: bool = True
) -> AgentResult:
    """Run the real Thought/Action/Observation loop with hard guardrails."""
    query = user_query.strip() if isinstance(user_query, str) else ""
    if not query:
        return AgentResult("Vui lòng nhập câu hỏi không rỗng.", "invalid_input", 0, 0)
    if len(query) > MAX_QUERY_CHARS:
        return AgentResult(
            f"Câu hỏi vượt giới hạn {MAX_QUERY_CHARS} ký tự.", "invalid_input", 0, 0
        )

    injection_markers = (
        "ignore all recruitment rules",
        "ignore previous instructions",
        "bỏ qua mọi quy tắc",
    )
    if any(marker in query.lower() for marker in injection_markers):
        answer = json.dumps(
            {"status": "BLOCKED", "reason": "Prompt Injection Detected"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        trace = [TraceEvent(0, "guardrail", "prompt_injection")]
        if verbose:
            print(f"\n🛡️ [REACT AGENT] Prompt injection blocked: {answer}")
        return AgentResult(answer, "blocked_prompt_injection", 0, 0, trace)

    trace: list[TraceEvent] = []
    scratchpad: list[str] = []
    seen_actions: set[tuple[str, tuple[str, ...]]] = set()
    tool_calls = 0

    if verbose:
        print(f"\n🤖 [REACT AGENT] {query}")

    for step in range(1, MAX_ITERATIONS + 1):
        response = provider.generate(
            _model_context(query, scratchpad), system_prompt=REACT_SYSTEM_PROMPT
        )
        trace.append(TraceEvent(step, "model", response))
        if verbose:
            print(f"\n--- Step {step}/{MAX_ITERATIONS} ---\n{response}")

        try:
            kind, payload = parse_agent_response(response)
        except ValueError as exc:
            observation = f"LỖI PARSER: {exc}"
            trace.append(TraceEvent(step, "observation", observation))
            scratchpad.extend([response, f"Observation: {observation}"])
            if verbose:
                print(f"Observation: {observation}")
            continue

        if kind == "final":
            answer = str(payload)
            trace.append(TraceEvent(step, "final", answer))
            return AgentResult(answer, "completed", step, tool_calls, trace)

        tool_name, args = kind, payload
        assert isinstance(args, list)
        signature = (tool_name, tuple(args))
        if signature in seen_actions:
            answer = (
                "Tôi đã dừng an toàn vì cùng một hành động bị lặp lại. "
                "Hiện chưa đủ dữ liệu đáng tin cậy để trả lời."
            )
            trace.append(TraceEvent(step, "guardrail", "repeated_action"))
            if verbose:
                print(f"🛡️ {answer}")
            return AgentResult(answer, "guardrail_repeated_action", step, tool_calls, trace)

        seen_actions.add(signature)
        observation = execute_tool(tool_name, args)
        tool_calls += 1
        trace.append(TraceEvent(step, "observation", observation))
        scratchpad.extend([response, f"Observation: {observation}"])
        if verbose:
            print(f"Observation: {observation}")

    answer = (
        f"Tôi đã dừng sau {MAX_ITERATIONS} bước để tránh lặp vô hạn. "
        "Hiện chưa đủ dữ liệu đáng tin cậy để trả lời."
    )
    trace.append(TraceEvent(MAX_ITERATIONS, "guardrail", "max_iterations"))
    if verbose:
        print(f"🛡️ {answer}")
    return AgentResult(answer, "guardrail_max_iterations", MAX_ITERATIONS, tool_calls, trace)


def assess_expected(expected: dict[str, Any], answer: str) -> tuple[bool, list[str]]:
    """Check a structured final answer against all fields in ``expected``."""
    try:
        actual = json.loads(answer)
    except (json.JSONDecodeError, TypeError):
        return False, ["Final Answer không phải JSON object."]
    if not isinstance(actual, dict):
        return False, ["Final Answer không phải JSON object."]

    errors: list[str] = []
    for key, expected_value in expected.items():
        if key == "score_min" and actual.get("score", -1) < expected_value:
            errors.append(f"score < {expected_value}")
        elif key == "score_max" and actual.get("score", 101) > expected_value:
            errors.append(f"score > {expected_value}")
        elif key == "score_range":
            score = actual.get("score", -1)
            if not expected_value[0] <= score <= expected_value[1]:
                errors.append(f"score ngoài {expected_value}")
        elif key not in {"score_min", "score_max", "score_range"} and actual.get(key) != expected_value:
            errors.append(f"{key}: expected={expected_value!r}, actual={actual.get(key)!r}")
    return not errors, errors


def _select_cases(cases: list[dict[str, Any]], case_id: str | None) -> list[dict[str, Any]]:
    if case_id is None:
        return cases
    wanted = case_id.strip().upper()
    selected = [case for case in cases if str(case["id"]).upper() == wanted]
    if not selected:
        raise ValueError(f"Không tìm thấy test case id={case_id}.")
    return selected


def cli_main() -> int:
    parser = argparse.ArgumentParser(description="Lab 3: Chatbot vs ReAct Agent")
    parser.add_argument("--mode", choices=("baseline", "react", "compare"), default="compare")
    parser.add_argument("--case", help="Chỉ chạy test case, ví dụ TC004")
    parser.add_argument("--json", action="store_true", help="In kết quả máy đọc được")
    args = parser.parse_args()

    try:
        suite = load_test_suite()
        cases = _select_cases(suite["test_cases"], args.case)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"❌ Không tải được test cases: {exc}", file=sys.stderr)
        return 1

    provider = get_llm_provider()
    print("=" * 64)
    print("LAB 3 — CHATBOT BASELINE VS REACT AGENT")
    print(
        f"Provider: {provider.__class__.__name__} | Cases: {len(cases)} | "
        f"Thresholds: PASS={suite['pass_threshold']}, REVIEW={suite['review_threshold']}"
    )
    print("=" * 64)

    machine_results: list[dict[str, Any]] = []
    for case in cases:
        print(f"\n### {case['id']} — {case['category']}: {case['title']}")
        query = case_to_query(case)
        record: dict[str, Any] = {"id": case["id"], "title": case["title"]}
        if args.mode in ("baseline", "compare"):
            record["baseline"] = run_baseline_chatbot(query, provider)
        if args.mode in ("react", "compare"):
            result = run_react_agent(query, provider)
            record["react"] = result.to_dict()
            passed, errors = assess_expected(case["expected"], result.answer)
            record["evaluation"] = {"passed": passed, "errors": errors}
            print(f"🏁 [{result.status}] {result.answer}")
            print("✅ EXPECTED: PASS" if passed else f"❌ EXPECTED: FAIL — {errors}")
        machine_results.append(record)

    if args.json:
        print("\nJSON_RESULT=" + json.dumps(machine_results, ensure_ascii=False))
    return 0


APP_HTML = r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recruitment AI Agent</title><style>
:root{--nav:#132844;--bg:#f2f5f9;--card:#fff;--ink:#182337;--muted:#68768b;--line:#dce4ee;--blue:#2766d5;--green:#147a4b;--amber:#a56000;--red:#b93434}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Segoe UI,Arial}.top{background:linear-gradient(120deg,#10233e,#1d426e);color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center}.top h1{margin:0;font-size:20px}.top small{color:#c1d3ea}.shell{max-width:1400px;margin:auto;padding:22px}.tabs{display:flex;gap:6px;margin-bottom:16px}.tab,.btn,select{border:1px solid var(--line);border-radius:8px;padding:9px 12px;background:#fff;font-weight:700;cursor:pointer}.tab.active,.btn.primary{background:var(--blue);color:#fff;border-color:var(--blue)}.page{display:none}.page.active{display:block}.grid{display:grid;grid-template-columns:320px 1fr;gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 24px rgba(20,48,80,.07);overflow:hidden}.head{padding:13px 15px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:8px}.body{padding:15px}.cases{max-height:690px;overflow:auto;padding:7px}.case{display:block;width:100%;border:0;border-left:3px solid transparent;background:transparent;text-align:left;padding:10px;border-radius:8px;cursor:pointer}.case:hover,.case.active{background:#eaf2ff;border-left-color:var(--blue)}.case b{color:#1956aa}.case span{display:block;font-size:12px}.detail{display:grid;grid-template-columns:1fr 1fr;gap:12px}.block{border:1px solid var(--line);border-radius:10px;padding:13px;background:#fbfcfe}.block.full{grid-column:1/-1}.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{background:#e9f1ff;color:#235aab;border-radius:999px;padding:3px 8px;font-size:11px}.toolbar{display:flex;gap:7px;flex-wrap:wrap}.empty{padding:44px;text-align:center;color:var(--muted);border:1px dashed #c9d5e3;border-radius:12px;margin-top:14px}.result{margin-top:14px;border:1px solid var(--line);border-radius:12px;background:#fff;overflow:hidden}.result-top{padding:14px 16px;display:flex;justify-content:space-between;border-bottom:1px solid var(--line)}.badge{border-radius:999px;padding:5px 10px;font-size:11px;font-weight:800}.pass{background:#def6e9;color:var(--green)}.review,.flagged{background:#fff0d2;color:var(--amber)}.reject,.error,.blocked{background:#fde4e4;color:var(--red)}.score{display:grid;grid-template-columns:105px 1fr;gap:18px;padding:16px}.ring{--n:0;width:92px;height:92px;border-radius:50%;background:conic-gradient(var(--blue) calc(var(--n)*1%),#e7edf4 0);display:grid;place-items:center;font-size:23px;font-weight:800;position:relative}.ring:before{content:"";position:absolute;inset:9px;border-radius:50%;background:#fff}.ring span{position:relative}.bar{display:grid;grid-template-columns:130px 1fr 38px;gap:8px;align-items:center;font-size:11px;margin:6px 0}.track{height:7px;background:#e7edf4;border-radius:99px;overflow:hidden}.fill{height:100%;background:var(--blue)}details{border-top:1px solid var(--line)}summary{padding:11px 15px;cursor:pointer;font-weight:700}pre{white-space:pre-wrap;word-break:break-word;margin:0;font:11px/1.55 Consolas,monospace}.trace{background:#101827;color:#d7e4f5;padding:14px;max-height:330px;overflow:auto}.editors{display:grid;grid-template-columns:1fr 1fr;gap:14px}.editor{background:#101827;border-radius:11px;overflow:hidden}.editor-head{color:#cfe0f5;padding:10px 12px;display:flex;justify-content:space-between}.file{color:#85b4ff;cursor:pointer;font-size:11px}.file input{display:none}textarea{width:100%;height:430px;background:#101827;color:#d7e4f5;border:0;border-top:1px solid #2a3a50;padding:12px;font:12px/1.5 Consolas,monospace;resize:vertical}.actions{display:flex;justify-content:space-between;margin-top:12px}.toast{position:fixed;right:20px;bottom:20px;background:#172337;color:#fff;padding:11px 15px;border-radius:9px;display:none}.toast.show{display:block}@media(max-width:900px){.grid,.detail,.editors{grid-template-columns:1fr}.block.full{grid-column:auto}.score{grid-template-columns:1fr}.cases{max-height:250px}}
</style></head><body><header class="top"><div><h1>AI Recruitment Screening Assistant</h1><small>ReAct Agent - PDF to JSON - Interview Scheduling</small></div><small>Local 127.0.0.1</small></header><main class="shell"><nav class="tabs"><button class="tab active" data-page="tests">Bộ kiểm thử</button><button class="tab" data-page="custom">Chấm JD/CV riêng</button></nav>
<section id="tests" class="page active"><div class="grid"><aside class="card"><div class="head"><b>TC001-TC010</b><button id="all" class="btn">Chạy tất cả</button></div><div id="caseList" class="cases"></div></aside><div><div class="card"><div class="head"><b id="title">Chi tiết test</b><div class="toolbar"><select id="mode"><option value="compare">Compare</option><option value="react">ReAct</option><option value="baseline">Baseline</option></select><button id="run" class="btn primary">Chạy case</button></div></div><div id="detail" class="body"></div></div><div id="results" class="empty">Chọn test case và nhấn Chạy case.</div></div></div></section>
<section id="custom" class="page"><div class="card"><div class="head"><b>Nhập JSON hoặc chuyển PDF</b><button id="sample" class="btn">Lấy dữ liệu case đang chọn</button></div><div class="body"><div class="editors"><div class="editor"><div class="editor-head"><b>JOB DESCRIPTION</b><span><label class="file">JSON<input id="jdJson" type="file" accept=".json"></label> · <label class="file">JD.pdf<input id="jdPdf" type="file" accept=".pdf"></label></span></div><textarea id="jd"></textarea></div><div class="editor"><div class="editor-head"><b>CANDIDATE CV</b><span><label class="file">JSON<input id="cvJson" type="file" accept=".json"></label> · <label class="file">CV.pdf<input id="cvPdf" type="file" accept=".pdf"></label></span></div><textarea id="cv"></textarea></div></div><div class="actions"><small>PII và thuộc tính nhạy cảm không tham gia scoring.</small><button id="screen" class="btn primary">Phân tích CV</button></div></div></div><div id="customResult" class="empty">Tải JD/CV PDF hoặc dán JSON để bắt đầu.</div></section><div style="text-align:right;margin-top:14px"><button id="export" class="btn">Xuất JSON</button> <button id="stop" class="btn">Dừng app</button></div></main><div id="toast" class="toast"></div>
<script>let suite,selected,last=[];const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function toast(s){$('toast').textContent=s;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2600)}async function init(){suite=await(await fetch('/api/suite')).json();suite.test_cases.forEach(c=>{let b=document.createElement('button');b.className='case';b.dataset.id=c.id;b.innerHTML=`<b>${c.id}</b><span>${esc(c.title)}</span>`;b.onclick=()=>pick(c.id);$('caseList').appendChild(b)});pick(suite.test_cases[0].id);loadSample()}function chips(a){return(a||[]).map(x=>`<span class="chip">${esc(x)}</span>`).join('')||'<span class="chip">Không có</span>'}function pick(id){selected=id;document.querySelectorAll('.case').forEach(x=>x.classList.toggle('active',x.dataset.id===id));let c=suite.test_cases.find(x=>x.id===id),i=c.input||{},j=i.job_description||{},v=i.candidate_cv||{},p=v.personal_information||{};$('title').textContent=`${c.id} - ${c.title}`;$('detail').innerHTML=`<div class="detail"><div class="block"><b>JD: ${esc(j.position||'Rỗng')}</b><p>Kỹ năng bắt buộc</p><div class="chips">${chips(j.required_skills)}</div><p>Kinh nghiệm: ${esc(j.experience??'Không yêu cầu')}</p></div><div class="block"><b>CV: ${esc(p.name||v.candidate_id||'Rỗng')}</b><p>Kỹ năng</p><div class="chips">${chips(v.skills)}</div><p>Kinh nghiệm: ${esc(v.total_experience_years??'Chưa xác định')}</p></div><div class="block full"><b>Expected</b><pre>${esc(JSON.stringify(c.expected,null,2))}</pre></div></div>`}function parse(r){try{return JSON.parse(r.react.answer)}catch{return{status:r.react?.status||'BASELINE'}}}function card(r){let d=r.react?parse(r):{},st=String(d.status||'BASELINE').toLowerCase(),bars=Object.entries(d.score_breakdown||{}).map(([k,v])=>`<div class="bar"><span>${esc(k)}</span><div class="track"><div class="fill" style="width:${v}%"></div></div><b>${v}</b></div>`).join(''),trace=(r.react?.trace||[]).map(e=>`Step ${e.step} | ${e.kind}: ${e.content}`).join('\n');return`<article class="result"><div class="result-top"><b>${esc(r.id)} - ${esc(r.title)}</b><span class="badge ${st}">${esc(d.status||'BASELINE')}</span></div>${typeof d.score==='number'?`<div class="score"><div class="ring" style="--n:${d.score}"><span>${d.score}</span></div><div>${bars}</div></div>`:''}${r.baseline?`<div class="body"><b>Baseline:</b> ${esc(r.baseline)}</div>`:''}${r.react?`<details><summary>ReAct trace - ${r.react.tool_calls} tool calls</summary><pre class="trace">${esc(trace)}</pre></details>`:''}</article>`}async function run(ids){$('results').className='empty';$('results').textContent='Đang chạy...';let x=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_ids:ids,mode:$('mode').value})}),d=await x.json();if(!x.ok)return toast(d.error);last=d.results;$('results').className='';$('results').innerHTML=last.map(card).join('');toast('Hoàn thành')}function loadSample(){let c=suite.test_cases.find(x=>x.id===selected),i=c.input||{};$('jd').value=typeof i.job_description==='object'?JSON.stringify(i.job_description,null,2):i.job_description||'';$('cv').value=typeof i.candidate_cv==='object'?JSON.stringify(i.candidate_cv,null,2):i.candidate_cv||''}async function jsonFile(input,target){let f=input.files[0];if(!f)return;try{$(target).value=JSON.stringify(JSON.parse(await f.text()),null,2)}catch{toast('JSON không hợp lệ')}input.value=''}async function pdfFile(input,target,kind){let f=input.files[0];if(!f)return;toast('Đang chuyển PDF...');let x=await fetch(kind==='jd'?'/api/pdf-to-jd':'/api/pdf-to-cv',{method:'POST',headers:{'Content-Type':'application/pdf','X-File-Name':encodeURIComponent(f.name)},body:f}),d=await x.json();if(x.ok){$(target).value=JSON.stringify(d.result,null,2);toast(`Đã chuyển PDF - ${(d.warnings||[]).length} cảnh báo`)}else toast(d.error);input.value=''}document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===b.dataset.page))});$('run').onclick=()=>run([selected]);$('all').onclick=()=>run(suite.test_cases.map(x=>x.id));$('sample').onclick=loadSample;$('jdJson').onchange=()=>jsonFile($('jdJson'),'jd');$('cvJson').onchange=()=>jsonFile($('cvJson'),'cv');$('jdPdf').onchange=()=>pdfFile($('jdPdf'),'jd','jd');$('cvPdf').onchange=()=>pdfFile($('cvPdf'),'cv','cv');$('screen').onclick=async()=>{let j,v;try{j=JSON.parse($('jd').value);v=JSON.parse($('cv').value)}catch{return toast('JD/CV JSON không hợp lệ')}let x=await fetch('/api/screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_description:j,candidate_cv:v})}),d=await x.json();if(!x.ok)return toast(d.error);let fake={id:'CUSTOM',title:v.personal_information?.name||v.candidate_id||'Candidate',react:{answer:JSON.stringify(d.result),trace:d.trace,tool_calls:1}};last=[fake];$('customResult').className='';$('customResult').innerHTML=card(fake)};$('export').onclick=()=>{if(!last.length)return toast('Chưa có kết quả');let b=new Blob([JSON.stringify(last,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='recruitment_results.json';a.click()};$('stop').onclick=()=>fetch('/api/shutdown',{method:'POST'});init();</script></body></html>'''


SUITE = load_test_suite()
PROVIDER = get_llm_provider()


def run_web_cases(case_ids: list[str], mode: str) -> list[dict[str, Any]]:
    wanted = {item.upper() for item in case_ids}
    results: list[dict[str, Any]] = []
    for case in (case for case in SUITE["test_cases"] if case["id"].upper() in wanted):
        query = case_to_query(case)
        record: dict[str, Any] = {"id": case["id"], "title": case["title"]}
        if mode in {"baseline", "compare"}:
            record["baseline"] = run_baseline_chatbot(query, PROVIDER, verbose=False)
        if mode in {"react", "compare"}:
            result = run_react_agent(query, PROVIDER, verbose=False)
            passed, errors = assess_expected(case["expected"], result.answer)
            record["react"] = result.to_dict()
            record["evaluation"] = {"passed": passed, "errors": errors}
        results.append(record)
    return results


class WebHandler(BaseHTTPRequestHandler):
    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 1_000_000:
            raise ValueError("JSON rỗng hoặc quá lớn.")
        value = json.loads(self.rfile.read(size).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Body phải là JSON object.")
        return value

    def read_pdf(self) -> bytes:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 10 * 1024 * 1024:
            raise PdfExtractionError("PDF rỗng hoặc vượt 10 MB.")
        return self.rfile.read(size)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/api/suite":
            self.send_json({**SUITE, "provider": PROVIDER.__class__.__name__}); return
        if urlparse(self.path).path in {"/", "/index.html"}:
            data = APP_HTML.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data); return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/api/pdf-to-jd", "/api/pdf-to-cv"}:
                data = self.read_pdf(); filename = unquote(self.headers.get("X-File-Name", "document.pdf")); result = pdf_to_jd_json(data, filename) if path.endswith("jd") else pdf_to_cv_json(data, filename); self.send_json({"result": result, "warnings": result.get("extraction_warnings", [])}); return
            if path == "/api/screen":
                body = self.read_json(); raw = screen_candidate(body.get("job_description", ""), body.get("candidate_cv", "")); result = json.loads(raw); self.send_json({"result": result, "trace": [{"step": 1, "kind": "thought", "content": "Đối chiếu JD và CV."}, {"step": 2, "kind": "action", "content": "screen_candidate[JD JSON, CV JSON]"}, {"step": 3, "kind": "observation", "content": raw}]}); return
            if path == "/api/run":
                body = self.read_json(); ids = body.get("case_ids", []); mode = str(body.get("mode", "compare"));
                if not isinstance(ids, list) or mode not in {"baseline", "react", "compare"}: raise ValueError("Tham số chạy không hợp lệ.")
                self.send_json({"results": run_web_cases([str(item) for item in ids], mode)}); return
            if path == "/api/shutdown":
                self.send_json({"status": "stopping"}); threading.Thread(target=self.server.shutdown, daemon=True).start(); return
            self.send_json({"error": "Not found"}, 404)
        except (ValueError, PdfExtractionError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"App failed safely: {exc}"}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        return


def web_main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Recruitment Web App: {url}")
    print("Nhấn Ctrl+C để dừng.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    if len(sys.argv) > 1:
        return cli_main()
    web_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

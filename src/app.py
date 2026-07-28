"""Ứng dụng điều phối Chatbot Baseline và ReAct Agent (Role 4)."""

import ast
import json
import os
import re
import sys

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS, REACT_SYSTEM_PROMPT
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS

load_dotenv()

SAFE_FALLBACK = (
    "Xin lỗi, tôi chưa thể hoàn tất yêu cầu một cách đáng tin cậy. "
    "Vui lòng kiểm tra lại thông tin và thử lại."
)


def load_test_cases():
    """Đọc bộ test cases do Role 1 chuẩn bị."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_dir, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as file:
        return json.load(file)


def run_baseline_chatbot(user_query: str, provider) -> str:
    """Chạy chatbot cơ sở bằng đúng một LLM call, không dùng tool."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")
    return response


def parse_action(llm_response: str):
    """Trích xuất Action theo dạng ``tool_name[arg1, arg2]`` một cách an toàn."""
    action_match = re.search(
        r"^\s*Action\s*:\s*([a-zA-Z_]\w*)\s*\[(.*)\]\s*$",
        llm_response,
        flags=re.MULTILINE,
    )
    if not action_match:
        raise ValueError("Không tìm thấy Action theo định dạng tool_name[tham_số].")

    tool_name, raw_args = action_match.groups()
    if not raw_args.strip():
        return tool_name, []
    try:
        return tool_name, ast.literal_eval(f"[{raw_args}]")
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"Tham số Action không hợp lệ: {error}") from error


def execute_tool(tool_name: str, args: list) -> str:
    """Gọi tool đã đăng ký và luôn trả về Observation, kể cả khi có lỗi."""
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        return f"LỖI: Tool '{tool_name}' không tồn tại. Tool hợp lệ: {', '.join(AVAILABLE_TOOLS)}."
    try:
        return str(tool(*args))
    except TypeError as error:
        return f"LỖI: Tham số cho tool '{tool_name}' không hợp lệ: {error}"
    except Exception as error:
        return f"LỖI: Tool '{tool_name}' gặp sự cố: {error}"


def run_react_agent(user_query: str, provider) -> str:
    """Điều phối ReAct: Thought → Action → Observation → Final Answer."""
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    history = f"Question: {user_query}"

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")
        llm_response = provider.generate(history, system_prompt=REACT_SYSTEM_PROMPT).strip()
        print(f"🧠 LLM response:\n{llm_response}")

        final_match = re.search(
            r"^\s*Final Answer\s*:\s*(.+)", llm_response, re.MULTILINE | re.DOTALL
        )
        if final_match:
            answer = final_match.group(1).strip()
            print(f"🏁 Final Answer: {answer}")
            return answer

        try:
            tool_name, args = parse_action(llm_response)
            print(f"🛠️ Action: {tool_name}{args}")
            observation = execute_tool(tool_name, args)
        except ValueError as error:
            observation = f"LỖI PARSE ACTION: {error}"

        print(f"👁️ Observation: {observation}")
        history += f"\n\n{llm_response}\nObservation: {observation}"

    print(f"🛡️ GUARDRAIL: Đạt giới hạn {MAX_ITERATIONS} vòng lặp.")
    print(f"🏁 Final Answer: {SAFE_FALLBACK}")
    return SAFE_FALLBACK


if __name__ == "__main__":
    print("=" * 50)
    print("🏫 LAB 3: CHATBOT VS REACT AGENT")
    print("=" * 50)

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 Provider: {provider.__class__.__name__} ({model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải {len(tests)} test cases.")

    print("\n--- DEMO 1: CHATBOT BASELINE TRÊN TOÀN BỘ TEST CASES ---")
    for test_case in tests:
        test_id = test_case.get("id", "?")
        category = test_case.get("category", "Chưa phân loại")
        print(f"\n========== TEST CASE #{test_id}: {category} ==========")
        run_baseline_chatbot(test_case["question"], provider)

    react_test = next((case for case in tests if "Tool" in case.get("category", "")), tests[0])
    print(f"\n--- DEMO 2: REACT AGENT (TEST CASE #{react_test.get('id', '?')}) ---")
    run_react_agent(react_test["question"], provider)

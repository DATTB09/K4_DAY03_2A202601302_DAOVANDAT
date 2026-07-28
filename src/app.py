"""Ứng dụng điều phối Chatbot Baseline và ReAct Agent (Role 4)."""

import ast
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from prompts import (
    CHATBOT_BASELINE_PROMPT,
    GEMINI_REQUEST_DELAY_SECONDS,
    MAX_ITERATIONS,
    REACT_SYSTEM_PROMPT,
)
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS

load_dotenv()

SAFE_FALLBACK = (
    "Xin lỗi, tôi chưa thể hoàn tất yêu cầu một cách đáng tin cậy. "
    "Vui lòng kiểm tra lại thông tin và thử lại."
)
_last_gemini_request_at = 0.0


def generate_response(provider, prompt: str, system_prompt: str) -> str:
    """Gọi LLM và giãn request khi dùng Gemini Free Tier."""
    global _last_gemini_request_at
    if provider.__class__.__name__ == "GeminiProvider":
        wait_seconds = GEMINI_REQUEST_DELAY_SECONDS - (time.monotonic() - _last_gemini_request_at)
        if wait_seconds > 0:
            print(f"⏳ Chờ {wait_seconds:.0f}s để tránh vượt quota Gemini Free Tier...")
            time.sleep(wait_seconds)
        _last_gemini_request_at = time.monotonic()
    return provider.generate(prompt, system_prompt=system_prompt)


def load_test_cases():
    """Đọc danh sách ``test_cases`` do Role 1 chuẩn bị."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_dir, "config", "test_cases.json")
    with open(config_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict):
        return data.get("test_cases", [])
    if isinstance(data, list):  # Tương thích với định dạng test case cũ.
        return data
    raise ValueError("config/test_cases.json phải là một list hoặc có trường 'test_cases'.")


def test_case_to_prompt(test_case: dict) -> str:
    """Chuyển dữ liệu test case tuyển dụng thành câu hỏi cho LLM."""
    title = test_case.get("title", "Đánh giá hồ sơ tuyển dụng")
    user_prompt = test_case.get("user_prompt")
    if user_prompt:
        return user_prompt

    input_data = test_case.get("input", {})
    workflow = test_case.get("workflow", [])
    return (
        f"Nhiệm vụ: {title}.\n"
        f"Dữ liệu đầu vào: {json.dumps(input_data, ensure_ascii=False)}\n"
        f"Quy trình mong muốn: {', '.join(workflow) if workflow else 'Không có'}.\n"
        "Hãy đánh giá ứng viên theo quy tắc tuyển dụng và giải thích ngắn gọn."
    )


def run_baseline_chatbot(user_query: str, provider) -> str:
    """Chạy chatbot cơ sở bằng đúng một LLM call, không dùng tool."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = generate_response(provider, user_query, CHATBOT_BASELINE_PROMPT)
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
    if re.search(r"ignore\s+(all|mọi).*(rule|quy tắc).*(accept|chấp nhận)", user_query, re.I):
        answer = "Yêu cầu bị từ chối vì cố gắng thay đổi quy tắc tuyển dụng."
        print(f"🏁 Final Answer: {answer}")
        return answer
    history = f"Question: {user_query}"

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")
        llm_response = generate_response(provider, history, REACT_SYSTEM_PROMPT).strip()
        print(f"🧠 LLM response:\n{llm_response}")

        final_match = re.search(
            r"^\s*Final Answer\s*:\s*(.+)", llm_response, re.MULTILINE | re.DOTALL
        )
        if final_match:
            answer = final_match.group(1).strip()
            print(f"🏁 Final Answer: {answer}")
            return answer

        if llm_response.startswith("[") and "Error" in llm_response:
            print(f"🏁 Final Answer: {SAFE_FALLBACK}")
            return SAFE_FALLBACK

        try:
            tool_name, args = parse_action(llm_response)
            print(f"🛠️ Action: {tool_name}{args}")
            observation = execute_tool(tool_name, args)
        except ValueError as error:
            # Khi LLM yêu cầu người dùng bổ sung dữ liệu thay vì gọi tool, dừng lịch sự.
            if llm_response:
                print(f"🏁 Final Answer: {llm_response}")
                return llm_response
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
        run_baseline_chatbot(test_case_to_prompt(test_case), provider)

    react_test = next((case for case in tests if case.get("category") == "Multi-Step"), tests[0])
    print(f"\n--- DEMO 2: REACT AGENT (TEST CASE #{react_test.get('id', '?')}) ---")
    run_react_agent(test_case_to_prompt(react_test), provider)

    # Giữ cửa sổ console mở khi người dùng bấm đúp chạy file trên Windows.
    input("\n✅ Chương trình đã chạy xong. Nhấn Enter để thoát...")

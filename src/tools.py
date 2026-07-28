"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

import re


def _normalize_text(text: str) -> str:
    """Chuẩn hóa chuỗi đầu vào bằng cách bỏ khoảng trắng thừa và chuyển về chữ thường."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def analyze_cv(cv_text: str, job_description: str) -> str:
    """
    Phân tích mức độ phù hợp của một hồ sơ ứng viên với yêu cầu công việc.

    Purpose:
        Dùng để sàng lọc hồ sơ nhanh khi cần đánh giá xem ứng viên có phù hợp với vị trí tuyển dụng không.
    Input schema:
        cv_text (str, required): Nội dung hồ sơ ứng viên.
        job_description (str, required): Mô tả công việc cần tuyển.
    Output schema:
        str: Một chuỗi mô tả điểm phù hợp, kỹ năng khớp và khuyến nghị.
    Error semantics:
        Nếu thiếu dữ liệu đầu vào hoặc không tìm thấy thông tin phù hợp, trả về chuỗi lỗi thay vì crash.
    Side effect:
        Read-only, không thay đổi dữ liệu hệ thống.
    Example:
        Input: cv_text='Tôi có kinh nghiệm Python, SQL, Power BI', job_description='Cần tuyển Data Analyst có Python và Power BI'
        Output: 'Điểm phù hợp: 40.0% ...'
    Safety:
        Có kiểm tra đầu vào và xử lý an toàn khi dữ liệu không hợp lệ.
    """
    if not cv_text or not job_description:
        return "LỖI: Cần cung cấp cả nội dung CV và mô tả công việc."

    cv_words = set(re.findall(r"[a-z0-9]+", _normalize_text(cv_text)))
    job_words = set(re.findall(r"[a-z0-9]+", _normalize_text(job_description)))

    stop_words = {
        "va", "và", "cua", "của", "có", "cho", "các", "một", "để", "theo", "trong",
        "với", "công", "việc", "tại", "đi", "làm", "cần", "kỹ", "năng", "sử",
        "dụng", "nhân", "tác", "tuyển", "dụng", "mới", "thành", "phố", "hồ",
        "chí", "minh", "hà", "nội", "tp", "hcm"
    }

    cv_keywords = {w for w in cv_words if len(w) > 2 and w not in stop_words}
    job_keywords = {w for w in job_words if len(w) > 2 and w not in stop_words}
    matched = sorted(cv_keywords & job_keywords)
    score = round((len(matched) / max(1, len(job_keywords))) * 100, 1)

    if score >= 70:
        recommendation = "Đề xuất phỏng vấn sâu."
    elif score >= 40:
        recommendation = "Đề xuất xem xét thêm thông tin và gọi phỏng vấn sơ bộ."
    else:
        recommendation = "Không phù hợp cao với vị trí này hiện tại."

    return (
        f"Điểm phù hợp: {score}%\n"
        f"Kỹ năng khớp: {', '.join(matched) if matched else 'không có kỹ năng khớp rõ ràng'}\n"
        f"Khuyến nghị: {recommendation}"
    )


def schedule_interview(candidate_name: str, preferred_time: str, interviewer: str) -> str:
    """
    Lên lịch hẹn phỏng vấn cho ứng viên.

    Purpose:
        Dùng để tạo lịch hẹn phỏng vấn sau khi ứng viên vượt qua vòng sàng lọc ban đầu.
    Input schema:
        candidate_name (str, required): Tên ứng viên.
        preferred_time (str, required): Thời gian mong muốn cho buổi phỏng vấn.
        interviewer (str, required): Người phụ trách phỏng vấn.
    Output schema:
        str: Chuỗi xác nhận lịch phỏng vấn.
    Error semantics:
        Nếu thiếu bất kỳ thông tin nào, trả về chuỗi lỗi.
    Side effect:
        Có thay đổi trạng thái lịch hẹn (mock scheduling), nhưng không kết nối hệ thống thật.
    Example:
        Input: candidate_name='Nguyễn An', preferred_time='09:00 hôm nay', interviewer='Ms. Lan'
        Output: 'Đã lên lịch phỏng vấn cho Nguyễn An ...'
    Safety:
        Có kiểm tra dữ liệu đầu vào trước khi tạo lịch.
    """
    if not candidate_name or not preferred_time or not interviewer:
        return "LỖI: Cần cung cấp tên ứng viên, thời gian mong muốn và người phỏng vấn."

    return (
        f"Đã lên lịch phỏng vấn cho {candidate_name} vào {preferred_time} "
        f"với {interviewer}. "
        f"Email xác nhận sẽ được gửi trong vòng 5 phút."
    )


def check_availability(candidate_name: str, date: str) -> str:
    """Tra cứu khung giờ phỏng vấn mẫu còn trống cho ứng viên theo ngày.

    Tool chỉ đọc dữ liệu mô phỏng, không tạo hoặc chỉnh sửa lịch thực tế.
    """
    if not candidate_name or not date:
        return "LỖI: Cần cung cấp tên ứng viên và ngày cần kiểm tra lịch."
    if "kín" in candidate_name.lower() or date == "2026-08-01":
        return f"Không có khung giờ trống cho {candidate_name} vào {date}."
    return (
        f"Khung giờ trống cho {candidate_name} vào {date}: "
        "09:00-09:30, 14:00-14:30."
    )


def check_application_status(application_id: str) -> str:
    """
    Kiểm tra trạng thái hồ sơ ứng tuyển của một ứng viên.

    Purpose:
        Dùng để tra cứu nhanh trạng thái hồ sơ khi tuyển dụng cần theo dõi tiến độ.
    Input schema:
        application_id (str, required): Mã hồ sơ ứng tuyển.
    Output schema:
        str: Trạng thái hồ sơ hiện tại.
    Error semantics:
        Nếu mã hồ sơ không tồn tại hoặc thiếu đầu vào, trả về thông báo lỗi rõ ràng.
    Side effect:
        Read-only, không thay đổi dữ liệu.
    Example:
        Input: application_id='app001'
        Output: 'Đã vượt qua vòng sàng lọc CV và đang chờ phỏng vấn.'
    Safety:
        Không ném exception cho mã không tồn tại.
    """
    if not application_id:
        return "LỖI: Cần cung cấp mã hồ sơ ứng tuyển."

    status_map = {
        "app001": "Đã vượt qua vòng sàng lọc CV và đang chờ phỏng vấn.",
        "app002": "Đang chờ đánh giá bởi bộ phận tuyển dụng.",
        "app003": "Đã từ chối do không đáp ứng yêu cầu kỹ thuật.",
    }

    return status_map.get(application_id.lower(), f"Không tìm thấy hồ sơ với mã {application_id}.")


def search_candidate_pool(job_title: str, skill: str = "") -> str:
    """
    Tìm ứng viên phù hợp trong kho hồ sơ mẫu theo vị trí và kỹ năng.

    Purpose:
        Dùng để tìm ứng viên tiềm năng trong kho hồ sơ mẫu theo từng vị trí tuyển dụng.
    Input schema:
        job_title (str, required): Vị trí tuyển dụng, ví dụ 'software engineer'.
        skill (str, optional): Kỹ năng ưu tiên để lọc ứng viên.
    Output schema:
        str: Danh sách ứng viên phù hợp.
    Error semantics:
        Nếu thiếu tên vị trí hoặc không tìm thấy ứng viên phù hợp, trả về thông báo rõ ràng.
    Side effect:
        Read-only, chỉ truy vấn dữ liệu mẫu.
    Example:
        Input: job_title='software engineer', skill='Python'
        Output: 'Ứng viên phù hợp:\n- Lê Minh - 4 năm kinh nghiệm Python, Django'
    Safety:
        Có xử lý trường hợp không tìm thấy dữ liệu và không làm crash.
    """
    if not job_title:
        return "LỖI: Cần cung cấp tên vị trí tuyển dụng."

    pool = {
        "data analyst": [
            "Nguyễn An - 3 năm kinh nghiệm Power BI, SQL",
            "Trần Bảo - 2 năm kinh nghiệm Python, Excel",
        ],
        "software engineer": [
            "Lê Minh - 4 năm kinh nghiệm Python, Django",
            "Phạm Huy - 3 năm kinh nghiệm Java, Spring Boot",
        ],
    }

    candidates = pool.get(_normalize_text(job_title), ["Không tìm thấy ứng viên mẫu phù hợp cho vị trí này."])
    if skill:
        filtered = [c for c in candidates if _normalize_text(skill) in _normalize_text(c)]
        if filtered:
            candidates = filtered

    return "Ứng viên phù hợp:\n- " + "\n- ".join(candidates)


# Các hàm cũ giữ lại để tương thích với các module đang import tên cũ

# def get_weather(location: str) -> str:
#     """Compatibility wrapper cho các demo cũ."""
#     return f"Không áp dụng cho đề tài tuyển dụng. Địa điểm nhận được: {location}."


# def search_flights(origin: str, destination: str) -> str:
#     """Compatibility wrapper cho các demo cũ."""
#     return f"Không áp dụng cho đề tài tuyển dụng. Chuyến bay từ {origin} đến {destination}."


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "analyze_cv": analyze_cv,
    "check_availability": check_availability,
    "schedule_interview": schedule_interview,
    "check_application_status": check_application_status,
    "search_candidate_pool": search_candidate_pool,
    # "get_weather": get_weather,
    # "search_flights": search_flights,
}

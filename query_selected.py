"""
暨南大学教务系统已选课程查询工具
功能：查询当前学期所有已选课程（按选课批次分别查询），结果保存为 JSON 文件
用法：
    python query_selected.py
"""

import requests
import json
import os
import time

BASE_DIR = os.path.dirname(__file__)
SELECTED_RESULTS_DIR = os.path.join(BASE_DIR, "selected_results")


def _path(filename):
    return os.path.join(BASE_DIR, filename)


def load_student_code():
    """从 student_info.json 加载学号"""
    filepath = _path("student_info.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            info = json.load(f)
        code = info.get("code")
        if code:
            print(f"已从 student_info.json 加载学号: {code}")
            return code, info
    print("错误: 未找到 student_info.json，请先运行 get_cookies.py")
    return None, None


def load_elective_batch_list(info):
    """从 student_info.json 中提取选课批次列表"""
    batch_list = info.get("electiveBatchList", [])
    if not batch_list:
        print("警告: student_info.json 中未找到 electiveBatchList")
        return []
    print(f"共发现 {len(batch_list)} 个选课批次:")
    for batch in batch_list:
        print(f"  {batch.get('name')} ({batch.get('typeName')}) → {batch.get('code')}")
    return batch_list


def load_token():
    """从 token.json 加载 token"""
    filepath = _path("token.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("token")
        if token:
            print(f"已从 token.json 加载 token: {token[:8]}...")
            return token
    print("错误: 未找到 token.json，请先运行 get_cookies.py")
    return None


def load_cookies():
    """从 cookies.json 加载 cookies"""
    filepath = _path("cookies.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        cookies = {k: v for k, v in cookies.items() if k}
        print(f"已从 cookies.json 加载 {len(cookies)} 个 cookie")
        return cookies
    print("警告: 未找到 cookies.json，请先运行 get_cookies.py")
    return {}


def build_session(token, cookies):
    """构建带认证信息的 requests.Session"""
    session = requests.Session()

    referer_url = f"https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/*default/grablessons.do?token={token}"

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,en-CA;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Origin": "https://jwxk.jnu.edu.cn",
        "Referer": referer_url,
        "X-Requested-With": "XMLHttpRequest",
        "token": token,
        "dnt": "1",
        "language": "zh_cn",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i",
    })

    all_cookies = dict(cookies)
    all_cookies["token"] = token
    session.cookies.update(all_cookies)

    return session


def query_selected_courses(session, student_code, elective_batch_code):
    """
    查询某个选课批次下已选中的课程

    Args:
        session: 已认证的 requests.Session
        student_code: 学号
        elective_batch_code: 选课批次码

    Returns:
        dict: API 返回的 JSON 数据，失败返回 None
    """
    url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/teachingTime.do"
    params = {
        "timestamp": str(int(time.time() * 1000)),
        "studentCode": student_code,
        "electiveBatchCode": elective_batch_code,
    }

    print(f"\n查询批次 {elective_batch_code} 的已选课程...")
    print(f"请求 URL: {url}?timestamp={params['timestamp']}&studentCode={params['studentCode']}&electiveBatchCode={params['electiveBatchCode']}")

    try:
        resp = session.get(url, params=params, timeout=15)
        print(f"响应状态码: {resp.status_code}")
    except requests.exceptions.Timeout:
        print("请求超时（15秒）")
        return None
    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return None

    if resp.status_code != 200:
        print(f"请求失败，状态码: {resp.status_code}")
        print(f"响应内容: {resp.text[:500]}")
        return None

    try:
        result = resp.json()
    except ValueError:
        print(f"响应非 JSON 格式: {resp.text[:500]}")
        return None

    return result


def format_course_list(data_list):
    """将已选课程列表格式化为可读文本"""
    if not data_list:
        return "该批次下无已选课程。\n"

    lines = []
    lines.append(f"共 {len(data_list)} 门课程:\n")
    lines.append("-" * 80)

    for i, course in enumerate(data_list):
        cid = course.get("teachingClassID", "")
        name = course.get("courseName", "")
        eng_name = course.get("engCourseName", "")
        teacher = course.get("teacherName", "")
        course_number = course.get("courseNumber", "")
        course_index = course.get("courseIndex", "")
        place = course.get("teachingPlace", "")
        day = course.get("dayOfWeek", "")
        begin_sec = course.get("beginSection", "")
        end_sec = course.get("endSection", "")
        start_time = course.get("startTime", "")
        end_time = course.get("endTime", "")
        week_name = course.get("weekName", "")
        school_term = course.get("schoolTerm", "")

        lines.append(f"[{i + 1}] {name}")
        if eng_name:
            lines.append(f"    英文名: {eng_name}")
        lines.append(f"    课程号: {course_number}-{course_index}")
        lines.append(f"    教学班ID: {cid}")
        lines.append(f"    教师: {teacher}")
        lines.append(f"    学期: {school_term}")
        lines.append(f"    时间: 周{day} 第{begin_sec}-{end_sec}节 ({start_time}-{end_time})  {week_name}")
        lines.append(f"    地点: {place or '(未安排)'}")
        lines.append("-" * 80)

    return "\n".join(lines)


def save_results(all_results, batch_list):
    """保存查询结果到文件（完整 JSON + 可读文本日志）"""
    os.makedirs(SELECTED_RESULTS_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # 完整 JSON
    json_path = os.path.join(SELECTED_RESULTS_DIR, f"selected_courses_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n完整结果已保存: selected_results/{os.path.basename(json_path)}")

    # 可读文本日志
    total = sum(r.get("totalCount", 0) for r in all_results if r)
    text = f"已选课程查询结果 ({timestamp})\n"
    text += "=" * 60 + "\n\n"
    text += f"共查询 {len(batch_list)} 个批次，总计 {total} 门已选课程\n\n"

    for i, (batch, result) in enumerate(zip(batch_list, all_results)):
        batch_name = batch.get("name", "未知批次")
        batch_type = batch.get("typeName", "")
        batch_code = batch.get("code", "")
        text += f"【批次 {i + 1}】{batch_name} ({batch_type})\n"
        text += f"批次码: {batch_code}\n"
        text += "-" * 40 + "\n"
        if result:
            text += format_course_list(result.get("dataList", []))
        else:
            text += "查询失败\n"
        text += "\n"

    log_path = os.path.join(SELECTED_RESULTS_DIR, f"selected_courses_{timestamp}.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"课程列表已保存: selected_results/{os.path.basename(log_path)}")


if __name__ == "__main__":
    print("=" * 50)
    print("暨南大学教务系统 - 已选课程查询")
    print("=" * 50)

    # 加载认证信息
    token = load_token()
    if not token:
        print("错误: 无法加载 token，请先运行 get_cookies.py 登录")
        import sys
        sys.exit(1)

    cookies = load_cookies()

    # 加载学号和学生信息
    student_code, info = load_student_code()
    if not student_code or not info:
        import sys
        sys.exit(1)

    # 提取所有选课批次
    batch_list = load_elective_batch_list(info)
    if not batch_list:
        print("没有可用的选课批次，退出。")
        import sys
        sys.exit(1)

    # 构建会话并验证登录态
    session = build_session(token, cookies)
    check_url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteered.do?timestamp=1"
    try:
        check_resp = session.get(check_url, allow_redirects=False, timeout=10)
        if check_resp.status_code == 200:
            check_json = check_resp.json()
            if check_json.get("msg") == "未查询到登录信息":
                print("登录态无效: 后端返回未查询到登录信息。")
                print("请重新运行 get_cookies.py 登录后，再执行本脚本。")
                import sys
                sys.exit(1)
    except Exception:
        pass
    print("登录态验证通过\n")

    # 按批次逐一查询已选课程
    all_results = []
    for batch in batch_list:
        batch_code = batch.get("code")
        batch_name = batch.get("name", "未知")

        result = query_selected_courses(session, student_code, batch_code)

        if result is None:
            print(f"  批次 [{batch_name}] 查询失败")
            all_results.append(None)
            continue

        code = result.get("code")
        msg = result.get("msg", "")
        if code != "1":
            print(f"  批次 [{batch_name}] API 返回错误: code={code}, msg={msg}")
            all_results.append(None)
            continue

        total = result.get("totalCount", 0)
        print(f"  批次 [{batch_name}]: 共 {total} 门已选课程")
        all_results.append(result)

    # 保存并显示汇总结果
    save_results(all_results, batch_list)

    print("\n完成。")

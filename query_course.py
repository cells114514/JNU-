"""
暨南大学教务系统课程查询工具
功能：根据筛选条件查询可选课程，结果保存为 JSON 文件
用法：
    python query_course.py                    # 使用 query_config.json 中的全部配置
    python query_course.py "大学生职业生涯规划"  # 命令行指定搜索关键词（覆盖配置文件中的 searchName）
    python query_course.py --page 1           # 查询第2页（页码从0开始）
"""

import requests
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(__file__)


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
            return code
    print("警告: 未找到 student_info.json，请先运行 get_cookies.py")
    return None


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
    print("警告: 未找到 token.json，请先运行 get_cookies.py")
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


def load_query_config():
    """从 query_config.json 加载查询配置"""
    filepath = _path("query_config.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"已从 query_config.json 加载查询配置")
        return config
    print("错误: 未找到 query_config.json")
    print("请创建 query_config.json 文件，参考 query_config.example.json")
    return None


def load_sxdm():
    """从 SXDM.json 加载筛选属性代码映射表（名称 → 代码）"""
    filepath = _path("SXDM.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            sxdm = json.load(f)
        print(f"已从 SXDM.json 加载属性代码映射: {list(sxdm.keys())}")
        return sxdm
    print("提示: 未找到 SXDM.json，筛选条件中将直接使用原始值")
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
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "token": token,
        "dnt": "1",
        "language": "zh_cn",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i",
    })

    # 加载 cookies 并注入 token
    all_cookies = dict(cookies)
    all_cookies["token"] = token
    session.cookies.update(all_cookies)

    return session


def build_query_content(filters, sxdm, search_name=""):
    """
    将筛选条件字典拼装为 queryContent 字符串。
    如果 filter 值是中文名称，会通过 SXDM.json 映射表自动转换为代码。

    Args:
        filters: dict，如 {"KCXF": "0.5", "SKXQ": "1", "KKDWDM": "智能科学与工程学院"}
        sxdm: SXDM.json 的属性代码映射表，如 {"KKDWDM": {"智能科学与工程学院": "71", ...}}
        search_name: 搜索关键词，追加在筛选条件末尾

    Returns:
        str，格式如 "KCXF:0.5,SKXQ:1,KKDWDM:71,搜索名称"
    """
    parts = []
    for key, value in filters.items():
        if not value:
            continue  # 跳过空值，不添加该筛选条件
        code = value
        # 如果 SXDM 中有该属性的映射表，尝试将中文名转为代码
        mapping = sxdm.get(key, {})
        if mapping and value in mapping:
            code = mapping[value]
        parts.append(f"{key}:{code}")
    content = ",".join(parts) + ","
    if search_name:
        content = content + search_name
    return content


def query_courses(session, config):
    """
    查询课程

    Args:
        session: 已认证的 requests.Session
        config: 查询配置字典，包含以下字段:
            - electiveBatchCode: 选课批次码
            - isMajor: 是否专业课 ("1" / "0")
            - campus: 校区 ("1" 珠海, 空字符串为不限)
            - teachingClassType: 教学班类型 (通常 "QXKC")
            - filters: 筛选条件字典，如 {"KCXF": "0.5", "SKXQ": "1", ...}
            - searchName: 搜索关键词，追加在筛选条件末尾
            - pageSize: 每页条数
            - pageNumber: 页码（从0开始）

    Returns:
        dict: API 返回的 JSON 数据，失败返回 None
    """
    student_code = load_student_code()
    if not student_code:
        print("错误: 无法获取学号")
        return None

    # 从 filters 字典拼装 queryContent 字符串（自动通过 SXDM 转换名称→代码）
    filters = config.get("filters", {})
    search_name = config.get("searchName", "")
    sxdm = load_sxdm()
    query_content = build_query_content(filters, sxdm, search_name)

    # 构建请求体
    payload = {
        "data": {
            "studentCode": student_code,
            "campus": config.get("campus", ""),
            "electiveBatchCode": config.get("electiveBatchCode", ""),
            "isMajor": config.get("isMajor", "1"),
            "teachingClassType": config.get("teachingClassType", "QXKC"),
            "queryContent": query_content,
        },
        "pageSize": str(config.get("pageSize", "10")),
        "pageNumber": str(config.get("pageNumber", "0")),
        "order": config.get("order", ""),
    }

    # 序列化为 querySetting 参数（表单格式）
    query_setting = json.dumps(payload, ensure_ascii=False)
    request_data = {"querySetting": query_setting}

    url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/publicCourse.do"

    print("\n" + "=" * 60)
    print("发送课程查询请求...")
    print(f"请求 URL: {url}")
    print(f"搜索关键词: {search_name or '(无)'}")
    print(f"原始筛选: {filters}")
    print(f"转换后 queryContent: {query_content}")
    print(f"批次码: {config.get('electiveBatchCode')}")
    print(f"专业课: {'是' if config.get('isMajor') == '1' else '否'}")
    print(f"每页条数: {config.get('pageSize', '10')}")
    print(f"页码: {config.get('pageNumber', '0')}")
    print("=" * 60)

    try:
        resp = session.post(url, data=request_data, timeout=15)
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
    """将课程列表格式化为可读文本，返回字符串"""
    if not data_list:
        return "未查询到任何课程。\n"

    lines = []
    lines.append(f"共查询到 {len(data_list)} 门课程:\n")
    lines.append("-" * 80)

    for i, course in enumerate(data_list):
        cid = course.get("teachingClassID", "")
        name = course.get("courseName", "")
        teacher = course.get("teacherName", "")
        credit = course.get("credit", "")
        capacity = course.get("classCapacity", "")
        selected = course.get("numberOfSelected", "")
        nature = course.get("courseNatureName", "")
        campus = course.get("campusName", "")
        place = course.get("teachingPlace", "")
        is_full = "已满" if course.get("isFull") == "1" else "可选"
        conflict = "冲突" if course.get("isConflict") == "1" else ""

        # 上课时间
        time_list = course.get("teachingTimeList", [])
        if time_list:
            t = time_list[0]
            schedule = f"周{t.get('dayOfWeek', '?')} 第{t.get('beginSection', '?')}-{t.get('endSection', '?')}节 {t.get('weekName', '')}"
        else:
            schedule = ""

        lines.append(f"[{i + 1}] {name} ({course.get('courseNumber', '')}-{course.get('courseIndex', '')})")
        lines.append(f"    教学班ID: {cid}")
        lines.append(f"    教师: {teacher}")
        lines.append(f"    学分: {credit}  |  课程性质: {nature}  |  校区: {campus}")
        lines.append(f"    容量: {selected}/{capacity}  |  {is_full}  {conflict}")
        lines.append(f"    时间: {schedule}")
        lines.append(f"    地点: {place}")
        if course.get("extInfo"):
            lines.append(f"    备注: {course.get('extInfo')}")
        lines.append("-" * 80)

    return "\n".join(lines)


QUERY_RESULTS_DIR = os.path.join(BASE_DIR, "query_results")


def save_result(result, config):
    """保存查询结果到 query_results/ 文件夹（完整 JSON + 可读文本日志）"""
    os.makedirs(QUERY_RESULTS_DIR, exist_ok=True)

    search_name = config.get("searchName", "query")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in search_name) if search_name else "query"
    base = f"course_query_{safe_name}_{timestamp}"

    # 完整 JSON
    json_path = os.path.join(QUERY_RESULTS_DIR, f"{base}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # 可读文本日志（课程列表）
    data_list = result.get("dataList", [])
    total_count = int(result.get("totalCount", 0))
    page_size = int(config.get("pageSize", 10))
    total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0
    text = format_course_list(data_list)
    text += f"\n总记录数: {total_count}  |  总页数: {total_pages}\n"

    log_path = os.path.join(QUERY_RESULTS_DIR, f"{base}.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"查询结果已保存: query_results/{base}.json")
    print(f"课程列表已保存: query_results/{base}.log")
    print(f"共 {len(data_list)} 门课程  |  总记录: {total_count}  |  总页数: {total_pages}")


if __name__ == "__main__":
    print("=" * 50)
    print("暨南大学教务系统 - 课程查询工具")
    print("=" * 50)

    # 加载认证信息
    token = load_token()
    if not token:
        print("错误: 无法加载 token，请先运行 get_cookies.py 登录")
        sys.exit(1)

    cookies = load_cookies()

    # 加载查询配置
    config = load_query_config()
    if not config:
        sys.exit(1)

    # 检查登录态
    session = build_session(token, cookies)
    check_url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteered.do?timestamp=1"
    check_resp = session.get(check_url, allow_redirects=False, timeout=10)
    if check_resp.status_code == 200:
        try:
            check_json = check_resp.json()
            if check_json.get("msg") == "未查询到登录信息":
                print("登录态无效: 后端返回未查询到登录信息。")
                print("请重新运行 get_cookies.py 登录后，再执行本脚本。")
                sys.exit(1)
        except ValueError:
            pass
    print("登录态验证通过")

    # 解析命令行参数
    # 用法: python query_course.py [搜索关键词] [--page N]
    args = sys.argv[1:]
    search_name = None
    page_number = None

    i = 0
    while i < len(args):
        if args[i] == "--page" and i + 1 < len(args):
            page_number = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            search_name = args[i]
            i += 1
        else:
            i += 1

    # 命令行参数覆盖配置文件
    if search_name is not None:
        config["searchName"] = search_name
        print(f"命令行指定搜索关键词: {search_name}")
    if page_number is not None:
        config["pageNumber"] = page_number
        print(f"命令行指定页码: {page_number}")

    # 执行查询
    result = query_courses(session, config)

    if result is None:
        print("\n查询失败，请检查配置和登录状态。")
        sys.exit(1)

    # 检查 API 返回
    code = result.get("code")
    msg = result.get("msg", "")
    if code != "1":
        print(f"\nAPI 返回错误: code={code}, msg={msg}")
        if "未登录" in msg or "身份不一致" in msg:
            print("请重新运行 get_cookies.py 登录后重试。")
        sys.exit(1)

    # 保存结果
    save_result(result, config)

    print("\n完成。")

"""
暨南大学教务系统选课脚本
功能：发送志愿选课请求并输出结果
"""

import requests
import json
import os
import time

print("jwxk.py")

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


def load_course_batch_mapping():
    """从 course_batch.json 加载 教学班ID → 批次码 的映射"""
    filepath = _path("course_batch.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        print(f"已从 course_batch.json 加载 {len(mapping)} 个课程批次映射:")
        for cid, batch in mapping.items():
            print(f"  {cid} → {batch}")
        return mapping
    print("警告: 未找到 course_batch.json")
    return {}

def post_volunteer(payload: dict, token: str = None) -> requests.Response:
    """
    提交志愿选课请求
    
    Args:
        payload: 请求参数，包含 data 字段
        token: 选课系统的token参数，如果为None则使用从文件加载的token
    
    Returns:
        requests.Response: 响应对象
    """
    # 加载token
    if token is None:
        token_file = os.path.join(os.path.dirname(__file__), "token.json")
        if os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("token")
            print(f"已从 token.json 加载token: {token}")
            print(f"token类型: {type(token)}")
            print(f"token长度: {len(token) if token else 0}")
        else:
            print("警告: 未找到 token.json 文件，请先运行 get_cookies.py 获取token")
            return None

    if not token:
        print("错误: token为空，请确保token.json文件中有有效的token")
        return None
    
    # 创建会话
    session = requests.Session()
    
    # 构建Referer URL
    referer_url = f"https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/*default/grablessons.do?token={token}"
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
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
        "sec-ch-ua": "\"Not:A-Brand\";v=\"99\", \"Microsoft Edge\";v=\"145\", \"Chromium\";v=\"145\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "priority": "u=1, i"
    })

    # 加载cookies
    cookies_file = os.path.join(os.path.dirname(__file__), "cookies.json")
    if os.path.exists(cookies_file):
        with open(cookies_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        # 清理异常cookie键，避免拼出非法Cookie头
        cookies = {k: v for k, v in cookies.items() if k}
        print(f"已从 cookies.json 加载 {len(cookies)} 个cookie")
        # 将token加入到cookies中
        cookies["token"] = token
        print(f"已将token添加到cookies: {token}")
        session.cookies.update(cookies)
    else:
        print("警告: 未找到 cookies.json 文件，请先运行 get_cookies.py 获取cookies")

    url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteer.do"

    # 先检查会话是否有效，避免把未登录误判成身份不一致
    check_url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteered.do?timestamp=1"
    check_resp = session.get(check_url, allow_redirects=False)
    if check_resp.status_code == 200:
        try:
            check_json = check_resp.json()
            if check_json.get("msg") == "未查询到登录信息":
                print("登录态无效: 后端返回未查询到登录信息。")
                print("请重新运行 get_cookies.py 完整登录后，再执行 jwxk.py。")
                return None
        except ValueError:
            pass
    
    # 构建请求数据 - 与用户提供的负载格式完全一致
    # 确保addParam的值是正确的JSON字符串
    add_param_value = json.dumps(payload)
    request_data = {
        "addParam": add_param_value
    }
    
    print("发送志愿选课请求...")
    print(f"请求数据: {request_data}")
    print(f"token值: '{token}'")
    print(f"addParam值: {add_param_value}")
    
    # 发送表单格式的请求
    resp = session.post(url, data=request_data, headers={
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    })
    print(f"志愿选课状态码: {resp.status_code}")
    print(f"返回值: {resp.text}")

    try:
        result = resp.json()
        if result.get("code") == "302" and "身份不一致" in (result.get("msg") or ""):
            print("提示: 该提示也可能由登录态异常触发，请优先确认是否已成功登录选课系统。")
    except ValueError:
        pass
    
    # 保存返回结果（JSONL 格式：每行一条完整的 JSON 记录）
    try:
        record = resp.json()
    except ValueError:
        record = {"_raw": resp.text, "_status": resp.status_code}
    record["_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("volunteer_response.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("返回结果已保存到 volunteer_response.jsonl")
    
    return resp

if __name__ == "__main__":
    # 从 student_info.json 加载学号（不再硬编码）
    student_code = load_student_code()
    if not student_code:
        print("错误: 无法加载学号，请先运行 get_cookies.py 获取 student_info.json")
        exit(1)

    # 从 course_batch.json 加载 教学班ID → 批次码 映射
    course_batch = load_course_batch_mapping()
    if not course_batch:
        print("错误: course_batch.json 为空或不存在")
        print("请创建 course_batch.json，格式: {\"教学班ID\": \"批次码\", ...}")
        print("批次码可从 student_info.json 的 electiveBatchList 中查找")
        exit(1)

    teaching_class_ids = list(course_batch.keys())
    print(f"\n将轮询以下 {len(teaching_class_ids)} 个课程:")

    index = 0
    while True:
        cid = teaching_class_ids[index % len(teaching_class_ids)]
        batch_code = course_batch[cid]

        volunteer_payload = {
            "data": {
                "operationType": "1",
                "studentCode": student_code,
                "electiveBatchCode": batch_code,
                "teachingClassId": cid,
                "isMajor": "1",
                "campus": "1",
                "teachingClassType": "QXKC"
            }
        }

        volunteer_resp = post_volunteer(volunteer_payload)
        index += 1
        time.sleep(1)  # 每秒发送一次请求，避免过快导致被封禁
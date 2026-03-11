import json
import time
import re
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


BASE_DIR = os.path.dirname(__file__)


def _path_in_script_dir(filename):
    return os.path.join(BASE_DIR, filename)


def validate_login_state(cookie_dict, token):
    """使用 requests 复核当前 cookies/token 是否被后端识别为已登录。"""
    if not token:
        return False, "token为空"

    session = requests.Session()
    cleaned = {k: v for k, v in (cookie_dict or {}).items() if k}
    cleaned["token"] = token
    session.cookies.update(cleaned)

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "token": token,
        "language": "zh_cn",
        "Origin": "https://jwxk.jnu.edu.cn",
        "Referer": f"https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/*default/grablessons.do?token={token}",
    }

    try:
        # 预检接口可能随学期版本变化，采用多接口兜底，避免单接口404误判。
        checks = [
            (
                "volunteered",
                "GET",
                "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/volunteered.do?timestamp=1",
                None,
            ),
            (
                "publicCourse",
                "POST",
                "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/publicCourse.do",
                {
                    "querySetting": json.dumps(
                        {
                            "data": {
                                "studentCode": "",
                                "campus": "1",
                                "electiveBatchCode": "",
                                "isMajor": "1",
                                "teachingClassType": "QXKC",
                                "queryContent": "",
                            },
                            "pageSize": "1",
                            "pageNumber": "0",
                            "order": "",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            (
                "studentstatus",
                "POST",
                "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/elective/studentstatus.do",
                {"studentCode": ""},
            ),
        ]

        traces = []
        for name, method, url, data in checks:
            resp = session.request(method, url, headers=headers, data=data, allow_redirects=False, timeout=15)
            traces.append(f"{name}:{resp.status_code}")

            if resp.status_code == 404:
                continue
            if resp.status_code in (301, 302, 303, 307, 308):
                return False, f"预检被重定向到登录页 ({name}:{resp.status_code})"
            if resp.status_code != 200:
                continue

            try:
                payload = resp.json()
            except ValueError:
                continue

            msg = payload.get("msg")
            code = str(payload.get("code")) if payload.get("code") is not None else ""

            if msg == "未查询到登录信息":
                continue

            # 只要任一接口返回非“未登录”语义，就认为登录态可用。
            if code in {"0", "1", "200", "500"} or msg is None or msg == "":
                return True, f"预检通过({name}): code={code}, msg={msg}"

        return False, f"后端未识别登录信息，探测轨迹: {' | '.join(traces)}"
    except Exception as e:
        return False, f"预检异常: {e}"


def extract_token_from_url(url):
    """从URL中提取token参数"""
    match = re.search(r'token=([a-f0-9\-]+)', url)
    if match:
        return match.group(1)
    return None


def extract_token_from_page(driver):
    """从页面中提取token（尝试多种方式）"""
    candidates = collect_token_candidates(driver)
    if candidates:
        source, token = candidates[0]
        print(f"从{source}提取到token: {token}")
        return token

    print("未能自动提取token，请手动输入或检查页面")
    return None


def collect_token_candidates(driver):
    """收集多个token候选，按可靠性排序。"""
    result = []
    seen = set()

    def add_candidate(source, value):
        if not value:
            return
        value = str(value).strip()
        if not re.fullmatch(r"[a-f0-9\-]{36}", value):
            return
        if value in seen:
            return
        seen.add(value)
        result.append((source, value))

    try:
        storage_token = driver.execute_script(
            "return sessionStorage.getItem('token') || sessionStorage.token || localStorage.getItem('token') || localStorage.token"
        )
        add_candidate("sessionStorage/localStorage", storage_token)
    except Exception:
        pass

    try:
        current_url = driver.current_url
        add_candidate("URL", extract_token_from_url(current_url))
    except Exception:
        pass

    try:
        page_source = driver.page_source
        for m in re.findall(r"[a-f0-9\-]{36}", page_source):
            add_candidate("页面内容", m)
            if len(result) >= 5:
                break
    except Exception:
        pass

    return result


def save_token(token):
    """保存token到文件"""
    if token:
        with open(_path_in_script_dir("token.json"), "w", encoding="utf-8") as f:
            json.dump({"token": token}, f, indent=2, ensure_ascii=False)
        print(f"token已保存到 token.json 文件")
        return True
    return False


def load_token_from_file():
    """从文件加载token"""
    try:
        with open(_path_in_script_dir("token.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"已从 token.json 加载token: {data.get('token')}")
        return data.get('token')
    except FileNotFoundError:
        print("未找到 token.json 文件")
        return None


def get_cookies_manual():
    """手动获取cookies：打开浏览器，用户登录后获取cookies和token"""
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/*default/index.do"
        print(f"正在打开浏览器: {url}")
        driver.get(url)
        
        print("\n请在浏览器中完成登录...")
        print("登录完成后，请在此终端按回车键继续...")
        input()
        
        cookies = driver.get_cookies()

        cookie_dict = {}
        for cookie in cookies:
            cookie_dict[cookie['name']] = cookie['value']
        
        print("\n正在尝试自动提取token...")
        candidates = collect_token_candidates(driver)
        token = candidates[0][1] if candidates else None
        if token:
            print(f"候选token数量: {len(candidates)}")
            for source, t in candidates:
                print(f"- {source}: {t}")
        
        if not token:
            print("\n未自动提取到token，请手动输入token（可选，按回车跳过）:")
            manual_token = input().strip()
            if manual_token:
                token = manual_token
                candidates = [("手动输入", token)]

        if token and not candidates:
            candidates = [("默认候选", token)]

        valid_token = None
        for source, candidate in candidates:
            ok, message = validate_login_state(cookie_dict, candidate)
            print(f"\n校验token[{source}]={candidate} -> {message}")
            if ok:
                valid_token = candidate
                break

        token = valid_token
        
        if not token:
            print("提示: 当前登录态无效，未保存 cookies/token。请确认进入选课系统后重试。")
            return cookie_dict, None

        print("\n获取到的cookies:")
        print(json.dumps(cookie_dict, indent=2, ensure_ascii=False))

        with open(_path_in_script_dir("cookies.json"), "w", encoding="utf-8") as f:
            json.dump(cookie_dict, f, indent=2, ensure_ascii=False)

        print("\ncookies已保存到 cookies.json 文件")

        save_token(token)
        
        return cookie_dict, token
        
    finally:
        print("\n按回车键关闭浏览器...")
        input()
        driver.quit()


def get_cookies_with_login(username, password):
    """自动登录获取cookies和token（需要根据实际登录页面调整）"""
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        url = "https://jwxk.jnu.edu.cn/xsxkapp/sys/xsxkapp/*default/index.do"
        print(f"正在打开浏览器: {url}")
        driver.get(url)
        
        wait = WebDriverWait(driver, 10)
        
        print("\n尝试自动登录...")
        print("注意：如果登录页面结构变化，需要调整选择器")
        
        try:
            username_input = wait.until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            password_input = driver.find_element(By.NAME, "password")
            login_button = driver.find_element(By.XPATH, "//button[contains(text(), '登录') or @type='submit']")
            
            username_input.send_keys(username)
            password_input.send_keys(password)
            login_button.click()
            
            print("等待登录完成...")
            time.sleep(3)
            
        except Exception as e:
            print(f"自动登录失败: {e}")
            print("请手动完成登录后按回车键继续...")
            input()
        
        cookies = driver.get_cookies()

        cookie_dict = {}
        for cookie in cookies:
            cookie_dict[cookie['name']] = cookie['value']
        
        print("\n正在尝试自动提取token...")
        candidates = collect_token_candidates(driver)
        token = candidates[0][1] if candidates else None
        if token:
            print(f"候选token数量: {len(candidates)}")
            for source, t in candidates:
                print(f"- {source}: {t}")
        
        if not token:
            print("\n未自动提取到token，请手动输入token（可选，按回车跳过）:")
            manual_token = input().strip()
            if manual_token:
                token = manual_token
                candidates = [("手动输入", token)]

        if token and not candidates:
            candidates = [("默认候选", token)]

        valid_token = None
        for source, candidate in candidates:
            ok, message = validate_login_state(cookie_dict, candidate)
            print(f"\n校验token[{source}]={candidate} -> {message}")
            if ok:
                valid_token = candidate
                break

        token = valid_token
        
        if not token:
            print("提示: 当前登录态无效，未保存 cookies/token。请确认进入选课系统后重试。")
            return cookie_dict, None

        print("\n获取到的cookies:")
        print(json.dumps(cookie_dict, indent=2, ensure_ascii=False))

        with open(_path_in_script_dir("cookies.json"), "w", encoding="utf-8") as f:
            json.dump(cookie_dict, f, indent=2, ensure_ascii=False)

        print("\ncookies已保存到 cookies.json 文件")

        save_token(token)
        
        return cookie_dict, token
        
    finally:
        time.sleep(2)
        driver.quit()


def load_cookies_from_file():
    """从文件加载cookies"""
    try:
        with open(_path_in_script_dir("cookies.json"), "r", encoding="utf-8") as f:
            cookies = json.load(f)
        print("已从 cookies.json 加载cookies:")
        print(json.dumps(cookies, indent=2, ensure_ascii=False))
        return cookies
    except FileNotFoundError:
        print("未找到 cookies.json 文件")
        return None


if __name__ == "__main__":
    print("=" * 50)
    print("Cookies和Token获取工具")
    print("=" * 50)
    
    print("手动获取（打开浏览器，手动登录）")
    cookies, token = get_cookies_manual()
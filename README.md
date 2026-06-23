# 暨南大学教务系统（jwxk）选课脚本。

项目包含两个核心脚本：

- `get_cookies.py`：打开浏览器登录，提取并校验 `cookies` 与 `token`，保存到本地文件。
- `jwxk.py`：读取本地 `cookies/token`，模拟浏览器行为向服务器按设定课程 ID 提交志愿选课请求。

## 目录说明

- `get_cookies.py`：获取并校验登录态。
- `jwxk.py`：发送志愿选课请求。

（脚本生成的文件）
- `cookies.json`：登录后保存的 cookies。
- `token.json`：登录后保存的 token。
- `volunteer_response.json`：选课接口响应。

## 运行环境

- Windows（当前项目在 Windows 下开发）
- Python 3.9+
- 已安装 Chrome 浏览器

Python 依赖：

```bash
pip install requests selenium
```

说明：

- `selenium` 启动 Chrome 时需要可用的驱动环境。新版 Selenium 通常可自动处理驱动；若失败，请检查本机 Chrome 与驱动兼容性。

## 快速开始

### 1. 获取登录态（cookies + token）

```bash
python get_cookies.py
```

执行后会：

1. 打开选课系统登录页。
2. 你手动完成登录。
3. 终端回车后脚本自动提取并校验 token。
4. 生成/更新 `cookies.json` 和 `token.json`。

如果校验失败，脚本会提示“未识别登录信息”，此时需要重新登录后再执行一次。

### 2. 配置你的学号和课程 ID

编辑 `jwxk.py`：

- 修改 `STUDENT_CODE` 为你的学号。
- 修改 `teaching_class_id` 为你的目标教学班 ID。
- 如需切换选课批次，修改 `electiveBatchCode`。

示例（来自当前脚本）：

```python
STUDENT_CODE = "你的学号"
teaching_class_id = ["2526207937", "2526207346"]
```

**注意**
新发现到选课批次的code每学期会变化，目前临时的解决方法是在选课时间前按F12到网络选项卡然后在浏览器页面按下选课按钮观察发出的包与jwxk.py中的以下代码段有何异同：
```python
        volunteer_payload = {
            "data": {
                "operationType": "1",
                "studentCode": STUDENT_CODE,
                "electiveBatchCode": ELECTIVE_BATCH_CODE,   # 此处改成了一个全局变量，以便修改
                "teachingClassId": teaching_class_id[index % len(teaching_class_id)],
                "isMajor": "1",
                "campus": "1",
                "teachingClassType": "QXKC"
            }
        }
```
如有不同，请自行修改。

### 3. 启动选课循环

```bash
python jwxk.py
```

默认行为：

- 按课程 ID 列表轮询提交（每秒一次）。
- 输出状态码和接口返回。
- 将最新返回覆盖写入 `volunteer_response.json`。

**验证**：若在选课时间前运行，发现返回的信息是“当前时间不在选课开放时间范围内”，则证明你的脚本已经准备好了。如果返回了其他值，请检查设置是否正确。

## 返回码与常见提示

- `code = "2"` 且 `msg` 类似“该课程已经存在选课结果中”：表示该课已在你的结果里。
- `msg = "未查询到登录信息"`：登录态失效，先重新运行 `get_cookies.py`。
- `code = "302"` 且提示“身份不一致”：通常与登录态异常有关，优先重新获取 cookies/token, 并且检查是否已经替换STUDENT_CODE为自己的学号。

## 常见问题

### 1) 浏览器打开了但提取不到 token

- 确认已进入选课系统页面（不是统一认证中间页）。
- 按脚本提示可手动输入 token。
- 若仍失败，重新登录后再试。

### 2) 一直提示未登录

- 先删除旧的 `cookies.json`、`token.json`。
- 重新运行 `python get_cookies.py` 完整登录。
- 再运行 `python jwxk.py`。

## 注意事项

- 获取cookies和token完成后不要在其他地方尝试登录教务系统，cookies会失效
- `cookies.json` 和 `token.json` 属于敏感登录凭据，不要外传。
- 目前尚不清楚请求间隔过短会不会被限制，调节间隔需谨慎
- 本脚本仅供学习与个人使用，请遵守学校选课系统相关规定，严禁用于任何形式的商业用途。

# 暨南大学教务系统（jwxk）选课脚本。

项目包含两个核心脚本：

- `get_cookies.py`：打开浏览器登录，提取并校验 `cookies` 与 `token`，同时获取学生信息和选课轮次列表，保存到本地文件。
- `jwxk.py`：读取本地凭据和课程配置，按每个课程匹配的批次码轮询提交志愿选课请求。

## 目录说明

- `get_cookies.py`：获取并校验登录态 + 学生信息。
- `jwxk.py`：发送志愿选课请求。
- `query_course.py`：查询可选课程（按筛选条件搜索）。
- `query_selected.py`：查询已选课程（当前学期所有已中选的课）。

（脚本生成的文件）
- `cookies.json`：登录后保存的 cookies。
- `token.json`：登录后保存的 token。
- `student_info.json`：学生基本信息 + 所有选课轮次（含批次码、名称、时间窗口）。
- `volunteer_response.jsonl`：选课接口响应日志（JSONL 格式，每行一条记录）。

（用户编辑的配置文件）
- `course_batch.json`：教学班ID → 批次码 的映射，需用户自行填写。

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

### 1. 获取登录态和学生信息

```bash
python get_cookies.py
```

执行后会：

1. 打开选课系统登录页。
2. 你手动完成登录。
3. 终端回车后脚本自动提取并校验 token。
4. 尝试从页面自动提取学号（失败则手动输入）。
5. 请求学生信息接口，获取选课轮次列表。
6. 生成/更新 `cookies.json`、`token.json`、`student_info.json`。

终端会打印所有可用选课轮次的摘要，含批次码和时间窗口。

### 2. 配置课程批次映射

编辑 `course_batch.json`，**初次使用需要新建此文件**。为每个目标课程填写对应的批次码：

```json
{
  "1234567890": "io93nnd8amnmn34ofysagvcbje4effax",
  "1234567890": "io93nnd8amnmn34ofysagvcbje4effax"
}
```

批次码来源：`student_info.json` → `electiveBatchList` 中对应轮次的 `code` 字段。不同课程可能属于不同选课轮次（专业课 / 通选课），需要分别匹配。

### 3. 启动选课循环

```bash
python jwxk.py
```

脚本会：

- 从 `student_info.json` 加载学号。
- 从 `course_batch.json` 加载课程→批次映射。
- 按课程列表轮询提交（每秒一次），每个课程使用各自匹配的批次码。
- 将每次请求的响应以 JSONL 格式追加写入 `volunteer_response.jsonl`。

### 4.提前验证脚本是否生效
在选课时间前按照步骤开始选课后，如果`msg`显示"当前时间不在选课开放时间范围内"，则表示脚本已正常运作。如果显示其他，请检查你的设置。


## 其他脚本说明

### 查询可选课程（`query_course.py`）

按筛选条件搜索当前可选课程，用于选课前浏览课程信息、查看容量和冲突情况。

```bash
python query_course.py                     # 使用 query_config.json 中的配置
python query_course.py "大学生职业生涯规划"   # 命令行指定搜索关键词
python query_course.py --page 1            # 查询第 2 页（页码从 0 开始）
```

**前置条件**：先运行 `get_cookies.py` 登录，确保 `cookies.json`、`token.json`、`student_info.json` 存在。

**配置文件 `query_config.json`**（仓库中已有示例）：

```json
{
  "electiveBatchCode": "d7d8c03b35884aa88ae2b9887f4f8a51",
  "isMajor": "1",
  "campus": "",
  "teachingClassType": "QXKC",
  "filters": {
    "KCXF": "0.5",
    "SKXQ": "1"
  },
  "pageSize": "10",
  "pageNumber": "0"
}
```

- `electiveBatchCode`：选课批次码，来自 `student_info.json` → `electiveBatchList`。
- `isMajor`：`"1"` 为专业课，`"0"` 为通选课。
- `filters`：筛选条件，如 `KCXF`（课程学分）、`SKXQ`（上课校区）、`KKDWDM`（开课单位）等，值为中文名时会自动通过 `SXDM.json` 转码（这个转码字典映射还没有完善，慎用）。
- `searchName`：搜索关键词（命令行为准，配置文件中的会被覆盖）。

**建议优先使用配置文件查询**
结果保存到 `query_results/` 文件夹，包含完整 JSON 和可读文本日志。

### 查询已选课程（`query_selected.py`）

查询当前学期所有已中选的课程（按选课批次分别查询），用于确认选课结果。

```bash
python query_selected.py
```

**前置条件**：先运行 `get_cookies.py` 登录，确保 `cookies.json`、`token.json`、`student_info.json` 存在。

脚本会自动遍历 `student_info.json` 中的所有选课批次，对每个批次查询已中选课程并汇总。结果保存到 `selected_results/` 文件夹，包含完整 JSON 和按批次汇总的可读文本日志。


## 返回码与常见提示

- `code = "2"` 且 `msg` 类似"该课程已经存在选课结果中"：表示该课已在你的结果里。
- `msg = "未查询到登录信息"`：登录态失效，先重新运行 `get_cookies.py`。
- `code = "302"` 且提示"身份不一致"：通常与登录态异常有关，优先重新获取 cookies/token。

## 常见问题

### 1) 浏览器打开了但提取不到 token

- 确认已进入选课系统页面（不是统一认证中间页）。

### 2) 一直提示未登录

- 先删除旧的 `cookies.json`、`token.json`、`student_info.json`。
- 重新运行 `python get_cookies.py` 完整登录。
- 再运行 `python jwxk.py`。

## 注意事项

- 获取 cookies 和 token 完成后不要在其他地方尝试登录教务系统，cookies 会失效。
- `cookies.json`、`token.json`、`student_info.json` 属于敏感凭据和个人信息，不要外传。
- 目前尚不清楚请求间隔过短会不会被限制，调节间隔需谨慎，后果自付。
- 本脚本仅供学习与个人使用，请遵守学校选课系统相关规定，严禁用于任何形式的商业用途。
- 脚本有随时过期无法使用的风险，不一定保证可以使用。每次使用前请自行检查脚本是否正常运作。
- **如果你发现了bug**，你可以提issue告诉作者，作者可能会不定期查看（即使作者可能不会怎么修）。


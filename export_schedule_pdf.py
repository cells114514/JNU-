"""
将已导出的课表 JSON 生成为单页周课表 PDF。

用法：
    python export_schedule_pdf.py
    python export_schedule_pdf.py selected_results/selected_courses_20260702_105748.json
    python export_schedule_pdf.py input.json -o output.pdf --page-size a3

默认行为：
    - 自动读取 selected_results/ 下最新的 selected_courses_*.json；
    - 输出到 selected_results/course_schedule.pdf；
    - 使用横向 A4，整个课表只占一页。

脚本只依赖 reportlab，不会修改原始 JSON。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = BASE_DIR / "selected_results"
DEFAULT_OUTPUT = DEFAULT_RESULTS_DIR / "course_schedule.pdf"

DAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
SECTION_GROUPS = (("上午", 1, 4), ("下午", 5, 8), ("晚上", 9, 13))
DAY_NAME_TO_NUMBER = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 7,
    "天": 7,
}


@dataclass(frozen=True)
class CourseSlot:
    """课表中一个占用连续节次的课程块。"""

    name: str
    course_index: str
    week_name: str
    begin_section: int
    end_section: int
    day: int
    place: str
    teacher: str
    sport_name: str = ""

    @property
    def title(self) -> str:
        title = self.name.strip() or "未命名课程"
        if self.course_index.strip():
            title += f"-{self.course_index.strip()}"
        if self.sport_name.strip():
            title += f"({self.sport_name.strip()})"
        return title

    @property
    def section_text(self) -> str:
        return f"{self.week_name} {self.begin_section}-{self.end_section}节".strip()


def find_font() -> tuple[str, Path]:
    """寻找 Windows 常见中文字体，避免 PDF 中的中文变成方框。"""

    candidates = [
        ("SimHei", Path(r"C:\Windows\Fonts\simhei.ttf")),
        ("Deng", Path(r"C:\Windows\Fonts\Deng.ttf")),
        ("MicrosoftYaHei", Path(r"C:\Windows\Fonts\msyh.ttf")),
        ("Simsun", Path(r"C:\Windows\Fonts\simsun.ttf")),
    ]
    for font_name, font_path in candidates:
        if font_path.exists():
            return font_name, font_path

    raise RuntimeError(
        "未找到可用的中文字体。请确认 C:\\Windows\\Fonts 中存在 simhei.ttf、"
        "Deng.ttf、msyh.ttf 或 simsun.ttf。"
    )


def register_chinese_font() -> str:
    font_name, font_path = find_font()
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    return font_name


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_day(value: Any) -> int | None:
    """将 1-7、周一、星期一等格式统一成 1-7。"""

    if value is None:
        return None
    text = as_text(value)
    number = parse_int(text)
    if number is not None and 1 <= number <= 7:
        return number

    for char, day in DAY_NAME_TO_NUMBER.items():
        if char in text:
            return day
    return None


def compact_week_ranges(mask: str) -> str:
    """从周次位串推导显示文本，例如 111100011 -> 1-4,8-9周。"""

    positions = [i + 1 for i, flag in enumerate(mask) if flag == "1"]
    if not positions:
        return ""

    ranges: list[str] = []
    start = previous = positions[0]
    for current in positions[1:]:
        if current == previous + 1:
            previous = current
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = current
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges) + "周"


def get_week_name(course: dict[str, Any], time_info: dict[str, Any]) -> str:
    week_name = as_text(time_info.get("weekName")) or as_text(course.get("weekName"))
    if week_name:
        return week_name

    week_mask = as_text(time_info.get("week")) or as_text(course.get("week"))
    return compact_week_ranges(week_mask)


def is_course_record(value: Any) -> bool:
    return isinstance(value, dict) and any(
        key in value for key in ("courseName", "teachingClassID", "beginSection")
    )


def iter_course_records(payload: Any) -> Iterable[dict[str, Any]]:
    """兼容 selected_courses JSON 和带 teachingTimeList 的课程查询 JSON。"""

    if isinstance(payload, list):
        for item in payload:
            yield from iter_course_records(item)
        return

    if not isinstance(payload, dict):
        return

    data_list = payload.get("dataList")
    if isinstance(data_list, list):
        for item in data_list:
            yield from iter_course_records(item)
        return

    if is_course_record(payload):
        time_list = payload.get("teachingTimeList")
        if isinstance(time_list, list) and time_list:
            for time_info in time_list:
                if isinstance(time_info, dict):
                    merged = dict(payload)
                    merged.update(time_info)
                    yield merged
            return
        yield payload
        return

    for value in payload.values():
        yield from iter_course_records(value)


def make_course_slot(record: dict[str, Any]) -> CourseSlot | None:
    day = parse_day(record.get("dayOfWeek"))
    begin = parse_int(record.get("beginSection"))
    end = parse_int(record.get("endSection"))
    if day is None or begin is None or end is None:
        return None
    if not 1 <= begin <= 13 or not 1 <= end <= 13:
        return None
    if end < begin:
        begin, end = end, begin

    return CourseSlot(
        name=as_text(record.get("courseName")) or "未命名课程",
        course_index=as_text(record.get("courseIndex")),
        week_name=get_week_name(record, record),
        begin_section=begin,
        end_section=end,
        day=day,
        place=as_text(record.get("teachingPlace")) or "时间地点未安排",
        teacher=as_text(record.get("teacherName")),
        sport_name=as_text(record.get("sportName")),
    )


def load_courses(input_path: Path) -> list[CourseSlot]:
    with input_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    courses: list[CourseSlot] = []
    seen: set[tuple[Any, ...]] = set()
    for record in iter_course_records(payload):
        slot = make_course_slot(record)
        if slot is None:
            continue

        # 防止某些导出格式同时在外层和 dataList 中出现同一条记录。
        key = (
            slot.name,
            slot.course_index,
            slot.day,
            slot.begin_section,
            slot.end_section,
            slot.week_name,
            slot.place,
            slot.teacher,
        )
        if key not in seen:
            seen.add(key)
            courses.append(slot)

    if not courses:
        raise ValueError(
            f"在 {input_path} 中没有找到可绘制的课程。"
            "请确认 JSON 包含 courseName、dayOfWeek、beginSection、endSection 等字段。"
        )
    return courses


def latest_input_file() -> Path:
    candidates = sorted(DEFAULT_RESULTS_DIR.glob("selected_courses_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "未找到 selected_results/selected_courses_*.json，"
            "请先运行 query_selected.py，或在命令行中显式传入 JSON 路径。"
        )
    return candidates[-1]


def wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    """按实际字体宽度逐字换行，适合中文和中英混排。"""

    if not text:
        return []

    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        current = ""
        for char in raw_line:
            candidate = current + char
            if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines or [""]


def make_text_lines(
    slot: CourseSlot,
    font_name: str,
    font_size: float,
    max_width: float,
) -> list[str]:
    lines: list[str] = []
    for content in (slot.title, slot.section_text, slot.place, slot.teacher):
        lines.extend(wrap_text(content, font_name, font_size, max_width))
    return lines


def draw_course_card(
    pdf: canvas.Canvas,
    slot: CourseSlot,
    x: float,
    y: float,
    width: float,
    height: float,
    font_name: str,
) -> None:
    card_padding = 3.5
    inner_width = max(10.0, width - card_padding * 2)
    available_height = max(8.0, height - card_padding * 2)

    # 课程较多时自动缩小文字，优先保证每个课程块仍留在自己的合并单元格内。
    chosen_size = 7.6
    chosen_lines: list[str] = []
    for font_size in (8.2, 7.8, 7.4, 7.0, 6.6, 6.2):
        line_height = font_size * 1.18
        candidate = make_text_lines(slot, font_name, font_size, inner_width)
        if len(candidate) * line_height <= available_height:
            chosen_size = font_size
            chosen_lines = candidate
            break
        chosen_size = font_size
        chosen_lines = candidate

    line_height = chosen_size * 1.18
    max_lines = max(1, int(available_height // line_height))
    if len(chosen_lines) > max_lines:
        chosen_lines = chosen_lines[:max_lines]
        if chosen_lines:
            last = chosen_lines[-1]
            while last and pdfmetrics.stringWidth(last + "…", font_name, chosen_size) > inner_width:
                last = last[:-1]
            chosen_lines[-1] = (last + "…") if last else "…"

    # 课程块略带白色填充，覆盖中间的节次线，形成参考图中的合并单元格效果。
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#d7e2f2"))
    pdf.setLineWidth(0.45)
    pdf.rect(x + 0.25, y + 0.25, width - 0.5, height - 0.5, fill=1, stroke=1)

    total_text_height = len(chosen_lines) * line_height
    baseline = y + (height + total_text_height) / 2 - chosen_size * 0.86
    pdf.setFillColor(colors.HexColor("#17345c"))
    pdf.setFont(font_name, chosen_size)
    for line in chosen_lines:
        pdf.drawCentredString(x + width / 2, baseline, line)
        baseline -= line_height


def assign_tracks(slots: list[CourseSlot]) -> dict[int, tuple[int, int]]:
    """为同一天有时间重叠的课程分配并列小列，避免文字相互覆盖。"""

    result: dict[int, tuple[int, int]] = {}
    for day in range(1, 8):
        day_slots = sorted(
            ((index, slot) for index, slot in enumerate(slots) if slot.day == day),
            key=lambda item: (item[1].begin_section, item[1].end_section),
        )
        track_ends: list[int] = []
        for index, slot in day_slots:
            track = next(
                (candidate for candidate, end in enumerate(track_ends) if end < slot.begin_section),
                len(track_ends),
            )
            if track == len(track_ends):
                track_ends.append(slot.end_section)
            else:
                track_ends[track] = slot.end_section
            result[index] = (track, len(track_ends))

        # 当前列数是最终列数；前面已分配的课程需要同步到最终宽度。
        final_track_count = len(track_ends)
        for index, slot in day_slots:
            track, _ = result[index]
            result[index] = (track, final_track_count)
    return result


def draw_schedule(
    output_path: Path,
    slots: list[CourseSlot],
    page_size_name: str = "a4",
) -> None:
    font_name = register_chinese_font()
    page_size = landscape(A4 if page_size_name == "a4" else A3)
    page_width, page_height = page_size

    pdf = canvas.Canvas(str(output_path), pagesize=page_size)
    pdf.setTitle("课程表")
    pdf.setAuthor("JNU Course Schedule Exporter")

    margin_x = 10.0
    margin_y = 10.0
    header_height = 30.0
    group_width = 25.0
    section_width = 27.0
    table_width = page_width - margin_x * 2
    table_height = page_height - margin_y * 2
    body_height = table_height - header_height
    row_height = body_height / 13.0
    day_width = (table_width - group_width - section_width) / 7.0
    table_left = margin_x
    body_top = page_height - margin_y - header_height
    table_bottom = margin_y
    days_left = table_left + group_width + section_width

    border = colors.HexColor("#d4e0f1")
    header_fill = colors.HexColor("#eaf2fc")
    group_fill = colors.HexColor("#eef5fd")
    body_fill = colors.HexColor("#fbfdfd")
    text_color = colors.HexColor("#17345c")

    # 表格主体背景。
    pdf.setFillColor(body_fill)
    pdf.rect(table_left, table_bottom, table_width, body_height, fill=1, stroke=0)

    # 周标题栏。
    pdf.setFillColor(header_fill)
    pdf.rect(table_left, body_top, table_width, header_height, fill=1, stroke=0)
    pdf.setStrokeColor(border)
    pdf.setLineWidth(0.55)
    pdf.rect(table_left, body_top, table_width, header_height, fill=0, stroke=1)
    pdf.line(days_left, body_top, days_left, body_top + header_height)
    pdf.line(table_left + group_width, table_bottom, table_left + group_width, body_top + header_height)
    pdf.line(days_left, table_bottom, days_left, body_top)

    pdf.setFillColor(text_color)
    pdf.setFont(font_name, 9.2)
    pdf.drawCentredString(
        table_left + (group_width + section_width) / 2,
        body_top + (header_height - 9.2) / 2 + 2,
        "节次/星期",
    )
    for day_index, day_name in enumerate(DAY_NAMES):
        x = days_left + day_index * day_width
        pdf.line(x, table_bottom, x, body_top + header_height)
        pdf.drawCentredString(x + day_width / 2, body_top + (header_height - 9.2) / 2 + 2, day_name)
    pdf.line(table_left + table_width, table_bottom, table_left + table_width, body_top + header_height)

    # 节次列、分区列和主体横线。
    pdf.setStrokeColor(border)
    pdf.setLineWidth(0.45)
    for row in range(14):
        y = body_top - row * row_height
        pdf.line(table_left + group_width, y, table_left + table_width, y)
    pdf.line(table_left + group_width + section_width, table_bottom, table_left + group_width + section_width, body_top)
    for row in range(1, 14):
        y = body_top - row * row_height
        pdf.drawCentredString(
            table_left + group_width + section_width / 2,
            y + row_height / 2 - 3.2,
            str(row),
        )

    # 上午、下午、晚上分区标签，保持参考图的纵向合并效果。
    for group_name, start, end in SECTION_GROUPS:
        y = body_top - end * row_height
        height = (end - start + 1) * row_height
        pdf.setFillColor(group_fill)
        pdf.rect(table_left, y, group_width, height, fill=1, stroke=0)
        pdf.setStrokeColor(border)
        pdf.rect(table_left, y, group_width, height, fill=0, stroke=1)

        pdf.setFillColor(text_color)
        pdf.setFont(font_name, 8.8)
        chars = list(group_name)
        char_gap = 10.2
        first_baseline = y + height / 2 + (len(chars) - 1) * char_gap / 2 - 3.0
        for offset, char in enumerate(chars):
            pdf.drawCentredString(table_left + group_width / 2, first_baseline - offset * char_gap, char)

    # 课程块。发生同一时间重叠时，在当天列内并排绘制。
    tracks = assign_tracks(slots)
    for index, slot in enumerate(slots):
        track, track_count = tracks[index]
        day_x = days_left + (slot.day - 1) * day_width
        card_width = day_width / track_count
        x = day_x + track * card_width
        y = body_top - slot.end_section * row_height
        height = (slot.end_section - slot.begin_section + 1) * row_height
        draw_course_card(pdf, slot, x, y, card_width, height, font_name)

    # 再描一次外框，让课程块不会覆盖表格边界。
    pdf.setStrokeColor(border)
    pdf.setLineWidth(0.6)
    pdf.rect(table_left, table_bottom, table_width, table_height, fill=0, stroke=1)
    pdf.showPage()
    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将导出的课程 JSON 生成一页周课表 PDF")
    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        help="课表 JSON；省略时读取 selected_results/ 下最新的 selected_courses_*.json",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出 PDF 路径（默认：{DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--page-size",
        choices=("a4", "a3"),
        default="a4",
        help="页面尺寸，默认横向 A4；课程名很长时可选择横向 A3",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_path = (args.input_json or latest_input_file()).resolve()
        output_path = args.output.resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"找不到输入 JSON：{input_path}")

        slots = load_courses(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        draw_schedule(output_path, slots, args.page_size)

        print(f"已导出 {len(slots)} 门课程到：{output_path}")
        print(f"页面：横向 {args.page_size.upper()}，单页课表")
        return 0
    except (FileNotFoundError, json.JSONDecodeError, OSError, RuntimeError, ValueError) as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

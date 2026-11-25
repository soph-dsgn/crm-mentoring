"""Import of personal strategies exported from Notion as PDF.

Parsing is a pure step that only returns a draft. The curator reviews the draft and the
client sends the confirmed draft back to ``apply_strategy_import``, which writes it in the
caller's transaction.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.modules.strategies.models import (
    ReviewStatus,
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.strategies.schemas import (
    ImportedProfile,
    ImportedSection,
    ImportedTask,
    ImportWarning,
    StrategyCreate,
    StrategyImportApply,
    StrategyImportDraft,
)
from app.modules.strategies.service import _lock_strategy_write, create_strategy
from app.modules.students.models import Student
from app.modules.students.schemas import StudentUpdate
from app.modules.students.service import update_student
from app.modules.users.audit import AuditAction
from app.modules.users.models import User
from app.modules.users.service import record_audit

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 80
TITLE_LIMIT = 255
SHORT_LIMIT = 255
LONG_LIMIT = 20_000

STATUS_ALIASES = {
    "done": StudyStatus.DONE,
    "completed": StudyStatus.DONE,
    "выполнено": StudyStatus.DONE,
    "готово": StudyStatus.DONE,
    "in progress": StudyStatus.IN_PROGRESS,
    "в процессе": StudyStatus.IN_PROGRESS,
    "в работе": StudyStatus.IN_PROGRESS,
    "hold": StudyStatus.HOLD,
    "on hold": StudyStatus.HOLD,
    "на паузе": StudyStatus.HOLD,
    "not started": StudyStatus.NOT_STARTED,
    "не начато": StudyStatus.NOT_STARTED,
}
POINT_HEADINGS = {"точка а": "point_a", "точка a": "point_a", "точка б": "point_b"}
LIST_MARKER = re.compile(r"^(\d+[.)]|[-–—•·▪●])\s")
BOLD_FONT = re.compile(r"bold|black|heavy|semibold|[_-](6|7|8|9)00", re.IGNORECASE)
URL = re.compile(r"https?://[^\s<>\"']+")
TELEGRAM_HANDLE = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

logging.getLogger("pdfminer").setLevel(logging.ERROR)


class _Draft:
    def __init__(self) -> None:
        self.source_title = ""
        self.sections: list[dict[str, Any]] = []
        self.points: dict[str, dict[str, list[str]]] = {"point_a": {}, "point_b": {}}
        self.telegram_parts: list[str] = []
        self.strategy_header: list[str] | None = None
        self.strategy_columns: list[tuple[float, float]] = []
        self.warnings: dict[str, ImportWarning] = {}

    def warn(self, code: str, detail: str = "") -> None:
        current = self.warnings.get(code)
        if current is None:
            self.warnings[code] = ImportWarning(
                code=code, count=1, examples=[detail][:1] if detail else []
            )
            return
        current.count += 1
        if detail and len(current.examples) < 3:
            current.examples.append(detail)


def _invalid(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message)


def _clean(value: str) -> str:
    return re.sub(r"[ \t ]+", " ", CONTROL.sub("", value)).strip()


STANDALONE_WORDS = {
    "в", "к", "с", "у", "о", "и", "а", "на", "до", "да", "по", "за", "из", "от", "не",
    "ни", "же", "ли", "бы", "но", "во", "со", "ко", "об", "то", "или", "для", "при", "без",
    "про", "под", "над", "что", "как", "нет", "есть", "если", "хотя", "уже", "еще", "ещё",
}  # fmt: skip
URL_CHARS = re.compile(r"[/.:=&?@_\d%#-]")


def _is_broken_word(head: str, tail_line: str) -> bool:
    """Decide whether ``tail_line`` continues the single token ``head`` without a space.

    Geometry alone cannot tell a broken word from a short word wrapped to the next line, so
    links and handles are always joined, common standalone words never are, and Cyrillic
    words are joined only for short endings of long words.
    """
    tail = tail_line.split(" ", 1)[0]
    if not head or not tail or tail.startswith("http"):
        return False
    if URL_CHARS.search(head) and not re.search(r"[а-яё]", head, re.IGNORECASE):
        return True
    if not (head[-1].isalpha() and tail[0].isalpha() and tail[0].islower()):
        return False
    if tail[0] in "ьъы":
        return True
    bare = tail.strip(".,;:!?»)\"'").lower()
    if bare in STANDALONE_WORDS:
        return False
    if head.isascii() and tail.isascii():
        return len(bare) <= 2
    if len(bare) <= 4:
        return len(head) + len(bare) >= 11
    return len(bare) <= 5 and len(head) >= 12


def join_wrapped_lines(lines: Iterable[tuple[str, float, float]]) -> str:
    """Join visual lines of a narrow table cell back into the original text.

    Each item is ``(text, free_space, first_char_width)``: the unused width at the end of
    the line and the width of its first character. The browser breaks a word only when it
    does not fit on a line by itself, so a broken line holds a single token and has no room
    left even for the first letter of its continuation.
    """
    result = ""
    previous: tuple[str, float] | None = None
    for raw_text, free_space, first_width in lines:
        text = _clean(raw_text)
        if not text:
            continue
        if previous is None:
            result = text
        else:
            prev_text, prev_free = previous
            broken_word = (
                prev_free < first_width * 0.9
                and " " not in prev_text
                and _is_broken_word(prev_text, text)
            )
            if broken_word:
                result += text
            elif LIST_MARKER.match(text):
                result += "\n" + text
            else:
                result += " " + text
        previous = (text, free_space)
    return result


def _cell_text(
    page: Any, bbox: tuple[float, float, float, float] | None, min_size: float = 0.0
) -> str:
    if bbox is None:
        return ""
    x0, top, x1, bottom = bbox
    region = page.within_bbox((x0, top, x1, bottom), strict=False)
    if min_size:
        region = region.filter(
            lambda obj: obj.get("object_type") != "char" or float(obj.get("size", 0)) >= min_size
        )
    lines = region.extract_text_lines(strip=True, return_chars=True)
    if not lines:
        return ""
    # Notion pads cells symmetrically, so the left gap gives the usable right edge.
    right_edge = x1 - max(min(line["x0"] for line in lines) - x0, 0.0)
    prepared = []
    for line in lines:
        chars = line.get("chars") or []
        first_width = float(chars[0]["width"]) if chars else 0.0
        prepared.append((line["text"], right_edge - float(line["x1"]), first_width))
    return join_wrapped_lines(prepared)


def _is_bold(word: dict[str, Any]) -> bool:
    return bool(BOLD_FONT.search(str(word.get("fontname", ""))))


def _inside(top: float, bboxes: list[tuple[float, float, float, float]]) -> bool:
    return any(bbox[1] - 2 <= top <= bbox[3] + 2 for bbox in bboxes)


def _headings(page: Any, table_boxes: list[tuple[float, float, float, float]], body_size: float):
    lines: dict[int, list[dict[str, Any]]] = {}
    for word in page.extract_words(extra_attrs=["fontname", "size"]):
        if _is_bold(word) and not _inside(word["top"], table_boxes):
            lines.setdefault(round(word["top"]), []).append(word)
    # Headings start at the content margin; bold text inside table cells is indented.
    margin = min(
        (
            float(char["x0"])
            for char in page.chars
            if float(char.get("size") or 0) >= body_size * 0.85 and char.get("upright", True)
        ),
        default=0.0,
    )
    result = []
    for top, words in sorted(lines.items()):
        words.sort(key=lambda item: item["x0"])
        if words[0]["x0"] > margin + 8:
            continue
        text = _clean(" ".join(word["text"] for word in words))
        size = max(float(word["size"]) for word in words)
        if not text or text.startswith("http") or text.endswith("/") or len(text) > 120:
            continue
        if text[0].isalpha() and text[0].islower():
            continue
        result.append((float(top), text, size >= body_size * 1.8))
    return result


def _font_family(char: dict[str, Any]) -> str:
    return str(char.get("fontname", "")).split("+", 1)[-1]


def _repair_glyphs(pdf: Any) -> None:
    """Restore punctuation drawn with glyphs that have no Unicode mapping.

    Chrome subsets fonts and sometimes omits ToUnicode entries for hyphens, ``@`` and
    brackets; pdfminer then reports ``\x00``. Such a glyph is replaced only when visible
    characters of the same font with the same advance width identify it unambiguously.
    """
    widths: dict[tuple[str, float], set[str]] = {}
    unknown: list[tuple[list[dict[str, Any]], int]] = []
    for page in pdf.pages:
        chars = page.chars
        for index, char in enumerate(chars):
            size = float(char.get("size") or 0)
            if not size:
                continue
            key = (_font_family(char), round(float(char["width"]) / size, 3))
            text = char.get("text", "")
            if text == "\x00":
                unknown.append((chars, index))
            elif text and not text.isalnum() and not text.isspace() and text != "@":
                widths.setdefault(key, set()).add(text)
    for chars, index in unknown:
        char = chars[index]
        ratio = round(float(char["width"]) / float(char["size"]), 3)
        family = _font_family(char)
        candidates: set[str] = set()
        for (other_family, other_ratio), texts in widths.items():
            if other_family == family and abs(other_ratio - ratio) <= 0.004:
                candidates |= texts
        previous = chars[index - 1]["text"] if index else ""
        if len(candidates) == 1:
            char["text"] = next(iter(candidates))
        elif candidates == {"(", ")"}:
            char["text"] = ")" if previous.isalnum() else "("


def _body_size(pdf: Any) -> float:
    sizes: dict[float, int] = {}
    for page in pdf.pages[:3]:
        for char in page.chars:
            size = round(float(char.get("size", 0)), 1)
            sizes[size] = sizes.get(size, 0) + 1
    return max(sizes, key=lambda size: sizes[size]) if sizes else 10.0


def _header_index(header: list[str], *tokens: str) -> int | None:
    for index, cell in enumerate(header):
        lowered = cell.replace(" ", "").lower()
        if any(token in lowered for token in tokens):
            return index
    return None


def _status(value: str) -> StudyStatus | None:
    lowered = _clean(value).lower()
    if lowered in STATUS_ALIASES:
        return STATUS_ALIASES[lowered]
    for alias, mapped in STATUS_ALIASES.items():
        if lowered.endswith(alias) and len(lowered) < len(alias) + 12:
            return mapped
    return None


def _telegram_url(value: str) -> str | None:
    explicit = re.search(r"t\.me/([A-Za-z0-9_]{5,32})", value)
    if explicit:
        return f"https://t.me/{explicit.group(1)}"
    compact = re.sub(r"\s+", "", CONTROL.sub("", value)).lstrip("@")
    match = TELEGRAM_HANDLE.fullmatch(compact)
    return f"https://t.me/{match.group(0)}" if match else None


def _row_cells(page: Any, table: Any, row_index: int) -> list[str]:
    row = table.rows[row_index]
    return [_cell_text(page, cell) for cell in row.cells]


Row = tuple[list[str], tuple[float, float, float, float]]


def _table_rows(page: Any, table: Any, next_top: float, body_size: float) -> list[Row]:
    """Return table rows plus the upper part of a row that continues on the next page.

    Chrome does not draw the bottom border of a row split by a page break, so the table
    finder stops at the previous row and the text of the split part would be lost.
    """
    rows: list[Row] = [
        (_row_cells(page, table, index), table.rows[index].bbox) for index in range(len(table.rows))
    ]
    last = table.rows[-1]
    bottom = min(next_top, float(page.height)) - 1
    top = float(last.bbox[3]) + 1
    if bottom - top < 4:
        return rows
    columns = [cell for cell in last.cells if cell is not None]
    cells = [
        _cell_text(page, (cell[0], top, cell[2], bottom), min_size=body_size * 0.85)
        for cell in columns
    ]
    if columns and any(cells):
        rows.append((cells, (columns[0][0], top, columns[-1][2], bottom)))
    return rows


def _columns(table: Any) -> list[tuple[float, float]]:
    return [(float(cell[0]), float(cell[2])) for cell in table.rows[-1].cells if cell is not None]


def _row_links(page: Any, row_bbox: tuple[float, float, float, float]) -> list[str]:
    links = []
    for link in page.hyperlinks:
        uri = link.get("uri") or ""
        top = float(link.get("top", -100))
        if uri.startswith(("http://", "https://")) and row_bbox[1] - 1 <= top <= row_bbox[3] + 1:
            links.append(uri)
    return links


def _limited(value: str, limit: int, draft: _Draft, code: str) -> str:
    if len(value) <= limit:
        return value
    draft.warn(code, value[:80])
    return value[: limit - 1].rstrip() + "…"


def _strategy_table(
    draft: _Draft,
    page: Any,
    header: list[str],
    rows: list[Row],
    page_number: int,
    *,
    continues_previous: bool = False,
) -> None:
    """Append table rows as tasks; rows without a title continue the previous task."""
    title_col = _header_index(header, "этап", "задач", "name", "название")
    period_col = _header_index(header, "период", "срок")
    comment_col = _header_index(header, "коммент", "описан")
    material_col = _header_index(header, "материал", "ссылк")
    status_col = _header_index(header, "статус", "status", "select")
    if not draft.sections:
        draft.sections.append({"title": "Вводная часть", "tasks": []})
        draft.warn("section_missing")
    section = draft.sections[-1]
    for row_index, (cells, row_bbox) in enumerate(rows):

        def value(index: int | None, cells: list[str] = cells) -> str:
            return cells[index] if index is not None and index < len(cells) else ""

        title = value(title_col)
        comment = value(comment_col)
        period = value(period_col)
        material = value(material_col)
        status_value = _status(value(status_col)) if status_col is not None else None
        if status_value is None:
            status_value = next((s for s in map(_status, reversed(cells)) if s), None)
        links = _row_links(page, row_bbox)
        materials = list(dict.fromkeys([*URL.findall(material), *links]))
        if material and not URL.search(material):
            materials.append(material)
        if not title or (continues_previous and row_index == 0):
            previous_tasks = [task for item in draft.sections for task in item["tasks"]]
            if previous_tasks:
                prior = previous_tasks[-1]
                prior["title"] = " ".join(x for x in [prior["title"], title] if x)
                # A split row is one cell, so its parts continue the same text.
                prior["description"] = " ".join(x for x in [prior["description"], comment] if x)
                prior["period_text"] = " ".join(x for x in [prior["period_text"], period] if x)
                prior["materials"] = list(dict.fromkeys(prior["materials"] + materials))
            elif comment or material:
                draft.warn("orphan_row", f"{page_number}")
            continue
        if status_value is None:
            draft.warn("status_missing", title[:80])
        section["tasks"].append(
            {
                "title": title,
                "description": comment,
                "period_text": period,
                "materials": materials,
                "study_status": status_value or StudyStatus.NOT_STARTED,
            }
        )


def _point_table(draft: _Draft, rows: list[Row], key: str) -> None:
    header = rows[0][0]
    telegram_col = _header_index(header, "тг", "telegram", "телеграм")
    for cells, _ in rows[1:]:
        for index, cell in enumerate(cells):
            # Notion prints "Untitled" for an empty linked page.
            if not cell or cell == "Untitled":
                continue
            if key == "point_a" and index == telegram_col:
                draft.telegram_parts.append(cell)
                continue
            label = header[index] if index < len(header) else ""
            draft.points[key].setdefault(label, []).append(cell)


def _point_text(values: dict[str, list[str]]) -> str:
    lines = []
    for label, parts in values.items():
        text = " ".join(parts)
        lines.append(f"{label}: {text}" if label else text)
    return "\n".join(lines)


def parse_notion_pdf(data: bytes) -> StrategyImportDraft:
    if not data.startswith(b"%PDF"):
        raise _invalid("unsupported_file", "File is not a PDF document")
    import pdfplumber  # Imported lazily: only the import endpoint needs the PDF stack.

    draft = _Draft()
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise _invalid("unreadable_pdf", "PDF document cannot be read")
            if page_count > MAX_PDF_PAGES:
                raise _invalid("too_many_pages", "PDF document has too many pages")
            _repair_glyphs(pdf)
            body_size = _body_size(pdf)
            active_point: str | None = None
            for page_number, page in enumerate(pdf.pages, 1):
                tables = page.find_tables()
                boxes = [table.bbox for table in tables]
                events: list[tuple[float, str, Any]] = [
                    (top, "heading", (text, is_title))
                    for top, text, is_title in _headings(page, boxes, body_size)
                ]
                events.extend((table.bbox[1], "table", table) for table in tables)
                events.sort(key=lambda event: event[0])
                if draft.strategy_header and draft.strategy_columns:
                    # Text above the first table or heading continues a row from the previous page.
                    bottom = (events[0][0] if events else float(page.height)) - 1
                    cells = [
                        _cell_text(page, (x0, 0, x1, bottom), min_size=body_size * 0.85)
                        for x0, x1 in draft.strategy_columns
                    ]
                    if bottom > 4 and any(cells):
                        row_box = (
                            draft.strategy_columns[0][0],
                            0.0,
                            draft.strategy_columns[-1][1],
                            bottom,
                        )
                        _strategy_table(
                            draft,
                            page,
                            draft.strategy_header,
                            [(cells, row_box)],
                            page_number,
                            continues_previous=True,
                        )
                for event_index, (_, kind, payload) in enumerate(events):
                    if kind == "heading":
                        text, is_title = payload
                        if is_title:
                            draft.source_title = draft.source_title or text
                            continue
                        point = POINT_HEADINGS.get(text.lower())
                        draft.strategy_columns = []
                        if point:
                            active_point = point
                            draft.strategy_header = None
                            continue
                        if text[0].isdigit():
                            continue
                        active_point = None
                        if not draft.sections or draft.sections[-1]["title"] != text:
                            draft.sections.append({"title": text, "tasks": []})
                        continue
                    table = payload
                    if not table.rows:
                        continue
                    next_top = next(
                        (
                            event[0]
                            for event in events[event_index + 1 :]
                            if event[0] > table.bbox[3]
                        ),
                        float(page.height),
                    )
                    rows = _table_rows(page, table, next_top, body_size)
                    header = rows[0][0]
                    header_text = "".join(header).replace(" ", "").lower()
                    if "этап" in header_text and any(
                        token in header_text for token in ("статус", "status", "select")
                    ):
                        active_point = None
                        draft.strategy_header = header
                        draft.strategy_columns = _columns(table)
                        _strategy_table(draft, page, header, rows[1:], page_number)
                    elif active_point and len(header) > 1:
                        _point_table(draft, rows, active_point)
                    elif draft.strategy_header and len(header) == len(draft.strategy_header):
                        # A table continued on the next page without a repeated header row.
                        draft.strategy_columns = _columns(table)
                        _strategy_table(draft, page, draft.strategy_header, rows, page_number)
    except ApiError:
        raise
    except Exception as error:  # noqa: BLE001  any parser failure means an unreadable file
        raise _invalid("unreadable_pdf", "PDF document cannot be read") from error
    sections = []
    for raw_section in draft.sections:
        if not raw_section["tasks"]:
            continue
        tasks = [
            ImportedTask(
                title=_limited(task["title"], TITLE_LIMIT, draft, "title_truncated"),
                description=_limited(task["description"], LONG_LIMIT, draft, "text_truncated"),
                period_text=_limited(task["period_text"], SHORT_LIMIT, draft, "text_truncated"),
                materials=[
                    _limited(item, SHORT_LIMIT, draft, "text_truncated")
                    for item in task["materials"][:100]
                ],
                study_status=task["study_status"],
            )
            for task in raw_section["tasks"]
        ]
        sections.append(
            ImportedSection(
                title=_limited(raw_section["title"], TITLE_LIMIT, draft, "title_truncated"),
                tasks=tasks,
            )
        )
    if not sections:
        raise _invalid("no_strategy_found", "No strategy tables found in the PDF document")
    profile = ImportedProfile(
        point_a=_limited(_point_text(draft.points["point_a"]), LONG_LIMIT, draft, "text_truncated")
        or None,
        point_b=_limited(_point_text(draft.points["point_b"]), LONG_LIMIT, draft, "text_truncated")
        or None,
        telegram=_telegram_url("".join(draft.telegram_parts)) if draft.telegram_parts else None,
    )
    return StrategyImportDraft(
        source_title=draft.source_title[:SHORT_LIMIT],
        sha256=hashlib.sha256(data).hexdigest(),
        page_count=page_count,
        profile=profile,
        sections=sections,
        warnings=list(draft.warnings.values()),
    )


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def apply_strategy_import(
    database: Session,
    actor: User,
    student: Student,
    payload: StrategyImportApply,
    now: datetime,
) -> tuple[Strategy, int]:
    strategy = database.scalar(select(Strategy).where(Strategy.student_id == student.id))
    if strategy is None:
        strategy = create_strategy(database, actor, student, StrategyCreate())
    else:
        _lock_strategy_write(database, strategy, actor)
        if database.scalar(
            select(StrategySection.id).where(StrategySection.strategy_id == strategy.id).limit(1)
        ):
            raise _conflict("strategy_not_empty", "Strategy already has sections")
    task_count = 0
    for section_position, imported_section in enumerate(payload.sections):
        section = StrategySection(
            strategy_id=strategy.id, title=imported_section.title, position=section_position
        )
        database.add(section)
        database.flush()
        for task_position, imported_task in enumerate(imported_section.tasks):
            primary = next(
                (
                    item
                    for item in imported_task.materials
                    if item.startswith(("http://", "https://"))
                ),
                None,
            )
            task = StrategyTask(
                strategy_id=strategy.id,
                section_id=section.id,
                title=imported_task.title,
                description=imported_task.description,
                materials=list(imported_task.materials),
                links={"primary": primary} if primary else {},
                period_text=imported_task.period_text,
                position=task_position,
                study_status=imported_task.study_status,
                review_status=ReviewStatus.NONE,
            )
            database.add(task)
            database.flush()
            database.add(
                TaskHistory(
                    task_id=task.id,
                    actor_user_id=actor.id,
                    event_type="task_created",
                    details={"source": "notion_import"},
                    created_at=now,
                )
            )
            task_count += 1
    metadata = dict(strategy.source_metadata or {})
    metadata["notion_import"] = {
        "file_name": payload.source.file_name,
        "sha256": payload.source.sha256,
        "title": payload.source.title,
        "imported_at": now.isoformat(),
        "sections": len(payload.sections),
        "tasks": task_count,
    }
    strategy.source_metadata = metadata
    profile_values: dict[str, Any] = {}
    if payload.profile.point_a is not None:
        profile_values["point_a"] = payload.profile.point_a
    if payload.profile.point_b is not None:
        profile_values["point_b"] = payload.profile.point_b
    if payload.profile.telegram is not None:
        profile_values["links"] = {"telegram": str(payload.profile.telegram)}
    if profile_values:
        update_student(
            database,
            actor,
            student,
            StudentUpdate(expected_version=payload.expected_version, **profile_values),
            now,
        )
    elif student.version != payload.expected_version:
        database.rollback()
        raise _conflict("version_conflict", "Student was changed")
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STRATEGY_IMPORTED,
        target_group_id=student.group_id,
        details={
            "strategy_id": strategy.id,
            "student_id": student.id,
            "sections": len(payload.sections),
            "tasks": task_count,
            "profile_fields": sorted(profile_values),
            "sha256": payload.source.sha256,
        },
    )
    return strategy, task_count

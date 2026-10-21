"""Extract the supplied Notion PDF strategies into a reviewable, stable seed.

Run with the bundled Python that provides pdfplumber. No user records are read or changed.
"""
import json
import logging
import re
from pathlib import Path

import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.CRITICAL)
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public" / "strategies"
OUTPUT = SOURCE / "strategy-seed.json"
STARTS = {"group_1": "2026-08-03", "group_2": "2026-09-07", "group_3": "2026-09-17", "group_4": "2026-10-01"}
ENDS = {"group_1": "2027-01-18", "group_2": "2027-03-07", "group_3": "2027-03-17", "group_4": "2027-04-01"}
KNOWN = {"done": "done", "in progress": "in_progress", "hold": "hold", "not started": "not_started"}


def clean(value):
    return re.sub(r"[ \t]+", " ", (value or "").replace("\x00", "").replace("\u0001", "")).strip()


def flattened(value):
    return clean(value).replace("\n", " ")


def section_headings(page, tables):
    lines = {}
    for word in page.extract_words(extra_attrs=["fontname"]):
        if (
            "Inter_700wght" in word["fontname"]
            and word["x0"] < 260
            and not any(table.bbox[1] - 2 <= word["top"] <= table.bbox[3] + 2 for table in tables)
        ):
            lines.setdefault(round(word["top"]), []).append(word["text"])
    result = []
    for top, words in sorted(lines.items()):
        title = flattened(" ".join(words))
        if not title or "Стратегия" in title or "действий" == title or title in {"Точка А", "Точка Б"}:
            continue
        if title.startswith("http") or title.endswith("/") or title[0].isdigit() or len(title) > 90:
            continue
        result.append((top, title))
    return result


def main_tables(page):
    result = []
    for table in page.find_tables():
        rows = table.extract()
        if not rows or len(rows[0]) < 5:
            continue
        header = " ".join(flattened(cell) for cell in rows[0])
        if "Этап" in header and ("Статус" in header or "Select" in header):
            result.append((table, rows))
    return result


def status_from_row(row):
    for cell in reversed(row):
        value = flattened(cell).lower()
        if value in KNOWN:
            return KNOWN[value]
        for source, target in KNOWN.items():
            if value.endswith(source) and len(value) < len(source) + 12:
                return target
    return "not_started"


def column(header, token, fallback):
    return next((i for i, cell in enumerate(header) if token in flattened(cell)), fallback)


def extract_pdf(path):
    source_key = path.stem.rsplit("_", 1)[-1]
    student_id = f"strategy-student-{source_key}"
    name = path.name.split("_Стратегия")[0].replace("_", " ")
    sections, tasks, intro, problems, orphan = [], [], [], [], []
    active_section = None
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            tables = main_tables(page)
            headings = section_headings(page, [table for table, _ in tables]) if tables or tasks else []
            if not tables and page_number <= 3:
                intro.append(page.extract_text() or "")
            events = [(top, "heading", title) for top, title in headings]
            events.extend((table.bbox[1], "table", (table, rows)) for table, rows in tables)
            for _, kind, payload in sorted(events, key=lambda event: event[0]):
                if kind == "heading":
                    title = payload
                    if title in {"Точка А", "Точка Б"}:
                        continue
                    if not sections or sections[-1]["title"] != title:
                        active_section = f"strategy-section-{source_key}-{len(sections)+1}"
                        sections.append({"id": active_section, "studentId": student_id, "title": title, "order": len(sections), "createdAt": "2026-10-21T00:00:00.000Z"})
                    continue
                table, rows = payload
                header = rows[0]
                title_col = column(header, "Этап", 1)
                period_col = column(header, "Перио", 2)
                comment_col = column(header, "Комментар", 3)
                material_col = column(header, "Материал", -1)
                if not active_section:
                    active_section = f"strategy-section-{source_key}-{len(sections)+1}"
                    sections.append({"id": active_section, "studentId": student_id, "title": "Вводная часть", "order": len(sections), "createdAt": "2026-10-21T00:00:00.000Z"})
                for row_index, row in enumerate(rows[1:], 1):
                    title = flattened(row[title_col]) if title_col < len(row) else ""
                    comment = clean(row[comment_col]) if comment_col < len(row) else ""
                    period = clean(row[period_col]) if period_col < len(row) else ""
                    material = clean(row[material_col]) if 0 <= material_col < len(row) else ""
                    status = status_from_row(row)
                    cell_bbox = table.rows[row_index].bbox if row_index < len(table.rows) else table.bbox
                    links = [link.get("uri", "") for link in page.hyperlinks if link.get("uri") and cell_bbox[1]-1 <= link.get("top", -100) <= cell_bbox[3]+1]
                    materials = list(dict.fromkeys([*(re.findall(r"https?://[^\s]+", material)), *links]))
                    if material and not materials:
                        materials = [material]
                    if not title:
                        if tasks:
                            prior = tasks[-1]
                            prior["description"] = "\n".join(x for x in [prior["description"], comment] if x)
                            prior["period"] = "\n".join(x for x in [prior["period"], period] if x)
                            prior["materials"] = list(dict.fromkeys(prior["materials"] + materials))
                        elif comment or material:
                            orphan.append(f"Страница {page_number}: {comment} {material}".strip())
                        continue
                    task_id = f"strategy-task-{source_key}-{len(tasks)+1}"
                    tasks.append({"id":task_id,"studentId":student_id,"sectionId":active_section,"title":title,"description":comment,"period":period,"materials":materials,"studyStatus":status,"status":"done" if status=="done" else "progress" if status in {"in_progress","hold"} else "backlog","stage":"start","owner":"Не назначен","dueAt":"","url":materials[0] if materials and materials[0].startswith("http") else "","comments":"","order":len(tasks),"blocker":False,"createdAt":"2026-10-21T00:00:00.000Z","updatedAt":"2026-10-21T00:00:00.000Z","reviewStatus":"none","approvalStatus":None,"approvalType":"","approvalSentAt":"","approvalComment":"","history":[],"sourceFile":str(path.relative_to(ROOT)).replace("\\", "/")})
        if not tasks:
            problems.append("no strategy table rows extracted")
    raw_intro = "\n\n".join(intro)
    point_a = raw_intro.split("Точка А",1)[-1].split("Точка Б",1)[0].strip() if "Точка А" in raw_intro else ""
    point_b = raw_intro.split("Точка Б",1)[-1].strip() if "Точка Б" in raw_intro else ""
    telegram = re.search(r"@[A-Za-z][A-Za-z0-9_]{4,}", point_a)
    group_id = f"strategy-{path.parent.name}"
    student = {"id":student_id,"groupId":group_id,"name":name,"age":None,"photo":"","avatarIndex":-1,"stage":"start","stageKnown":False,"startsAt":STARTS[path.parent.name],"level":"","desiredPosition":"","careerGoal":"","links":{"figma":"","portfolio":"","resume":"","telegram":telegram.group(0) if telegram else "","notion":""},"background":"","experience":"","strengths":"","growthAreas":"","difficulties":"","expectations":"","personalNotes":"","pointA":point_a,"pointB":point_b,"notes":"\n\n".join(orphan),"strategyUpdatedAt":"2026-10-21T00:00:00.000Z","createdAt":"2026-10-21T00:00:00.000Z"}
    if orphan:
        problems.append(f"{len(orphan)} orphan continuation rows preserved in curator notes")
    return student, sections, tasks, problems


def main():
    paths = sorted(SOURCE.rglob("*.pdf"))
    groups = [{"id":f"strategy-{key}","name":f"Группа {key[-1]}","startsAt":STARTS[key],"endsAt":ENDS[key],"actualEndsAt":"","status":"active","statusBeforeArchive":None,"notes":"","createdAt":"2026-10-21T00:00:00.000Z"} for key in STARTS]
    students, sections, tasks, report = [], [], [], []
    for path in paths:
        try:
            student, student_sections, student_tasks, problems = extract_pdf(path)
            students.append(student); sections.extend(student_sections); tasks.extend(student_tasks)
            report.append({"file":str(path.relative_to(ROOT)).replace("\\", "/"),"sections":len(student_sections),"tasks":len(student_tasks),"problems":problems})
        except Exception as exc:
            report.append({"file":str(path.relative_to(ROOT)).replace("\\", "/"),"sections":0,"tasks":0,"problems":[str(exc)]})
    seed = {"version":3,"groups":groups,"students":students,"sections":sections,"tasks":tasks,"meetings":[],"homeworks":[],"demo":False,"importReport":report}
    OUTPUT.write_text(json.dumps(seed,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"files":len(paths),"groups":len(groups),"students":len(students),"sections":len(sections),"tasks":len(tasks),"issues":[entry for entry in report if entry["problems"]]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()

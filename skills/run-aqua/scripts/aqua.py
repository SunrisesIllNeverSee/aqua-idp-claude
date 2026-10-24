#!/usr/bin/env python3
"""Deterministic file operations for the AQUA personal workspace (Python 3 stdlib)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from beta import configure as configure_beta, record as record_beta


SCHEMA_VERSION = "0.1.13"
Q_FIELDS = [
    "question_ref", "application_path", "source_ref", "source_order",
    "original_question", "options", "required", "limit", "asking_summary",
    "general_or_custom", "topic", "related_group", "answer_refs", "status",
    "field_state", "field_state_reason",
]
A_FIELDS = [
    "answer_ref", "title", "answer_path", "status", "preferred", "answers_what",
    "question_refs", "source_refs", "context_limits", "facts_as_of", "approved_at",
    "approved_sha256",
]
R_FIELDS = ["question_ref", "answer_ref", "fit", "reason", "linked_at"]
H_INPUT_FIELDS = ["application", "source_path", "source_question", "answer_text", "source_date", "kind", "theme", "question_ref"]
H_FIELDS = ["history_ref", *H_INPUT_FIELDS, "status"]
HL_FIELDS = ["history_ref", "question_ref", "reason", "linked_at"]
FUNNELS = {"Tech", "Jobs", "College", "Grants Funding"}
FUNNEL_FILE = "Funnel.txt"
SOURCE_MODES = ("blank", "completed", "unknown")
FIELD_STATES = ("not_applicable", "skipped")
PLAN_FIELDS = ["entity", "program", "funnel", "source_file", "source_url", "questions_csv", "history_csv", "answer_map_csv", "source_mode"]
QUESTION_INPUT_FIELDS = ["order", "question", "options", "required", "limit", "source_ref"]
HISTORY_RUN_FIELDS = ["source_question", "answer_text", "source_date", "kind", "theme", "question_ref"]
ANSWER_MAP_FIELDS = ["question_ref", "answer_ref"]
RUN_STATUS_FIELDS = ["application_key", "entity", "program", "historical_candidates", "A", "QU", "Answers", "S", "work_needed", "next_action"]
WORK_VIEW_FIELDS = [
    "application", "question_ref", "source_order", "original_question", "required", "limit",
    "related_group", "field_state", "asking_summary", "general_or_custom", "category",
    "answer_ref", "answer_text", "answer_status", "answer_source", "facts_as_of",
]
# 0.1.12 headers. Workspaces still using them must run `migrate` before other commands.
LEGACY_HEADERS = {
    tuple(Q_FIELDS): Q_FIELDS[:-2],
    tuple(A_FIELDS): A_FIELDS[:-1],
}
LEGACY_PLAN_FIELDS = PLAN_FIELDS[:-1]
READY_NAME = "Application-ready.md"
DRAFT_NAME = "Application-draft.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70]
    if not value:
        raise ValueError("Name needs letters or numbers")
    return value


def root(path: str) -> Path:
    return Path(path).expanduser().resolve()


def inside(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Path escapes AQUA workspace: {rel}")
    return target


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    try:
        with handle as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(handle.name, path)
    finally:
        if Path(handle.name).exists():
            Path(handle.name).unlink()


def csv_header(path: Path) -> list[str] | None:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), None)


def read_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Missing index; run init first: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != fields:
            if reader.fieldnames == LEGACY_HEADERS.get(tuple(fields)):
                raise ValueError(f"{path.name} uses the 0.1.12 schema; run `aqua.py migrate --workspace <folder>` "
                                 "first (it backs up the indexes before adding columns)")
            raise ValueError(f"Unexpected columns in {path}; preserve the AQUA schema")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"Malformed CSV: {path}")
    return rows


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    import io
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, out.getvalue())


def qpath(w: Path) -> Path:
    return w / "QU Questions/Question-Index.csv"


def apath(w: Path) -> Path:
    return w / "A Answers/Answer-Index.csv"


def rpath(w: Path) -> Path:
    return w / "A Answers/Reuse-Links.csv"


def hpath(w: Path) -> Path:
    return w / "A Answers/Historical-Answer-Catalog.csv"


def hlpath(w: Path) -> Path:
    return w / "A Answers/Historical-Links.csv"


def index_files(w: Path) -> list[tuple[Path, list[str]]]:
    return [(qpath(w), Q_FIELDS), (apath(w), A_FIELDS), (rpath(w), R_FIELDS),
            (hpath(w), H_FIELDS), (hlpath(w), HL_FIELDS)]


def legacy_schema(w: Path) -> bool:
    """True when an index still has a 0.1.12 header or the 0.1.13 link file is absent."""
    found_index = False
    for path, fields in index_files(w):
        if not path.exists():
            continue
        found_index = True
        if csv_header(path) == LEGACY_HEADERS.get(tuple(fields)):
            return True
    return found_index and not hlpath(w).exists()


def next_ref(rows: list[dict[str, str]], field: str, prefix: str) -> str:
    used = [int(m.group(1)) for row in rows if (m := re.fullmatch(prefix + r"(\d+)", row[field]))]
    return f"{prefix}{max(used, default=0) + 1:03d}"


def template(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "assets" / name).read_text(encoding="utf-8")


def normalize_answer(text: str) -> str:
    """Approval digest normalization: LF newlines, Unicode NFC, no trailing spaces, no outer blank lines."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def answer_digest(text: str) -> str:
    return hashlib.sha256(normalize_answer(text).encode("utf-8")).hexdigest()


def application_funnels(w: Path) -> set[str]:
    found = set()
    for record in (w / "A Applications").glob("*/Application.md"):
        match = re.search(r"^Funnel: (.+)$", record.read_text(encoding="utf-8"), re.M)
        if not match or match.group(1).strip() not in FUNNELS:
            raise ValueError(f"Application has no valid funnel: {record}")
        found.add(match.group(1).strip())
    return found


def workspace_funnel(w: Path) -> str:
    marker = w / FUNNEL_FILE
    if marker.exists():
        funnel = marker.read_text(encoding="utf-8").strip()
        if funnel not in FUNNELS:
            raise ValueError(f"Invalid workspace funnel in {marker}")
    else:
        found = application_funnels(w)
        if len(found) != 1:
            raise ValueError("Workspace has no single funnel; initialize a separate Tech, Grants Funding, College, or Jobs folder")
        funnel = next(iter(found))  # Existing one-funnel workspaces remain readable.
    other = application_funnels(w) - {funnel}
    if other:
        raise ValueError(f"Workspace is {funnel}; found applications for {', '.join(sorted(other))}")
    return funnel


def init(w: Path, args: argparse.Namespace | None = None) -> None:
    requested = getattr(args, "funnel", None)
    if requested and requested not in FUNNELS:
        raise ValueError("Choose Tech, Grants Funding, College, or Jobs")
    if legacy_schema(w):
        raise ValueError("This workspace uses the 0.1.12 schema; run `aqua.py migrate --workspace <folder>` first")
    if (w / FUNNEL_FILE).exists() or (w / "START-HERE.md").exists():
        try:
            funnel = workspace_funnel(w)
        except ValueError:
            if (w / FUNNEL_FILE).exists() or application_funnels(w) or not requested:
                raise
            funnel = requested  # Existing empty legacy folder selected explicitly.
        if requested and requested != funnel:
            raise ValueError(f"This workspace is {funnel}; use a separate {requested} folder")
    else:
        funnel = requested or (w.name if w.name in FUNNELS else None)
        if funnel is None:
            raise ValueError("New workspaces need --funnel and a separate folder for that funnel")
        if w.name != funnel:
            raise ValueError(f"New funnel folder must be named {funnel}; use <AQUA root>/{funnel}")
    w.mkdir(parents=True, exist_ok=True)
    if not (w / FUNNEL_FILE).exists():
        atomic_text(w / FUNNEL_FILE, funnel + "\n")
    for folder in ("A Applications", "QU Questions", "A Answers/Background", "S Submit"):
        (w / folder).mkdir(parents=True, exist_ok=True)
    for name in ("START-HERE.md", "PROGRESS.md", "Applicant-Context.md"):
        path = w / name
        if not path.exists():
            atomic_text(path, template(name).replace("{{WORKSPACE}}", str(w)).replace("{{FUNNEL}}", funnel))
    for path, fields in index_files(w):
        if not path.exists():
            write_rows(path, fields, [])
        else:
            read_rows(path, fields)
    for name, fields in (("Run-Plan.csv", PLAN_FIELDS),
                         ("Run-Questions-Template.csv", QUESTION_INPUT_FIELDS),
                         ("Run-History-Template.csv", HISTORY_RUN_FIELDS),
                         ("Run-Answer-Map-Template.csv", ANSWER_MAP_FIELDS)):
        path = w / name
        if not path.exists():
            write_rows(path, fields, [])
    if not (w / "Questions-and-Answers-View.csv").exists():
        write_rows(w / "Questions-and-Answers-View.csv", WORK_VIEW_FIELDS, [])
    print(f"AQUA {funnel} workspace ready: {w}")


def migrate(w: Path) -> None:
    """Upgrade 0.1.12 indexes in place after backing them up; never invents approval digests."""
    if not (w / "START-HERE.md").exists():
        raise ValueError("Initialize this AQUA workspace first")
    workspace_funnel(w)
    plan = []
    for path, fields in index_files(w):
        if not path.exists():
            if path == hlpath(w):
                plan.append((path, fields, None))
                continue
            raise ValueError(f"Missing index; inspect before migrating: {path}")
        header = csv_header(path)
        if header == fields:
            continue
        legacy = LEGACY_HEADERS.get(tuple(fields))
        if header != legacy:
            raise ValueError(f"Unexpected columns in {path}; migration stopped without changes")
        plan.append((path, fields, legacy))
    if not plan:
        print(f"Workspace schema already current ({SCHEMA_VERSION}); nothing changed")
        return
    backup = w / ".aqua-migrations" / f"{now().replace(':', '')}-to-{SCHEMA_VERSION}"
    backup.mkdir(parents=True, exist_ok=False)
    for path, _, legacy in plan:
        if legacy is not None:
            shutil.copy2(path, backup / path.name)
    notes = []
    for path, fields, legacy in plan:
        if legacy is None:
            write_rows(path, fields, [])
            notes.append(f"- Created {path.relative_to(w)}")
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        upgraded = [dict(dict.fromkeys(fields, ""), **row) for row in rows]
        write_rows(path, fields, upgraded)
        notes.append(f"- {path.relative_to(w)}: {len(rows)} row(s); added {', '.join(f for f in fields if f not in legacy)}")
    pending = [r["answer_ref"] for r in read_rows(apath(w), A_FIELDS)
               if r["status"] == "approved" and not r["approved_sha256"]]
    notes.append(f"- Approved versions without an approval digest: {len(pending)}"
                 + (f" ({', '.join(pending)}); run reconfirm-approval after the applicant reconfirms the current wording" if pending else ""))
    atomic_text(backup / "MIGRATION.md", f"# AQUA schema migration to {SCHEMA_VERSION}\n\nRun: {now()}\n"
                f"Backup of changed indexes: this folder.\n\n" + "\n".join(notes) + "\n")
    print(f"Migrated to {SCHEMA_VERSION}; backup: {backup.relative_to(w)}")
    print("\n".join(notes))


def app_dir(w: Path, app: str) -> Path:
    candidate = inside(w, f"A Applications/{app}")
    if candidate.parent != w / "A Applications":
        raise ValueError("Use a single application folder name")
    return candidate


def source_mode(record: Path) -> str:
    match = re.search(r"^Source mode: (\w+)", record.read_text(encoding="utf-8"), re.M)
    mode = match.group(1).lower() if match else "unknown"
    return mode if mode in SOURCE_MODES else "unknown"


def set_source_mode(record: Path, mode: str) -> bool:
    """Record a verified mode on an application whose mode is still unknown; refuse a conflicting change."""
    current = source_mode(record)
    if mode == "unknown" or mode == current:
        return False
    if current != "unknown":
        raise ValueError(f"Application source mode is {current}; inspect the source before recording {mode}")
    content = record.read_text(encoding="utf-8")
    line = f"Source mode: {mode}"
    content = (re.sub(r"^Source mode: .*$", line, content, count=1, flags=re.M)
               if re.search(r"^Source mode: ", content, re.M) else content.replace("\n\n", f"\n{line}\n\n", 1))
    atomic_text(record, content)
    return True


def application_title(record: Path) -> str:
    content = record.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", content, re.M)
    entity = re.search(r"^Entity: (.+)$", content, re.M)
    name = title.group(1).strip() if title else record.parent.name
    return f"{entity.group(1).strip()} — {name}" if entity and entity.group(1).strip() not in name else name


def add_application(w: Path, args: argparse.Namespace) -> None:
    if args.funnel not in FUNNELS:
        raise ValueError("Funnel must be Tech, Jobs, College, or Grants Funding")
    selected = workspace_funnel(w)
    if args.funnel != selected:
        raise ValueError(f"This workspace is {selected}; create or use a separate {args.funnel} workspace")
    mode = getattr(args, "source_mode", None)
    key = slug(args.entity + "-" + args.title)
    folder = app_dir(w, key)
    record = folder / "Application.md"
    if record.exists():
        if mode and set_source_mode(record, mode):
            print(f"Source mode recorded: {key} = {mode}")
        else:
            print(f"Existing application unchanged: {record}")
        return
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Sources").mkdir(exist_ok=True)
    content = template("Application.md").replace("{{TITLE}}", args.title).replace(
        "{{ENTITY}}", args.entity).replace("{{FUNNEL}}", args.funnel).replace(
        "{{SOURCE_URL}}", args.source_url or "Unknown").replace("{{CAPTURED_AT}}", now()).replace(
        "{{SOURCE_MODE}}", mode or "unknown")
    atomic_text(record, content)
    print(f"Application created: {key} (source mode: {mode or 'unknown'})")


def add_source(w: Path, args: argparse.Namespace) -> None:
    folder = app_dir(w, args.application)
    if not (folder / "Application.md").exists():
        raise ValueError("Create the application first")
    supplied = Path(args.file).expanduser()
    if supplied.is_symlink():
        raise ValueError("Pass a regular source file, not a symlink")
    src = supplied.resolve()
    if not src.is_file():
        raise ValueError(f"Source file not found: {src}")
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    sources = folder / "Sources"
    for existing in sources.iterdir():
        if existing.is_file() and hashlib.sha256(existing.read_bytes()).hexdigest() == digest:
            print(f"Source already archived: {existing.relative_to(w)}")
            return
    stem = slug(src.stem)
    if not stem.startswith(digest[:12] + "-"):  # A file AQUA archived before keeps its single hash prefix.
        stem = f"{digest[:12]}-{stem}"
    target = sources / f"{stem}{src.suffix.lower()}"
    shutil.copy2(src, target)
    print(f"Archived: {target.relative_to(w)} sha256={digest}")


def requirement_arg(args: argparse.Namespace) -> str | None:
    if getattr(args, "required", False):
        return "yes"
    if getattr(args, "optional", False):
        return "no"
    if getattr(args, "unknown", False):
        return "unknown"
    return None


def add_question(w: Path, args: argparse.Namespace) -> None:
    folder = app_dir(w, args.application)
    if not (folder / "Application.md").exists():
        raise ValueError("Create the application first")
    question = Path(args.text_file).read_text(encoding="utf-8").strip() if args.text_file else args.text.strip()
    if not question or args.order < 1:
        raise ValueError("Question text and positive source order required")
    rows = read_rows(qpath(w), Q_FIELDS)
    rel = str((folder / "Application.md").relative_to(w))
    requirement = requirement_arg(args)
    same_slot = [r for r in rows if r["application_path"] == rel and r["source_order"] == str(args.order)]
    if same_slot:
        if len(same_slot) == 1 and same_slot[0]["original_question"] == question:
            existing = same_slot[0]
            supplied = {"required": requirement, "options": args.options, "limit": args.limit,
                        "source_ref": args.source_ref}
            conflicts = [name for name, value in supplied.items() if value is not None and value != existing[name]]
            if conflicts:
                raise ValueError(f"Question {existing['question_ref']} is already indexed with different "
                                 f"{', '.join(conflicts)}; use update-question to change its metadata")
            print(f"Question already indexed: {existing['question_ref']}")
            return
        raise ValueError("Source order already used with different wording; inspect source before editing")
    ref = next_ref(rows, "question_ref", "q")
    row = dict.fromkeys(Q_FIELDS, "")
    row.update(question_ref=ref, application_path=rel, source_ref=args.source_ref or "",
               source_order=str(args.order), original_question=question, options=args.options or "",
               required=requirement or "unknown", limit=args.limit or "", status="captured")
    rows.append(row)
    write_rows(qpath(w), Q_FIELDS, rows)
    print(f"Question indexed: {ref}")


def update_question(w: Path, args: argparse.Namespace) -> None:
    rows = read_rows(qpath(w), Q_FIELDS)
    match = next((r for r in rows if r["question_ref"] == args.question), None)
    if not match:
        raise ValueError("Unknown question reference")
    if args.kind is not None and args.kind not in ("general", "custom"):
        raise ValueError("Kind must be general or custom")
    interpreted = False
    for arg_name, column in (("summary", "asking_summary"), ("kind", "general_or_custom"),
                             ("topic", "topic"), ("group", "related_group")):
        value = getattr(args, arg_name)
        if value is not None:
            match[column] = value
            interpreted = True
    changed = []
    requirement = requirement_arg(args)
    if requirement is not None and requirement != match["required"]:
        match["required"] = requirement
        changed.append(f"required={requirement}")
    for name in ("options", "limit"):
        value = getattr(args, name)
        if value is not None and value != match[name]:  # An explicit empty value clears the field.
            match[name] = value
            changed.append(f"{name}={value or '(cleared)'}")
    if args.group:
        sources = {r["application_path"] + ":" + r["source_order"] for r in rows
                   if r["related_group"] == args.group}
        sources.add(match["application_path"] + ":" + match["source_order"])
        if len(sources) < 2:
            raise ValueError("Use group-questions to establish a new group from two source occurrences")
    if not interpreted and not changed and requirement is None and args.options is None and args.limit is None:
        raise ValueError("Nothing to update; exact question wording cannot be changed")
    if interpreted:
        match["status"] = "organized"
    write_rows(qpath(w), Q_FIELDS, rows)
    print(f"Question updated: {args.question}" + (f" ({'; '.join(changed)})" if changed else ""))


def mark_question(w: Path, args: argparse.Namespace) -> None:
    """Record that a field does not apply or was deliberately left blank; never creates bank answers."""
    rows = read_rows(qpath(w), Q_FIELDS)
    match = next((r for r in rows if r["question_ref"] == args.question), None)
    if not match:
        raise ValueError("Unknown question reference")
    if args.clear:
        if not match["field_state"]:
            print(f"Field state already open: {args.question}")
            return
        match["field_state"], match["field_state_reason"] = "", ""
        write_rows(qpath(w), Q_FIELDS, rows)
        print(f"Field state cleared: {args.question}")
        return
    state = "not_applicable" if args.not_applicable else "skipped"
    reason = (args.reason or "").strip()
    if not reason:
        raise ValueError("State the reason (for example the observed branch condition or the applicant's choice)")
    if state == "skipped" and match["required"] != "no":
        raise ValueError(f"Only a known optional field can be skipped; requirement is {match['required']}. "
                         "Use update-question --optional if the source shows it, or --not-applicable "
                         "with the observed branch condition")
    if match["field_state"] == state and match["field_state_reason"] == reason:
        print(f"Field state unchanged: {args.question} = {state}")
        return
    match["field_state"], match["field_state_reason"] = state, reason
    write_rows(qpath(w), Q_FIELDS, rows)
    print(f"Field marked {state}: {args.question}")


def group_questions(w: Path, args: argparse.Namespace) -> None:
    rows = read_rows(qpath(w), Q_FIELDS)
    refs = [part.strip() for part in args.questions.split(",") if part.strip()]
    if len(refs) < 2 or len(refs) != len(set(refs)):
        raise ValueError("Provide at least two distinct question references")
    chosen = [row for row in rows if row["question_ref"] in refs]
    if len(chosen) != len(refs):
        raise ValueError("Unknown question reference")
    occurrences = {row["application_path"] + ":" + row["source_order"] for row in chosen}
    if len(occurrences) < 2:
        raise ValueError("Group needs two distinct source occurrences")
    name = args.group.strip()
    if not name:
        raise ValueError("Group name required")
    for row in chosen:
        row["related_group"] = name
        row["status"] = "organized"
    write_rows(qpath(w), Q_FIELDS, rows)
    print(f"Grouped {len(chosen)} questions: {name}")


def save_answer(w: Path, args: argparse.Namespace) -> None:
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Answer file is empty")
    questions = read_rows(qpath(w), Q_FIELDS)
    refs = [x.strip() for x in args.questions.split(",") if x.strip()]
    known = {r["question_ref"] for r in questions}
    if not refs or any(ref not in known for ref in refs):
        raise ValueError("Provide known question references")
    rows = read_rows(apath(w), A_FIELDS)
    topic = slug(args.title)
    titles = {r["title"] for r in rows if Path(r["answer_path"]).parent == Path("A Answers") / topic}
    if titles and args.title not in titles:
        raise ValueError(f"Title '{args.title}' collides with existing answer topic '{sorted(titles)[0]}' "
                         f"(folder A Answers/{topic}); reuse that exact title for a new version or choose a distinct title")
    folder = w / "A Answers" / topic
    existing = list(folder.glob("v[0-9][0-9][0-9].md")) if folder.exists() else []
    version = max((int(p.stem[1:]) for p in existing), default=0) + 1
    base_refs = [r["answer_ref"] for r in rows if Path(r["answer_path"]).parent == Path("A Answers") / topic]
    base = base_refs[0].split("-v")[0] if base_refs else next_ref(
        [{"answer_ref": r["answer_ref"].split("-v")[0]} for r in rows], "answer_ref", "a")
    answer_ref = f"{base}-v{version:03d}"
    rel = f"A Answers/{topic}/v{version:03d}.md"
    content = (f"# {args.title}\n\nStatus: draft\nAnswer reference: {answer_ref}\n"
               f"Question references: {', '.join(refs)}\nSources: {args.sources or 'Not supplied'}\n"
               f"Context limits: {args.context or 'None recorded'}\n"
               f"Facts as of: {args.facts_as_of or 'Unknown'}\n"
               f"Approval: pending\n\n## What this answers\n\n{args.answers_what or args.title}\n\n"
               f"## Answer\n\n{text}\n\n## Version note\n\n{args.note or 'Initial draft'}\n")
    atomic_text(inside(w, rel), content)
    row = dict.fromkeys(A_FIELDS, "")
    row.update(answer_ref=answer_ref, title=args.title, answer_path=rel, status="draft",
               preferred="no", answers_what=args.answers_what or args.title,
               question_refs=";".join(refs), source_refs=args.sources or "",
               context_limits=args.context or "", facts_as_of=args.facts_as_of or "")
    rows.append(row)
    write_rows(apath(w), A_FIELDS, rows)
    for question in questions:
        if question["question_ref"] in refs:
            old = [value for value in question["answer_refs"].split(";") if value]
            question["answer_refs"] = ";".join(old + [answer_ref])
    write_rows(qpath(w), Q_FIELDS, questions)
    print(f"Draft saved: {answer_ref} -> {rel}")


def verified_body(w: Path, row: dict[str, str]) -> str:
    """Return an approved answer body only if it still matches the digest recorded at approval."""
    if row["status"] != "approved":
        raise ValueError(f"Answer must exist and be approved: {row['answer_ref']}")
    body = answer_body(inside(w, row["answer_path"]))
    if not row["approved_sha256"]:
        raise ValueError(f"Approved answer {row['answer_ref']} has no approval digest (approved before 0.1.13); "
                         "run reconfirm-approval after the applicant reconfirms the current wording")
    if answer_digest(body) != row["approved_sha256"]:
        raise ValueError(f"Approved wording of {row['answer_ref']} changed after approval; restore it, or save the "
                         "change as a new draft with save-answer and seek approval")
    return body


def approve_answer(w: Path, args: argparse.Namespace) -> None:
    if not args.evidence.strip():
        raise ValueError("State the actual user approval; silence is not approval")
    rows = read_rows(apath(w), A_FIELDS)
    row = next((r for r in rows if r["answer_ref"] == args.answer), None)
    if not row:
        raise ValueError("Unknown answer reference")
    if row["status"] == "approved":
        print(f"Already approved: {args.answer}")
        return
    if row["status"] != "draft":
        raise ValueError("Only a draft can be newly approved")
    path = inside(w, row["answer_path"])
    content = path.read_text(encoding="utf-8")
    if "Status: draft\n" not in content or "Approval: pending\n" not in content:
        raise ValueError("Answer file does not match draft index")
    digest = answer_digest(answer_body(path))
    content = content.replace("Status: draft\n", "Status: approved\n", 1).replace(
        "Approval: pending\n", f"Approval: {args.evidence.strip()} ({now()})\n", 1)
    row["status"] = "approved"
    row["approved_at"] = now()
    row["approved_sha256"] = digest
    if args.preferred:
        for other in rows:
            if other["answer_ref"].split("-v")[0] == row["answer_ref"].split("-v")[0]:
                other["preferred"] = "no"
        row["preferred"] = "yes"
    atomic_text(path, content)
    write_rows(apath(w), A_FIELDS, rows)
    print(f"Approved: {args.answer}; preferred={row['preferred']}; sha256={digest[:12]}")


def reconfirm_approval(w: Path, args: argparse.Namespace) -> None:
    """Record a digest for an answer approved before 0.1.13, after the applicant reconfirms its wording."""
    if not args.evidence.strip():
        raise ValueError("State the applicant's reconfirmation of the current wording")
    rows = read_rows(apath(w), A_FIELDS)
    row = next((r for r in rows if r["answer_ref"] == args.answer), None)
    if not row:
        raise ValueError("Unknown answer reference")
    if row["status"] != "approved":
        raise ValueError("Only an approved answer can be reconfirmed; approve a draft with approve-answer")
    path = inside(w, row["answer_path"])
    digest = answer_digest(answer_body(path))
    if row["approved_sha256"]:
        if row["approved_sha256"] == digest:
            print(f"Approval digest already current: {args.answer}")
            return
        raise ValueError("Approved wording changed after approval; save the change as a new draft instead")
    content = path.read_text(encoding="utf-8")
    marker = re.search(r"^Approval: .*$", content, re.M)
    note = f"Approval reconfirmed: {args.evidence.strip()} ({now()})"
    content = content[:marker.end()] + "\n" + note + content[marker.end():] if marker else content
    row["approved_sha256"] = digest
    atomic_text(path, content)
    write_rows(apath(w), A_FIELDS, rows)
    print(f"Approval reconfirmed: {args.answer}; sha256={digest[:12]}")


def link_answer(w: Path, args: argparse.Namespace) -> None:
    """Add a later direct-fit question without changing an approved answer file."""
    reason = args.reason.strip()
    if not reason:
        raise ValueError("Explain why the approved answer directly covers the new question")
    questions = read_rows(qpath(w), Q_FIELDS)
    answers = read_rows(apath(w), A_FIELDS)
    links = read_rows(rpath(w), R_FIELDS)
    question = next((row for row in questions if row["question_ref"] == args.question), None)
    answer = next((row for row in answers if row["answer_ref"] == args.answer), None)
    if question is None or answer is None:
        raise ValueError("Unknown question or answer reference")
    if answer["status"] != "approved":
        raise ValueError("Only an approved answer can be linked for direct reuse")
    verified_body(w, answer)
    existing = next((row for row in links if row["question_ref"] == args.question
                     and row["answer_ref"] == args.answer), None)
    if existing:
        print(f"Reuse link already recorded: {args.question} -> {args.answer}")
        return
    if args.question in answer["question_refs"].split(";"):
        print(f"Answer already linked to question: {args.answer} -> {args.question}")
        return
    links.append(dict(question_ref=args.question, answer_ref=args.answer,
                      fit="direct", reason=reason, linked_at=now()))
    answer["question_refs"] = ";".join(filter(None, [answer["question_refs"], args.question]))
    question["answer_refs"] = ";".join(filter(None, [question["answer_refs"], args.answer]))
    write_rows(rpath(w), R_FIELDS, links)
    write_rows(apath(w), A_FIELDS, answers)
    write_rows(qpath(w), Q_FIELDS, questions)
    print(f"Direct reuse recorded: {args.question} -> {args.answer}")


def import_history(w: Path, args: argparse.Namespace) -> None:
    """Catalog preserved historical Q+A without promoting it to an approved answer."""
    incoming_path = Path(args.input_csv).expanduser().resolve()
    incoming = read_rows(incoming_path, H_INPUT_FIELDS)
    catalog_history_rows(w, incoming)


def catalog_history_rows(w: Path, incoming: list[dict[str, str]]) -> None:
    """Apply the same provenance and idempotency checks to manual and run-plan imports."""
    questions = {row["question_ref"] for row in read_rows(qpath(w), Q_FIELDS)}
    existing = read_rows(hpath(w), H_FIELDS)
    known = {(row["source_path"], row["source_question"], row["answer_text"]): row for row in existing}
    staged = []
    differing = []
    for row in incoming:
        source = inside(w, row["source_path"])
        if not source.is_file():
            raise ValueError(f"Historical source is not archived in workspace: {row['source_path']}")
        if not row["application"].strip() or not row["source_question"].strip() or not row["answer_text"].strip():
            raise ValueError("Historical application, question and answer are required")
        if row["kind"] not in ("general", "custom", "unknown"):
            raise ValueError("Historical kind must be general, custom or unknown")
        if row["question_ref"] and row["question_ref"] not in questions:
            raise ValueError(f"Unknown historical question reference: {row['question_ref']}")
        key = (row["source_path"], row["source_question"], row["answer_text"])
        if key in known:
            if known[key]["question_ref"] != row["question_ref"]:
                differing.append(known[key]["history_ref"])
            continue
        known[key] = row
        staged.append(row)
    for row in staged:
        record = {field: row[field] for field in H_INPUT_FIELDS}
        record["history_ref"] = next_ref(existing, "history_ref", "h")
        record["status"] = "historical_unreviewed"
        existing.append(record)
    write_rows(hpath(w), H_FIELDS, existing)
    print(f"Historical answers cataloged: {len(staged)} new, {len(incoming) - len(staged)} already present")
    if differing:
        print(f"Note: {', '.join(differing)} already cataloged with a different question_ref; re-import does not "
              "change links. Use link-history to connect a historical answer to another question.")


def link_history(w: Path, args: argparse.Namespace) -> None:
    """Mark a historical answer as a candidate for a question; never approves it or edits its provenance."""
    reason = args.reason.strip()
    if not reason:
        raise ValueError("Explain why this historical answer is a candidate for the question")
    history = read_rows(hpath(w), H_FIELDS)
    questions = {row["question_ref"] for row in read_rows(qpath(w), Q_FIELDS)}
    links = read_rows(hlpath(w), HL_FIELDS)
    item = next((row for row in history if row["history_ref"] == args.history), None)
    if item is None or args.question not in questions:
        raise ValueError("Unknown historical answer or question reference")
    if item["question_ref"] == args.question or any(
            row["history_ref"] == args.history and row["question_ref"] == args.question for row in links):
        print(f"Historical candidate already linked: {args.history} -> {args.question}")
        return
    links.append(dict(history_ref=args.history, question_ref=args.question, reason=reason, linked_at=now()))
    write_rows(hlpath(w), HL_FIELDS, links)
    print(f"Historical candidate linked: {args.history} -> {args.question} (not approved)")


def limit_issue(limit: str, answer: str) -> str | None:
    match = re.fullmatch(r"\s*(words|chars)\s*:\s*(\d+)\s*", limit, re.I)
    if not match:
        return "Limit needs manual check" if limit.strip() else None
    actual = len(answer.split()) if match.group(1).lower() == "words" else len(answer)
    maximum = int(match.group(2))
    return f"{actual} {match.group(1).lower()} exceed {maximum}" if actual > maximum else None


def answer_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^## Answer\n\n(.*?)(?=\n## Version note\n|\Z)", content, re.M | re.S)
    if not match:
        raise ValueError(f"Missing answer section: {path}")
    return match.group(1).strip()


def review_sheet(w: Path) -> None:
    """Refresh a readable Q&A view; source indexes and answer files stay authoritative."""
    questions = sorted(read_rows(qpath(w), Q_FIELDS),
                       key=lambda row: (row["application_path"], int(row["source_order"])))
    history = read_rows(hpath(w), H_FIELDS)
    history_links = read_rows(hlpath(w), HL_FIELDS)
    answers = {row["answer_ref"]: row for row in read_rows(apath(w), A_FIELDS)}
    rows = []
    for question in questions:
        base = dict.fromkeys(WORK_VIEW_FIELDS, "")
        base.update(application=Path(question["application_path"]).parent.name,
                    question_ref=question["question_ref"], source_order=question["source_order"],
                    original_question=question["original_question"], required=question["required"],
                    limit=question["limit"], related_group=question["related_group"],
                    field_state=question["field_state"],
                    asking_summary=question["asking_summary"],
                    general_or_custom=question["general_or_custom"], category=question["topic"])
        linked = [(item, "") for item in history if item["question_ref"] == question["question_ref"]]
        for link in history_links:
            if link["question_ref"] == question["question_ref"]:
                item = next((h for h in history if h["history_ref"] == link["history_ref"]), None)
                if item is not None:
                    linked.append((item, f"; linked later: {link['reason']}"))
        for item, note in linked:
            rows.append(dict(base, answer_ref=item["history_ref"], answer_text=item["answer_text"],
                             answer_status=item["status"], answer_source=item["source_path"] + note,
                             facts_as_of=item["source_date"]))
        version_refs = [ref for ref in question["answer_refs"].split(";") if ref]
        for ref in version_refs:
            item = answers.get(ref)
            if item is None:
                raise ValueError(f"Question {question['question_ref']} refers to unknown answer {ref}")
            rows.append(dict(base, answer_ref=ref, answer_text=answer_body(inside(w, item["answer_path"])),
                             answer_status=item["status"], answer_source=item["source_refs"],
                             facts_as_of=item["facts_as_of"]))
        if not linked and not version_refs:
            rows.append(dict(base, answer_status=question["field_state"] or "unanswered",
                             answer_source=question["field_state_reason"]))
    linked_refs = {item["history_ref"] for item in history if item["question_ref"]} | {
        link["history_ref"] for link in history_links}
    for item in history:
        if item["history_ref"] in linked_refs:
            continue
        parts = Path(item["source_path"]).parts
        row = dict.fromkeys(WORK_VIEW_FIELDS, "")
        row.update(application=parts[1] if len(parts) > 2 and parts[0] == "A Applications" else "",
                   original_question=item["source_question"], general_or_custom=item["kind"],
                   category=item["theme"], answer_ref=item["history_ref"], answer_text=item["answer_text"],
                   answer_status="historical_unlinked", answer_source=item["source_path"],
                   facts_as_of=item["source_date"])
        rows.append(row)
    output = w / "Questions-and-Answers-View.csv"
    write_rows(output, WORK_VIEW_FIELDS, rows)
    print(f"Q&A view refreshed: {output}; {len(questions)} questions, {len(rows)} rows")


def assemble(w: Path, args: argparse.Namespace) -> None:
    folder = app_dir(w, args.application)
    app_record = folder / "Application.md"
    if not app_record.exists():
        raise ValueError("Unknown application")
    mode = source_mode(app_record)
    if mode == "completed":
        raise ValueError("This application is a completed historical record; prepare drafts only for a current blank form")
    questions = [r for r in read_rows(qpath(w), Q_FIELDS)
                 if r["application_path"] == str(app_record.relative_to(w))]
    if not questions:
        raise ValueError("Application has no indexed questions")
    questions.sort(key=lambda r: int(r["source_order"]))
    answers = {r["answer_ref"]: r for r in read_rows(apath(w), A_FIELDS)}
    mapping = {}
    for pair in args.map or []:
        if "=" not in pair:
            raise ValueError("Each --map must be question_ref=answer_ref")
        q, a = pair.split("=", 1)
        mapping[q] = a
    known = {r["question_ref"] for r in questions}
    if any(q not in known for q in mapping):
        raise ValueError("A mapped question does not belong to this application")
    lines = [f"# {application_title(app_record)} — application answers", "", f"Prepared: {now()}",
             f"Source application: {app_record.relative_to(w)}", f"Source mode: {mode}",
             "Status: pending checks", "", "## Copyable questions and answers", ""]
    issues = []
    used = []
    resolved = []
    if mode != "blank":
        issues.append("Source mode not verified as a current blank form; record it with "
                      "add-application --source-mode blank after inspecting the source")
    for q in questions:
        ref = q["question_ref"]
        lines.extend([f"### {q['source_order']}. {q['original_question']}", ""])
        if q["options"]:
            lines.extend([f"Options: {q['options']}", ""])
        answer_ref = mapping.get(ref)
        state = q["field_state"]
        if answer_ref:
            if state:
                raise ValueError(f"{ref} is marked {state}; clear it with mark-question --clear before mapping an answer")
            row = answers.get(answer_ref)
            if not row or row["status"] != "approved":
                raise ValueError(f"Answer must exist and be approved: {answer_ref}")
            if ref not in row["question_refs"].split(";"):
                raise ValueError(f"Answer {answer_ref} has no recorded link to {ref}")
            body = verified_body(w, row)
            lines.extend([body, ""])
            used.append(f"{ref} → {answer_ref} ({row['answer_path']})")
            problem = limit_issue(q["limit"], body)
            if problem:
                issues.append(f"{ref}: {problem}")
        elif state == "not_applicable":
            lines.extend([f"[NOT APPLICABLE — {q['field_state_reason']}]", ""])
            resolved.append(f"{ref} not applicable: {q['field_state_reason']}")
        elif state == "skipped" and q["required"] == "no":
            lines.extend([f"[LEFT BLANK — {q['field_state_reason']}]", ""])
            resolved.append(f"{ref} skipped (optional): {q['field_state_reason']}")
        else:
            lines.extend(["[ANSWER NEEDED]", ""])
            needed = {"yes": "required answer missing", "no": "optional answer not supplied",
                      "unknown": "answer missing; requirement not confirmed"}
            issue = needed.get(q["required"], "answer missing; requirement not confirmed")
            if state == "skipped":
                issue = f"marked skipped but requirement is {q['required']}"
            issues.append(f"{ref}: {issue}")
    lines.extend(["## Checks and unresolved items", ""])
    lines += [f"- {issue}" for issue in issues] or ["- No indexed-question gaps or parseable limit violations."]
    lines.extend(["", "## Not applicable or intentionally skipped", ""])
    lines += [f"- {item}" for item in resolved] or ["- None"]
    lines.extend(["", "Ready means the recorded structural checks passed. Still review answer fit, current facts, "
                  "attachments, branching conditions and the live form before filling or submitting.",
                  "", "## Answer versions used", ""])
    lines += [f"- {item}" for item in used] or ["- None"]
    lines.extend(["", "Prepared does not mean filled, submitted, or accepted.", ""])
    output_dir = w / "S Submit" / args.application
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / (DRAFT_NAME if issues else READY_NAME)
    result = "\n".join(lines).replace("Status: pending checks", "Status: ready" if not issues else "Status: incomplete", 1)
    current = [path for path in (output_dir / READY_NAME, output_dir / DRAFT_NAME) if path.exists()]
    if current == [output]:
        def without_prepared_date(value: str) -> str:
            return re.sub(r"^Prepared: .*?$", "Prepared: <date>", value, count=1, flags=re.M)
        if without_prepared_date(output.read_text(encoding="utf-8")) == without_prepared_date(result):
            print(f"Existing assembly unchanged: {output}; {'incomplete' if issues else 'ready'}")
            return
    previous = output_dir / "Previous"
    for path in current:  # Only one current file remains; earlier outputs move aside, never deleted.
        previous.mkdir(exist_ok=True)
        index = 1
        while any(previous.glob(f"{index:03d}-*")):
            index += 1
        path.rename(previous / f"{index:03d}-{path.name}")
    atomic_text(output, result)
    print(f"Assembled: {output}; {'incomplete' if issues else 'ready'}; issues={len(issues)}")


def validate(w: Path) -> None:
    workspace_funnel(w)
    questions = read_rows(qpath(w), Q_FIELDS)
    answers = read_rows(apath(w), A_FIELDS)
    links = read_rows(rpath(w), R_FIELDS)
    history = read_rows(hpath(w), H_FIELDS)
    history_links = read_rows(hlpath(w), HL_FIELDS)
    errors = []
    warnings = []
    for field, rows in (("question_ref", questions), ("answer_ref", answers)):
        values = [r[field] for r in rows]
        if len(values) != len(set(values)):
            errors.append(f"Duplicate {field}")
    qrefs = {r["question_ref"] for r in questions}
    for q in questions:
        if not inside(w, q["application_path"]).is_file():
            errors.append(f"Missing application for {q['question_ref']}")
        if q["field_state"] and q["field_state"] not in FIELD_STATES:
            errors.append(f"Unknown field state for {q['question_ref']}: {q['field_state']}")
        if q["field_state"] and not q["field_state_reason"]:
            errors.append(f"Field state lacks a reason: {q['question_ref']}")
        if q["field_state"] == "skipped" and q["required"] != "no":
            errors.append(f"Skipped field is not known optional: {q['question_ref']}")
    groups = {}
    for q in questions:
        if q["related_group"]:
            groups.setdefault(q["related_group"], set()).add(q["application_path"] + ":" + q["source_order"])
        for answer_ref in filter(None, q["answer_refs"].split(";")):
            if answer_ref not in {a["answer_ref"] for a in answers}:
                errors.append(f"Unknown answer link for {q['question_ref']}")
    errors.extend(f"Singleton named group: {name}" for name, items in groups.items() if len(items) < 2)
    preferred = {}
    answer_by_id = {a["answer_ref"]: a for a in answers}
    question_by_id = {q["question_ref"]: q for q in questions}
    for link in links:
        question = question_by_id.get(link["question_ref"])
        answer = answer_by_id.get(link["answer_ref"])
        if question is None or answer is None:
            errors.append("Reuse link points to an unknown question or answer")
        elif (link["question_ref"] not in answer["question_refs"].split(";")
              or link["answer_ref"] not in question["answer_refs"].split(";")):
            errors.append("Reuse link and indexes disagree")
        elif answer["status"] != "approved":
            errors.append("Reuse link points to an unapproved answer")
        if link["fit"] != "direct" or not link["reason"]:
            errors.append("Reuse link needs direct fit and a reason")
    history_ids = {row["history_ref"] for row in history}
    if len(history_ids) != len(history):
        errors.append("Duplicate historical answer reference")
    for row in history:
        if not inside(w, row["source_path"]).is_file():
            errors.append(f"Missing historical source for {row['history_ref']}")
        if row["question_ref"] and row["question_ref"] not in question_by_id:
            errors.append(f"Unknown question for {row['history_ref']}")
    pairs = set()
    for link in history_links:
        if link["history_ref"] not in history_ids or link["question_ref"] not in qrefs:
            errors.append(f"Historical link points to an unknown reference: {link['history_ref']} -> {link['question_ref']}")
        if not link["reason"]:
            errors.append(f"Historical link lacks a reason: {link['history_ref']} -> {link['question_ref']}")
        pair = (link["history_ref"], link["question_ref"])
        if pair in pairs:
            errors.append(f"Duplicate historical link: {pair[0]} -> {pair[1]}")
        pairs.add(pair)
    for a in answers:
        path = inside(w, a["answer_path"])
        if not path.is_file():
            errors.append(f"Missing answer file for {a['answer_ref']}")
        elif a["status"] == "approved":
            if not a["approved_sha256"]:
                warnings.append(f"{a['answer_ref']} was approved before 0.1.13 and has no approval digest; "
                                "reconfirm-approval is required before assembly or reuse")
            elif answer_digest(answer_body(path)) != a["approved_sha256"]:
                errors.append(f"Approved wording changed after approval: {a['answer_ref']}")
        if any(ref not in qrefs for ref in a["question_refs"].split(";") if ref):
            errors.append(f"Unknown question link for {a['answer_ref']}")
        if a["status"] == "approved" and not a["approved_at"]:
            errors.append(f"Approved answer lacks approval date: {a['answer_ref']}")
        if a["preferred"] == "yes":
            base = a["answer_ref"].split("-v")[0]
            preferred[base] = preferred.get(base, 0) + 1
            if a["status"] != "approved":
                errors.append(f"Preferred answer is not approved: {a['answer_ref']}")
    errors.extend(f"Multiple preferred versions for {base}" for base, count in preferred.items() if count > 1)
    for warning in warnings:
        print(f"Warning: {warning}")
    if errors:
        raise ValueError("Validation failed:\n- " + "\n- ".join(errors))
    print(f"Valid: {len(questions)} questions, {len(answers)} answer versions"
          + (f"; {len(warnings)} warning(s)" if warnings else ""))


def plan_input(plan: Path, value: str, label: str) -> Path | None:
    if not value.strip():
        return None
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = plan.parent / candidate
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} must be an existing regular file: {value}")
    return candidate.resolve()


def read_plan(plan: Path) -> list[dict[str, str]]:
    """Read a run plan; a 0.1.12 plan without source_mode is treated as unverified (unknown)."""
    header = csv_header(plan)
    if header == LEGACY_PLAN_FIELDS:
        return [dict(row, source_mode="unknown") for row in read_rows(plan, LEGACY_PLAN_FIELDS)]
    return read_rows(plan, PLAN_FIELDS)


def load_run_plan(w: Path, plan: Path) -> list[dict]:
    """Preflight the complete batch before changing any workspace files."""
    if plan.is_symlink() or not plan.is_file():
        raise ValueError(f"Run plan not found as a regular CSV file: {plan}")
    if legacy_schema(w):
        raise ValueError("This workspace uses the 0.1.12 schema; run `aqua.py migrate --workspace <folder>` first")
    selected = workspace_funnel(w)
    entries = []
    seen = set()
    existing_questions = read_rows(qpath(w), Q_FIELDS) if qpath(w).exists() else []
    for number, row in enumerate(read_plan(plan), start=2):
        entity, program, funnel = (row[name].strip() for name in ("entity", "program", "funnel"))
        if not entity or not program or funnel not in FUNNELS:
            raise ValueError(f"Run plan row {number}: entity, program, and a valid funnel are required")
        if funnel != selected:
            raise ValueError(f"Run plan row {number}: {funnel} belongs in its own workspace; this one is {selected}")
        mode = row["source_mode"].strip().lower() or "unknown"
        if mode not in SOURCE_MODES:
            raise ValueError(f"Run plan row {number}: source_mode must be blank, completed, or unknown")
        key = slug(entity + "-" + program)
        if key in seen:
            raise ValueError(f"Run plan row {number}: duplicate application key {key}")
        seen.add(key)
        source = plan_input(plan, row["source_file"], f"Row {number} source_file")
        if not source and not row["source_url"].strip():
            raise ValueError(f"Run plan row {number}: source_file or source_url is required")
        questions_file = plan_input(plan, row["questions_csv"], f"Row {number} questions_csv")
        history_file = plan_input(plan, row["history_csv"], f"Row {number} history_csv")
        map_file = plan_input(plan, row["answer_map_csv"], f"Row {number} answer_map_csv")
        if mode == "completed" and map_file:
            raise ValueError(f"Run plan row {number}: a completed historical record cannot be assembled; "
                             "remove answer_map_csv and use a current blank form")
        questions = read_rows(questions_file, QUESTION_INPUT_FIELDS) if questions_file else []
        history = read_rows(history_file, HISTORY_RUN_FIELDS) if history_file else []
        if history and not source:
            raise ValueError(f"Run plan row {number}: history_csv needs an archived source_file")
        for answer in history:
            if (not answer["source_question"].strip() or not answer["answer_text"].strip()
                    or answer["kind"].strip() not in ("general", "custom", "unknown")):
                raise ValueError(f"Run plan row {number}: historical answers need a question, answer, and valid kind")
        used_orders = set()
        for question in questions:
            order = question["order"].strip()
            if not order.isdigit() or int(order) < 1 or int(order) in used_orders or not question["question"].strip():
                raise ValueError(f"Run plan row {number}: questions need unique positive orders and text")
            if question["required"].strip().lower() not in ("yes", "no", "unknown"):
                raise ValueError(f"Run plan row {number}: required must be yes, no, or unknown")
            used_orders.add(int(order))
        application_path = f"A Applications/{key}/Application.md"
        for indexed in existing_questions:
            if indexed["application_path"] != application_path:
                continue
            for question in questions:
                if indexed["source_order"] != str(int(question["order"])):
                    continue
                if indexed["original_question"] != question["question"].strip():
                    raise ValueError(f"Run plan row {number}: question order {question['order']} conflicts with the existing index")
                supplied = {"required": question["required"].strip().lower(), "options": question["options"].strip(),
                            "limit": question["limit"].strip(), "source_ref": question["source_ref"].strip()}
                differs = [name for name, value in supplied.items() if value != indexed[name]]
                if differs:
                    raise ValueError(f"Run plan row {number}: question order {question['order']} has different "
                                     f"{', '.join(differs)} than {indexed['question_ref']}; use update-question")
        record = app_dir(w, key) / "Application.md"
        if record.exists():
            content = record.read_text(encoding="utf-8")
            expected = {"Entity": entity, "Program": program, "Funnel": funnel,
                        "Source URL": row["source_url"].strip() or "Unknown"}
            if any(f"{label}: {value}\n" not in content for label, value in expected.items()):
                raise ValueError(f"Run plan row {number}: existing Application.md metadata differs; inspect before continuing")
            recorded = source_mode(record)
            if "unknown" not in (recorded, mode) and recorded != mode:
                raise ValueError(f"Run plan row {number}: source_mode {mode} conflicts with recorded {recorded}")
        mappings = read_rows(map_file, ANSWER_MAP_FIELDS) if map_file else []
        refs = [item["question_ref"].strip() for item in mappings]
        if any(not ref or not item["answer_ref"].strip() for ref, item in zip(refs, mappings)) or len(refs) != len(set(refs)):
            raise ValueError(f"Run plan row {number}: answer map needs unique question refs and nonempty answer refs")
        entries.append(dict(key=key, entity=entity, program=program, funnel=funnel, mode=mode,
                            source=source, source_url=row["source_url"].strip(),
                            questions=questions, history=history, mappings=mappings))
    if not entries:
        raise ValueError("Run plan has no applications; add a row to Run-Plan.csv")
    return entries


def update_run_progress(w: Path, statuses: list[dict]) -> None:
    path = w / "PROGRESS.md"
    content = path.read_text(encoding="utf-8")
    start = "<!-- AQUA RUN STATUS START -->"
    end = "<!-- AQUA RUN STATUS END -->"
    if (start in content) != (end in content):
        raise ValueError("PROGRESS.md has an incomplete run-status marker; inspect before rerunning")
    content = content.replace("## Work needed\n\nNone identified yet.",
                              "## Manual work needed (outside run plan)\n\nNone recorded yet.", 1)
    content = content.replace("## Current batch\n\nNo applications started.",
                              "## Current batch\n\nSee the run-plan current batch above.", 1)
    content = content.replace("## Next action\n\nAdd an applicant context and the first application source.",
                              "## Next action\n\nSee the run-plan next actions above.", 1)
    needs = [f"- **{row['application_key']}**: {row['work_needed']}" for row in statuses
             if row["work_needed"]]
    block = (f"{start}\n## Run plan: current batch\n\n" +
             "\n".join(f"- {row['application_key']}" for row in statuses) +
             "\n\n## Run plan: work needed\n\n" +
             ("\n".join(needs) if needs else "No run-plan work identified.") +
             "\n\n## Run plan: next actions\n\n" +
             "\n".join(f"- **{row['application_key']}**: {row['next_action']}" for row in statuses) +
             f"\n{end}\n\n")
    if start in content:
        first = content.index(start)
        last = content.index(end, first) + len(end)
        content = content[:first] + block.rstrip() + content[last:]
    else:
        heading = "# AQUA progress\n\n"
        if not content.startswith(heading):
            raise ValueError("PROGRESS.md heading differs; inspect before adding run status")
        content = heading + block + content[len(heading):]
    atomic_text(path, content)


def run_plan(w: Path, args: argparse.Namespace) -> None:
    plan = Path(args.plan).expanduser().resolve() if args.plan else w / "Run-Plan.csv"
    entries = load_run_plan(w, plan)
    print(f"Run plan valid: {len(entries)} application(s)")
    if args.dry_run:
        print("Dry run: no workspace files changed")
        return
    init(w)
    statuses = []
    for entry in entries:
        key = entry["key"]
        status = dict(application_key=key, entity=entry["entity"], program=entry["program"],
                      historical_candidates="0", A="pending", QU="waiting_for_A",
                      Answers="waiting_for_QU", S="waiting_for_answers",
                      work_needed="", next_action="")
        needs = []
        try:
            add_application(w, argparse.Namespace(entity=entry["entity"], title=entry["program"],
                                                   funnel=entry["funnel"], source_url=entry["source_url"],
                                                   source_mode=entry["mode"]))
            record = app_dir(w, key) / "Application.md"
            mode = source_mode(record)
            if entry["source"]:
                add_source(w, argparse.Namespace(application=key, file=str(entry["source"])))
            for question in entry["questions"]:
                required = question["required"].strip().lower()
                add_question(w, argparse.Namespace(application=key, order=int(question["order"]),
                    text=question["question"].strip(), text_file=None,
                    options=question["options"].strip(), source_ref=question["source_ref"].strip(),
                    required=required == "yes", optional=required == "no", unknown=required == "unknown",
                    limit=question["limit"].strip()))
            if entry["history"]:
                digest = hashlib.sha256(entry["source"].read_bytes()).hexdigest()
                archived = next((item for item in (app_dir(w, key) / "Sources").iterdir()
                                 if item.is_file() and hashlib.sha256(item.read_bytes()).hexdigest() == digest), None)
                if archived is None:
                    raise ValueError("Historical source was not archived")
                incoming = [dict(application=entry["program"], source_path=str(archived.relative_to(w)),
                                 source_question=item["source_question"].strip(),
                                 answer_text=item["answer_text"].strip(),
                                 source_date=item["source_date"].strip(), kind=item["kind"].strip(),
                                 theme=item["theme"].strip(), question_ref=item["question_ref"].strip())
                            for item in entry["history"]]
                catalog_history_rows(w, incoming)
            status["historical_candidates"] = str(sum(
                1 for row in read_rows(hpath(w), H_FIELDS)
                if row["source_path"].startswith(f"A Applications/{key}/Sources/")))
            rel = f"A Applications/{key}/Application.md"
            indexed = [row for row in read_rows(qpath(w), Q_FIELDS) if row["application_path"] == rel]
            if not entry["source"]:
                needs.append("Capture and archive the URL source")
            if not indexed:
                needs.append("Extract ordered questions into a questions CSV")
            if needs:
                status["next_action"] = needs[0]
            else:
                status["A"] = "ready"
                unclassified = [row for row in indexed if not row["asking_summary"] or not row["general_or_custom"]]
                if unclassified:
                    status["QU"] = "review_needed"
                    needs.append(f"Interpret and classify {len(unclassified)} question(s) in QU")
                    status["next_action"] = "Review questions; use update-question and group-questions where justified"
                elif mode == "completed":
                    status["QU"] = "ready"
                    count = int(status["historical_candidates"])
                    status["Answers"] = "review_needed" if count else "not_applicable"
                    status["S"] = "historical_record"
                    if count:
                        needs.append(f"Review {count} historical answer candidate(s) from this completed record")
                    status["next_action"] = "Use this completed record as evidence; prepare drafts only for a current blank form"
                else:
                    status["QU"] = "ready"
                    mappings = {item["question_ref"].strip(): item["answer_ref"].strip() for item in entry["mappings"]}
                    indexed_refs = {row["question_ref"] for row in indexed}
                    if any(ref not in indexed_refs for ref in mappings):
                        raise ValueError("Answer map contains a question outside this application")
                    answers = {row["answer_ref"]: row for row in read_rows(apath(w), A_FIELDS)}
                    missing = [row["question_ref"] for row in indexed
                               if row["question_ref"] not in mappings and not row["field_state"]]
                    invalid = [ref for ref, answer_ref in mappings.items()
                               if answer_ref not in answers or answers[answer_ref]["status"] != "approved"
                               or ref not in answers[answer_ref]["question_refs"].split(";")]
                    if missing or invalid:
                        status["Answers"] = "review_needed"
                        count = int(status["historical_candidates"])
                        if count:
                            needs.append(f"Review {count} historical answer candidate(s); select approved linked answers for {len(missing) + len(invalid)} question(s)")
                        else:
                            needs.append(f"Select approved linked answers for {len(missing) + len(invalid)} question(s)")
                        status["next_action"] = "Review historical wording or draft, confirm fit and approval, then update answer_map_csv"
                    elif mode != "blank":
                        status["Answers"] = "ready"
                        status["S"] = "source_mode_unverified"
                        needs.append("Verify the source is a current blank form, then set source_mode to blank")
                        status["next_action"] = "Inspect the source; set source_mode (blank or completed) in Run-Plan.csv and rerun"
                    else:
                        status["Answers"] = "ready"
                        assemble(w, argparse.Namespace(application=key,
                            map=[f"{ref}={answer_ref}" for ref, answer_ref in mappings.items()]))
                        status["S"] = "draft_ready" if (w / "S Submit" / key / READY_NAME).exists() else "checks_needed"
                        if status["S"] == "checks_needed":
                            needs.append("Resolve draft checks and limits")
                        status["next_action"] = "Review draft and live form; fill or submit only on user instruction"
            status["work_needed"] = "; ".join(needs)
        except (OSError, ValueError) as exc:
            status["work_needed"] = f"Exception: {exc}"
            status["next_action"] = "Correct the plan or workspace conflict, then rerun"
            status["S"] = "exception"
        statuses.append(status)
        write_rows(w / "Run-Status.csv", RUN_STATUS_FIELDS, statuses)
        update_run_progress(w, statuses)
    if any(row["S"] == "exception" for row in statuses):
        raise ValueError("One or more applications need repair; inspect Run-Status.csv and PROGRESS.md")
    try:
        validate(w)
    except ValueError as exc:
        statuses[-1]["S"] = "exception"
        statuses[-1]["work_needed"] = f"Workspace validation: {exc}"
        statuses[-1]["next_action"] = "Repair the referenced index or file, then rerun"
        write_rows(w / "Run-Status.csv", RUN_STATUS_FIELDS, statuses)
        update_run_progress(w, statuses)
        raise
    review_sheet(w)
    print(f"Run complete: {w / 'Run-Status.csv'}; no answers approved or forms submitted")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AQUA personal workspace file helper")
    sub = p.add_subparsers(dest="command", required=True)
    def cmd(name: str, help_text: str) -> argparse.ArgumentParser:
        item = sub.add_parser(name, help=help_text)
        item.add_argument("--workspace", required=True, help="AQUA workspace path")
        return item
    def requirement_flags(item: argparse.ArgumentParser) -> None:
        group = item.add_mutually_exclusive_group()
        group.add_argument("--required", action="store_true")
        group.add_argument("--optional", action="store_true")
        group.add_argument("--unknown", action="store_true", help="Requirement not established by the source")
    setup = cmd("init", "Create or resume one funnel's four-folder workspace")
    setup.add_argument("--funnel", choices=sorted(FUNNELS), help="Required for a new workspace unless its folder name is the funnel")
    cmd("migrate", "Upgrade a 0.1.12 workspace's indexes after backing them up")
    cmd("review-sheet", "Refresh the generated Questions-and-Answers-View.csv")
    run = cmd("run", "Resume a CSV run plan through safe AQUA phase gates")
    run.add_argument("--plan", help="Run-Plan.csv path; defaults to the workspace copy")
    run.add_argument("--dry-run", action="store_true", help="Validate the plan without changing the workspace")
    a = cmd("add-application", "Create an application record")
    a.add_argument("--entity", required=True); a.add_argument("--title", required=True)
    a.add_argument("--funnel", required=True, choices=sorted(FUNNELS)); a.add_argument("--source-url")
    a.add_argument("--source-mode", choices=SOURCE_MODES,
                   help="blank (current unanswered form), completed (submitted/historical record) or unknown")
    s = cmd("add-source", "Archive a local source file, deduplicated by hash")
    s.add_argument("--application", required=True); s.add_argument("--file", required=True)
    q = cmd("add-question", "Index exact source wording")
    q.add_argument("--application", required=True); q.add_argument("--order", required=True, type=int)
    t = q.add_mutually_exclusive_group(required=True); t.add_argument("--text"); t.add_argument("--text-file")
    q.add_argument("--source-ref"); q.add_argument("--options")
    requirement_flags(q)
    q.add_argument("--limit")
    u = cmd("update-question", "Add interpretation or correct metadata without changing original wording")
    u.add_argument("--question", required=True); u.add_argument("--summary")
    u.add_argument("--kind", choices=["general", "custom"]); u.add_argument("--topic"); u.add_argument("--group")
    requirement_flags(u)
    u.add_argument("--limit", help="words:N or chars:N; pass an empty value to clear")
    u.add_argument("--options", help="Visible options; pass an empty value to clear")
    mq = cmd("mark-question", "Mark a field not applicable or deliberately skipped, with a reason")
    state = mq.add_mutually_exclusive_group(required=True)
    state.add_argument("--not-applicable", action="store_true", help="Field does not apply, e.g. hidden by an observed branch")
    state.add_argument("--skipped", action="store_true", help="Known optional field deliberately left blank")
    state.add_argument("--clear", action="store_true", help="Return the field to open")
    mq.add_argument("--question", required=True); mq.add_argument("--reason")
    g = cmd("group-questions", "Group at least two compatible source occurrences")
    g.add_argument("--group", required=True); g.add_argument("--questions", required=True, help="comma-separated refs")
    d = cmd("save-answer", "Save a new draft version")
    d.add_argument("--title", required=True); d.add_argument("--text-file", required=True); d.add_argument("--questions", required=True)
    d.add_argument("--answers-what"); d.add_argument("--sources"); d.add_argument("--context"); d.add_argument("--facts-as-of"); d.add_argument("--note")
    v = cmd("approve-answer", "Record actual user approval")
    v.add_argument("--answer", required=True); v.add_argument("--evidence", required=True); v.add_argument("--preferred", action="store_true")
    rc = cmd("reconfirm-approval", "Record a digest for a pre-0.1.13 approval after the applicant reconfirms it")
    rc.add_argument("--answer", required=True); rc.add_argument("--evidence", required=True)
    l = cmd("link-answer", "Link a later question to an unchanged approved answer")
    l.add_argument("--answer", required=True); l.add_argument("--question", required=True)
    l.add_argument("--reason", required=True, help="Why this answer directly covers the later question")
    h = cmd("import-history", "Catalog historical answers without approving them")
    h.add_argument("--input-csv", required=True, help="CSV with the historical import columns")
    hl = cmd("link-history", "Mark a historical answer as a candidate for a question (never approval)")
    hl.add_argument("--history", required=True); hl.add_argument("--question", required=True)
    hl.add_argument("--reason", required=True, help="Why the historical answer may fit this question")
    m = cmd("assemble", "Build ordered Markdown application from approved versions")
    m.add_argument("--application", required=True); m.add_argument("--map", action="append", help="question_ref=answer_ref; repeat")
    cmd("validate", "Check index identities, links, files, approval state")
    b = cmd("report-issue", "Save beta feedback in the workspace; send metadata if opted in")
    b.add_argument("--detail", required=True, help="Description kept locally, never sent automatically")
    c = cmd("beta-reporting", "Persist beta report delivery choice in the workspace")
    state = c.add_mutually_exclusive_group(required=True)
    state.add_argument("--enable", action="store_true")
    state.add_argument("--disable", action="store_true")
    c.add_argument("--endpoint", help="Publisher-controlled HTTPS report receiver, required with --enable")
    return p


def main() -> int:
    args = parser().parse_args()
    w = root(args.workspace)
    try:
        if args.command == "beta-reporting":
            if not (w / "START-HERE.md").exists():
                raise ValueError("Initialize this AQUA workspace first")
            if args.enable and not args.endpoint:
                raise ValueError("--endpoint is required with --enable")
            if args.disable and args.endpoint:
                raise ValueError("Do not pass --endpoint with --disable")
            configure_beta(w, args.enable, args.endpoint or "")
            print("Beta delivery enabled" if args.enable else "Beta delivery disabled; local reports remain available")
            return 0
        if args.command == "report-issue":
            if not (w / "START-HERE.md").exists():
                raise ValueError("Initialize this AQUA workspace first")
            report_id, delivery = record_beta(w, args.command, "feedback", args.detail)
            print(f"Beta report saved: {report_id} ({delivery})")
            return 0
        actions = {"init": init, "review-sheet": review_sheet, "migrate": migrate,
                   "add-application": add_application, "add-source": add_source,
                   "run": run_plan,
                   "add-question": add_question, "update-question": update_question,
                   "mark-question": mark_question, "group-questions": group_questions,
                   "save-answer": save_answer, "approve-answer": approve_answer,
                   "reconfirm-approval": reconfirm_approval, "link-answer": link_answer,
                   "import-history": import_history, "link-history": link_history,
                   "assemble": assemble, "validate": validate}
        if args.command not in ("init", "run") and not (w / "START-HERE.md").exists():
            raise ValueError("Initialize this AQUA workspace first")
        if args.command == "init":
            init(w, args)
        elif args.command in ("validate", "review-sheet", "migrate"):
            actions[args.command](w)
        else:
            actions[args.command](w, args)
        return 0
    except (OSError, ValueError) as exc:
        print(f"AQUA error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        report_id, delivery = record_beta(w, args.command, "unexpected_error", str(exc), exc)
        print(f"AQUA unexpected error; beta report {report_id} ({delivery})", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

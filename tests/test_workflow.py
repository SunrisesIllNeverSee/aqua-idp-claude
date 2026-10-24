"""End-to-end file workflow checks using synthetic applicant material."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/run-aqua/scripts/aqua.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
import beta


class AquaWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "AQUA" / "Tech"

    def run_cli(self, command, *args, expected=0, env=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), command, "--workspace", str(self.workspace), *args],
            capture_output=True, text=True, env=dict(env or os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def rows(self, relative):
        with (self.workspace / relative).open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    def write_csv(self, path, fields, rows):
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_run_plan_resumes_at_human_gates_and_preserves_notes(self):
        self.run_cli("init")
        source = self.base / "cohort.md"
        source.write_text("What do you build?\nWho uses it?\n", encoding="utf-8")
        questions = self.workspace / "cohort-questions.csv"
        self.write_csv(questions, ["order", "question", "options", "required", "limit", "source_ref"], [
            dict(order="1", question="What do you build?", options="", required="yes", limit="words:50", source_ref="cohort.md"),
            dict(order="2", question="Who uses it?", options="", required="yes", limit="words:50", source_ref="cohort.md"),
        ])
        history = self.workspace / "cohort-history.csv"
        self.write_csv(history, ["source_question", "answer_text", "source_date", "kind", "theme", "question_ref"], [
            dict(source_question="What do you build?", answer_text="We help farmers plan irrigation.",
                 source_date="2026-05-01", kind="custom", theme="Product", question_ref="q001")])
        plan = self.workspace / "Run-Plan.csv"
        fields = ["entity", "program", "funnel", "source_file", "source_url", "questions_csv", "history_csv", "answer_map_csv", "source_mode"]
        row = dict(entity="Northstar", program="Cohort", funnel="Tech", source_file=str(source),
                   source_url="", questions_csv=questions.name, history_csv=history.name, answer_map_csv="",
                   source_mode="blank")
        self.write_csv(plan, fields, [row])
        progress = self.workspace / "PROGRESS.md"
        progress.write_text(progress.read_text(encoding="utf-8") + "\nPersonal note: verify deadline.\n", encoding="utf-8")
        self.run_cli("run", "--dry-run")
        self.assertFalse((self.workspace / "Run-Status.csv").exists())
        self.run_cli("run")
        self.run_cli("run")
        self.assertEqual(len(self.rows("QU Questions/Question-Index.csv")), 2)
        self.assertEqual(len(self.rows("A Answers/Historical-Answer-Catalog.csv")), 1)
        status = self.rows("Run-Status.csv")[0]
        self.assertEqual((status["A"], status["QU"]), ("ready", "review_needed"))
        self.assertEqual(status["historical_candidates"], "1")
        self.assertEqual(status["Answers"], "waiting_for_QU")
        self.assertIn("Personal note: verify deadline.", progress.read_text(encoding="utf-8"))
        self.assertNotIn("No applications started.", progress.read_text(encoding="utf-8"))
        self.assertIn("## Run plan: current batch", progress.read_text(encoding="utf-8"))
        self.run_cli("update-question", "--question", "q001", "--summary", "Product", "--kind", "custom")
        self.run_cli("update-question", "--question", "q002", "--summary", "Users", "--kind", "custom")
        self.run_cli("run")
        self.assertEqual(self.rows("Run-Status.csv")[0]["Answers"], "review_needed")
        self.assertIn("historical answer", self.rows("Run-Status.csv")[0]["work_needed"])
        answer = self.base / "answer.txt"
        answer.write_text("We build planning software for farmers.", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Product", "--text-file", str(answer), "--questions", "q001")
        self.run_cli("approve-answer", "--answer", "a001-v001", "--evidence", "Applicant approved")
        self.run_cli("link-answer", "--answer", "a001-v001", "--question", "q002", "--reason", "Directly identifies users")
        mapping = self.workspace / "cohort-map.csv"
        self.write_csv(mapping, ["question_ref", "answer_ref"], [
            dict(question_ref="q001", answer_ref="a001-v001"),
            dict(question_ref="q002", answer_ref="a001-v001"),
        ])
        row["answer_map_csv"] = mapping.name
        self.write_csv(plan, fields, [row])
        self.run_cli("run")
        status = self.rows("Run-Status.csv")[0]
        self.assertEqual((status["A"], status["QU"], status["Answers"], status["S"]),
                         ("ready", "ready", "ready", "draft_ready"))
        draft_dir = self.workspace / "S Submit/northstar-cohort"
        self.run_cli("run")
        self.assertEqual(len(list(draft_dir.glob("*.md"))), 1)
        self.assertIn("Personal note: verify deadline.", progress.read_text(encoding="utf-8"))
        self.assertNotIn("submit", status["S"])

    def test_run_plan_preflight_rejects_bad_question_without_changes(self):
        self.run_cli("init")
        source = self.base / "source.md"
        source.write_text("Question", encoding="utf-8")
        questions = self.workspace / "questions.csv"
        self.write_csv(questions, ["order", "question", "options", "required", "limit", "source_ref"], [
            dict(order="1", question="Question", options="", required="maybe", limit="", source_ref="")])
        self.write_csv(self.workspace / "Run-Plan.csv",
            ["entity", "program", "funnel", "source_file", "source_url", "questions_csv", "history_csv", "answer_map_csv"],
            [dict(entity="Example", program="Grant", funnel="Tech", source_file=str(source),
                  source_url="", questions_csv=questions.name, history_csv="", answer_map_csv="")])
        self.run_cli("run", expected=2)
        self.assertFalse((self.workspace / "A Applications/example-grant").exists())
        self.assertFalse((self.workspace / "Run-Status.csv").exists())

    def test_batch_preserves_source_and_reuses_approved_answer(self):
        self.run_cli("init")
        self.run_cli("init")
        source = self.base / "application.txt"
        source.write_text("Tell us what you build.\n", encoding="utf-8")
        for title in ("Spring Cohort", "Fall Cohort"):
            self.run_cli("add-application", "--entity", "Northstar", "--title", title,
                         "--funnel", "Tech", "--source-mode", "blank")
        self.run_cli("add-source", "--application", "northstar-spring-cohort", "--file", str(source))
        self.run_cli("add-source", "--application", "northstar-spring-cohort", "--file", str(source))
        sources = list((self.workspace / "A Applications/northstar-spring-cohort/Sources").iterdir())
        self.assertEqual(len(sources), 1)
        self.run_cli("add-question", "--application", "northstar-spring-cohort", "--order", "1",
                     "--text", "What are you building?", "--required", "--limit", "words:50")
        text = self.base / "answer.txt"
        text.write_text("We help growers plan irrigation using field observations.", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Product purpose", "--text-file", str(text),
                     "--questions", "q001", "--sources", "Applicant interview")
        self.run_cli("assemble", "--application", "northstar-spring-cohort", "--map", "q001=a001-v001", expected=2)
        self.run_cli("approve-answer", "--answer", "a001-v001", "--evidence", "Applicant approved in test chat", "--preferred")
        self.run_cli("assemble", "--application", "northstar-spring-cohort", "--map", "q001=a001-v001")
        approved_file = self.workspace / "A Answers/product-purpose/v001.md"
        approved_before = approved_file.read_bytes()
        self.run_cli("add-question", "--application", "northstar-fall-cohort", "--order", "1",
                     "--text", "Describe your product.", "--required")
        self.run_cli("add-question", "--application", "northstar-fall-cohort", "--order", "1",
                     "--text", "Describe your product.", "--required")
        self.assertEqual(len(self.rows("QU Questions/Question-Index.csv")), 2)
        self.run_cli("group-questions", "--group", "Product purpose", "--questions", "q001,q002")
        self.run_cli("assemble", "--application", "northstar-fall-cohort", "--map", "q002=a001-v001", expected=2)
        self.run_cli("link-answer", "--answer", "a001-v001", "--question", "q002",
                     "--reason", "Same requested product purpose and users")
        self.assertEqual(approved_file.read_bytes(), approved_before)
        self.run_cli("assemble", "--application", "northstar-fall-cohort", "--map", "q002=a001-v001")
        self.run_cli("assemble", "--application", "northstar-fall-cohort", "--map", "q002=a001-v001")
        ready_dir = self.workspace / "S Submit/northstar-fall-cohort"
        self.assertEqual(len(list(ready_dir.glob("*.md"))), 1)
        ready = (ready_dir / "Application-ready.md").read_text(encoding="utf-8")
        self.assertIn("Status: ready", ready)
        self.assertIn("We help growers plan irrigation", ready)
        self.assertEqual(len(self.rows("A Answers/Reuse-Links.csv")), 1)
        self.run_cli("validate")

    def test_beta_feedback_stays_local_without_opt_in(self):
        self.run_cli("init")
        private_detail = "Question q001 contains confidential applicant details"
        output = self.run_cli("report-issue", "--detail", private_detail)
        self.assertIn("local_only", output)
        report = next((self.workspace / "Beta Reports").glob("*.json"))
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["detail"], private_detail)
        self.assertEqual(data["delivery"], "local_only")
        env = dict(os.environ, AQUA_BETA_REPORTING="1", AQUA_BETA_REPORT_URL="http://example.com/report")
        output = self.run_cli("report-issue", "--detail", private_detail, env=env)
        self.assertIn("no_valid_https_endpoint", output)

    def test_beta_delivery_excludes_local_detail(self):
        self.workspace.mkdir(parents=True)
        captured = {}

        def receive(request, timeout):
            captured.update(json.loads(request.data))
            class Response:
                status = 204
                def __enter__(self): return self
                def __exit__(self, *_): return None
            return Response()

        with patch.dict(os.environ, {"AQUA_BETA_REPORTING": "1",
                                     "AQUA_BETA_REPORT_URL": "https://reports.example.test/ingest"}), \
             patch.object(beta, "urlopen", side_effect=receive):
            _, delivery = beta.record(self.workspace, "report-issue", "feedback",
                                      "Private answer: never transmit this")
        self.assertEqual(delivery, "sent")
        self.assertEqual(captured["version"], beta.VERSION)
        self.assertEqual(captured["kind"], "feedback")
        self.assertNotIn("Private answer", json.dumps(captured))
        self.assertNotIn("detail", captured)
        self.assertNotIn("traceback", captured)

    def test_beta_timeout_keeps_local_report(self):
        self.workspace.mkdir(parents=True)
        with patch.dict(os.environ, {"AQUA_BETA_REPORTING": "1",
                                     "AQUA_BETA_REPORT_URL": "https://reports.example.test/ingest"}), \
             patch.object(beta, "urlopen", side_effect=TimeoutError("receiver timed out")):
            report_id, delivery = beta.record(self.workspace, "report-issue", "feedback",
                                              "A private local issue")
        self.assertEqual(delivery, "delivery_failed")
        report = self.workspace / "Beta Reports" / f"{report_id}.json"
        saved = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(saved["detail"], "A private local issue")
        self.assertEqual(saved["delivery"], "delivery_failed")

    def test_beta_choice_persists_and_can_be_disabled(self):
        self.run_cli("init")
        self.run_cli("beta-reporting", "--enable", "--endpoint", "http://invalid.test/report", expected=2)
        self.run_cli("beta-reporting", "--enable", "--endpoint", "https://reports.example.test/report")
        settings = json.loads((self.workspace / "Beta Reports/Settings.json").read_text(encoding="utf-8"))
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["endpoint"], "https://reports.example.test/report")
        self.run_cli("beta-reporting", "--disable")
        output = self.run_cli("report-issue", "--detail", "Grouping missed two questions")
        self.assertIn("local_only", output)

    def test_new_version_keeps_old_approval_and_missing_answer_is_incomplete(self):
        self.workspace = self.base / "AQUA" / "Grants Funding"
        self.run_cli("init")
        self.run_cli("add-application", "--entity", "Garden", "--title", "Grant", "--funnel", "Grants Funding",
                     "--source-mode", "blank")
        self.run_cli("add-question", "--application", "garden-grant", "--order", "1",
                     "--text", "What is your project?", "--required", "--limit", "words:2")
        self.run_cli("add-question", "--application", "garden-grant", "--order", "2",
                     "--text", "Anything else?")
        self.assertEqual(self.rows("QU Questions/Question-Index.csv")[1]["required"], "unknown")
        self.run_cli("assemble", "--application", "garden-grant")
        output = self.workspace / "S Submit/garden-grant/Application-draft.md"
        self.assertIn("Status: incomplete", output.read_text(encoding="utf-8"))
        self.assertIn("requirement not confirmed", output.read_text(encoding="utf-8"))
        text = self.base / "draft.txt"
        text.write_text("We will grow and share vegetables.", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Project", "--text-file", str(text), "--questions", "q001")
        self.run_cli("approve-answer", "--answer", "a001-v001", "--evidence", "User approved", "--preferred")
        self.run_cli("assemble", "--application", "garden-grant", "--map", "q001=a001-v001")
        self.assertIn("exceed", output.read_text(encoding="utf-8"))
        text.write_text("Community gardens.", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Project", "--text-file", str(text), "--questions", "q001")
        rows = self.rows("A Answers/Answer-Index.csv")
        self.assertEqual([(r["status"], r["preferred"]) for r in rows],
                         [("approved", "yes"), ("draft", "no")])
        self.run_cli("validate")

    def test_each_funnel_has_its_own_files_and_rejects_cross_funnel_input(self):
        self.run_cli("init")
        tech = self.workspace
        self.assertEqual((tech / "Funnel.txt").read_text(encoding="utf-8").strip(), "Tech")
        self.run_cli("add-application", "--entity", "Example", "--title", "Role",
                     "--funnel", "Jobs", expected=2)
        self.assertEqual(self.rows("QU Questions/Question-Index.csv"), [])
        for funnel in ("Grants Funding", "College", "Jobs"):
            self.workspace = self.base / "AQUA" / funnel
            self.run_cli("init", "--funnel", funnel)
            self.assertEqual((self.workspace / "Funnel.txt").read_text(encoding="utf-8").strip(), funnel)
            for relative in ("A Applications", "QU Questions/Question-Index.csv",
                             "A Answers/Answer-Index.csv", "S Submit"):
                self.assertTrue((self.workspace / relative).exists())
            self.assertEqual(self.rows("QU Questions/Question-Index.csv"), [])
        self.workspace = tech
        self.run_cli("add-application", "--entity", "Example", "--title", "Cohort", "--funnel", "Tech")
        self.run_cli("add-question", "--application", "example-cohort", "--order", "1", "--text", "What do you build?")
        self.workspace = self.base / "AQUA" / "Jobs"
        self.assertEqual(self.rows("QU Questions/Question-Index.csv"), [])
        self.assertEqual(self.rows("A Answers/Answer-Index.csv"), [])
        self.run_cli("init", "--funnel", "Tech", expected=2)

    def test_existing_one_funnel_flat_workspace_can_be_marked_without_moving_files(self):
        self.run_cli("init")
        self.run_cli("add-application", "--entity", "Example", "--title", "Cohort", "--funnel", "Tech")
        leaf = self.workspace
        flat = self.base / "Existing-Flat"
        import shutil
        shutil.copytree(leaf, flat)
        (flat / "Funnel.txt").unlink()
        self.workspace = flat
        self.run_cli("init", "--funnel", "Tech")
        self.assertEqual((flat / "Funnel.txt").read_text(encoding="utf-8").strip(), "Tech")
        self.assertTrue((flat / "A Applications/example-cohort/Application.md").exists())
        self.run_cli("add-application", "--entity", "Example", "--title", "Role", "--funnel", "Jobs", expected=2)
        self.run_cli("validate")

    def test_historical_import_preserves_context_without_approval(self):
        self.run_cli("init")
        self.run_cli("add-application", "--entity", "Example", "--title", "Archive", "--funnel", "Tech")
        original = self.base / "old.md"
        original.write_text("Question: Why now?\nAnswer: The timing fits our research.\n", encoding="utf-8")
        self.run_cli("add-source", "--application", "example-archive", "--file", str(original))
        archived = next((self.workspace / "A Applications/example-archive/Sources").glob("*.md"))
        import_csv = self.base / "history.csv"
        fields = ["application", "source_path", "source_question", "answer_text", "source_date", "kind", "theme", "question_ref"]
        with import_csv.open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerow(dict(application="Example Archive", source_path=str(archived.relative_to(self.workspace)),
                                 source_question="Why now?", answer_text="The timing fits our research.",
                                 source_date="2026-05", kind="custom", theme="Timing", question_ref=""))
        self.run_cli("import-history", "--input-csv", str(import_csv))
        self.run_cli("import-history", "--input-csv", str(import_csv))
        history = self.rows("A Answers/Historical-Answer-Catalog.csv")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "historical_unreviewed")
        self.assertEqual(self.rows("A Answers/Answer-Index.csv"), [])
        self.run_cli("validate")

    def test_blank_history_new_blank_share_one_review_view(self):
        self.run_cli("init")
        for entity, title in (("Northstar", "Blank"), ("Garden", "Past"), ("Future", "Blank")):
            self.run_cli("add-application", "--entity", entity, "--title", title, "--funnel", "Tech")
        self.run_cli("add-question", "--application", "northstar-blank", "--order", "1",
                     "--text", "Describe your product.", "--required")
        self.run_cli("add-question", "--application", "garden-past", "--order", "1",
                     "--text", "What do you make?", "--required")
        self.run_cli("add-question", "--application", "future-blank", "--order", "1",
                     "--text", "Describe your product.", "--required")
        old = self.base / "past.md"
        old.write_text("What do you make?\nWe build irrigation planning tools.\n", encoding="utf-8")
        self.run_cli("add-source", "--application", "garden-past", "--file", str(old))
        archived = next((self.workspace / "A Applications/garden-past/Sources").glob("*.md"))
        history = self.base / "history.csv"
        self.write_csv(history,
                       ["application", "source_path", "source_question", "answer_text", "source_date", "kind", "theme", "question_ref"],
                       [dict(application="Garden Past", source_path=str(archived.relative_to(self.workspace)),
                             source_question="What do you make?", answer_text="We build irrigation planning tools.",
                             source_date="2026-05-01", kind="custom", theme="Product", question_ref="q002")])
        self.run_cli("import-history", "--input-csv", str(history))
        self.run_cli("review-sheet")
        view = self.rows("Questions-and-Answers-View.csv")
        self.assertEqual(len(view), 3)
        self.assertEqual({row["question_ref"]: row["answer_status"] for row in view},
                         {"q001": "unanswered", "q002": "historical_unreviewed", "q003": "unanswered"})
        answer = self.base / "approved.txt"
        answer.write_text("We build irrigation planning tools.", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Product", "--text-file", str(answer),
                     "--questions", "q002", "--sources", "Garden Past")
        self.run_cli("review-sheet")
        self.assertIn("draft", [row["answer_status"] for row in self.rows("Questions-and-Answers-View.csv")])
        self.run_cli("approve-answer", "--answer", "a001-v001", "--evidence", "Synthetic test applicant approval")
        self.run_cli("link-answer", "--answer", "a001-v001", "--question", "q003",
                     "--reason", "Both ask for the same product description")
        self.run_cli("review-sheet")
        view = self.rows("Questions-and-Answers-View.csv")
        self.assertEqual([row["answer_status"] for row in view if row["question_ref"] == "q003"], ["approved"])
        self.assertEqual([row["answer_status"] for row in view if row["question_ref"] == "q001"], ["unanswered"])
        self.run_cli("review-sheet")
        self.assertEqual(self.rows("Questions-and-Answers-View.csv"), view)
        self.run_cli("validate")


    # --- 0.1.13 regression tests -------------------------------------------------

    def blank_app(self, entity="Northstar", title="Cohort", mode="blank"):
        args = ["--entity", entity, "--title", title, "--funnel", "Tech"]
        self.run_cli("add-application", *args, *(["--source-mode", mode] if mode else []))
        return f"{entity}-{title}".lower().replace(" ", "-")

    def approved(self, title, text, questions, evidence="Synthetic applicant approved this wording"):
        path = self.base / f"{title}.txt"
        path.write_text(text, encoding="utf-8")
        out = self.run_cli("save-answer", "--title", title, "--text-file", str(path), "--questions", questions)
        ref = out.split("Draft saved: ")[1].split(" ")[0]
        self.run_cli("approve-answer", "--answer", ref, "--evidence", evidence, "--preferred")
        return ref

    def test_approved_wording_is_digest_protected(self):
        self.run_cli("init")
        app = self.blank_app()
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "What do you build?", "--required")
        ref = self.approved("Product", "We build irrigation planning tools.", "q001")
        self.assertEqual(len(self.rows("A Answers/Answer-Index.csv")[0]["approved_sha256"]), 64)
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        approved = self.workspace / "A Answers/product/v001.md"
        original = approved.read_text(encoding="utf-8")
        # Bookkeeping-only whitespace differences do not count as a wording change.
        approved.write_text(original.replace("We build irrigation planning tools.", "We build irrigation planning tools.   \r\n"), encoding="utf-8")
        self.run_cli("validate")
        approved.write_text(original.replace("irrigation", "rocket"), encoding="utf-8")
        self.assertIn("changed after approval", self.run_cli("validate", expected=2))
        self.assertIn("changed after approval", self.run_cli("assemble", "--application", app, "--map", f"q001={ref}", expected=2))
        self.run_cli("add-question", "--application", app, "--order", "2", "--text", "Describe it.", "--required")
        self.assertIn("changed after approval", self.run_cli("link-answer", "--answer", ref, "--question", "q002",
                                                             "--reason", "same", expected=2))
        approved.write_text(original, encoding="utf-8")
        self.run_cli("validate")
        new_ref = self.approved("Product", "We build rocket planning tools.", "q001")
        self.assertEqual(new_ref, "a001-v002")
        self.assertEqual(approved.read_text(encoding="utf-8"), original)
        self.assertEqual([r["status"] for r in self.rows("A Answers/Answer-Index.csv")], ["approved", "approved"])

    def make_legacy(self):
        """Rewrite current indexes into the 0.1.12 layout to exercise migration."""
        for relative, drop in (("QU Questions/Question-Index.csv", ("field_state", "field_state_reason")),
                               ("A Answers/Answer-Index.csv", ("approved_sha256",))):
            rows = self.rows(relative)
            with (self.workspace / relative).open(newline="", encoding="utf-8") as stream:
                fields = [f for f in next(csv.reader(stream)) if f not in drop]
            self.write_csv(self.workspace / relative, fields, [{k: v for k, v in r.items() if k in fields} for r in rows])
        (self.workspace / "A Answers/Historical-Links.csv").unlink()

    def test_legacy_workspace_migrates_with_backup_and_reconfirmation(self):
        self.run_cli("init")
        app = self.blank_app()
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "What do you build?", "--required")
        ref = self.approved("Product", "We build irrigation planning tools.", "q001")
        self.make_legacy()
        before = (self.workspace / "QU Questions/Question-Index.csv").read_bytes()
        self.assertIn("0.1.12 schema", self.run_cli("validate", expected=2))
        self.assertIn("0.1.12 schema", self.run_cli("init", expected=2))
        out = self.run_cli("migrate")
        self.assertIn("Approved versions without an approval digest: 1", out)
        backups = list((self.workspace / ".aqua-migrations").glob("*/Question-Index.csv"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertIn("already current", self.run_cli("migrate"))
        self.assertEqual(self.rows("QU Questions/Question-Index.csv")[0]["original_question"], "What do you build?")
        self.assertIn("reconfirm-approval", self.run_cli("validate"))
        self.assertIn("no approval digest", self.run_cli("assemble", "--application", app, "--map", f"q001={ref}", expected=2))
        self.run_cli("reconfirm-approval", "--answer", ref, "--evidence", "", expected=2)
        self.run_cli("reconfirm-approval", "--answer", ref, "--evidence", "Applicant reconfirmed current wording")
        self.assertIn("Approval reconfirmed:", (self.workspace / "A Answers/product/v001.md").read_text(encoding="utf-8"))
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        self.assertTrue((self.workspace / f"S Submit/{app}/Application-ready.md").exists())
        self.assertIn("already current", self.run_cli("reconfirm-approval", "--answer", ref, "--evidence", "again"))

    def test_link_history_later_and_unlinked_rows_visible(self):
        self.run_cli("init")
        self.blank_app("Garden", "Past", mode="completed")
        app = self.blank_app("Future", "Blank")
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "Describe your product.", "--required", "--limit", "words:40")
        old = self.base / "past.md"
        old.write_text("What do you make?\nWe build irrigation planning tools.\n", encoding="utf-8")
        self.run_cli("add-source", "--application", "garden-past", "--file", str(old))
        archived = next((self.workspace / "A Applications/garden-past/Sources").glob("*.md"))
        fields = ["application", "source_path", "source_question", "answer_text", "source_date", "kind", "theme", "question_ref"]
        row = dict(application="Garden Past", source_path=str(archived.relative_to(self.workspace)),
                   source_question="What do you make?", answer_text="We build irrigation planning tools.",
                   source_date="2026-05-01", kind="custom", theme="Product", question_ref="")
        history = self.base / "history.csv"
        self.write_csv(history, fields, [row])
        self.run_cli("import-history", "--input-csv", str(history))
        self.run_cli("review-sheet")
        view = self.rows("Questions-and-Answers-View.csv")
        unlinked = [r for r in view if r["answer_status"] == "historical_unlinked"]
        self.assertEqual(len(unlinked), 1)
        self.assertEqual((unlinked[0]["answer_text"], unlinked[0]["facts_as_of"], unlinked[0]["application"]),
                         ("We build irrigation planning tools.", "2026-05-01", "garden-past"))
        question_row = next(r for r in view if r["question_ref"] == "q001")
        self.assertEqual((question_row["required"], question_row["limit"]), ("yes", "words:40"))
        self.write_csv(history, fields, [dict(row, question_ref="q001")])
        self.assertIn("does not change links", self.run_cli("import-history", "--input-csv", str(history)))
        self.assertEqual(self.rows("A Answers/Historical-Answer-Catalog.csv")[0]["question_ref"], "")
        self.run_cli("link-history", "--history", "h001", "--question", "q001", "--reason", " ", expected=2)
        self.run_cli("link-history", "--history", "h001", "--question", "q001", "--reason", "Same product description")
        self.assertIn("already linked", self.run_cli("link-history", "--history", "h001", "--question", "q001", "--reason", "again"))
        self.assertEqual(len(self.rows("A Answers/Historical-Links.csv")), 1)
        catalog = self.rows("A Answers/Historical-Answer-Catalog.csv")[0]
        self.assertEqual((catalog["question_ref"], catalog["source_question"], catalog["status"]),
                         ("", "What do you make?", "historical_unreviewed"))
        self.run_cli("review-sheet")
        view = self.rows("Questions-and-Answers-View.csv")
        self.assertEqual([r["answer_status"] for r in view if r["question_ref"] == "q001"], ["historical_unreviewed"])
        self.assertFalse([r for r in view if r["answer_status"] == "historical_unlinked"])
        self.assertEqual(self.rows("A Answers/Answer-Index.csv"), [])
        self.assertIn("approved", self.run_cli("assemble", "--application", app, "--map", "q001=h001", expected=2))
        self.run_cli("validate")

    def test_question_metadata_can_be_corrected_but_not_silently(self):
        self.run_cli("init")
        app = self.blank_app()
        add = ["add-question", "--application", app, "--order", "1", "--text", "Architecture link"]
        self.run_cli(*add, "--options", "url")
        self.run_cli(*add)
        self.run_cli(*add, "--options", "url", "--unknown")
        self.assertIn("update-question", self.run_cli(*add, "--required", expected=2))
        self.assertIn("update-question", self.run_cli(*add, "--limit", "chars:150", expected=2))
        self.assertEqual(self.rows("QU Questions/Question-Index.csv")[0]["required"], "unknown")
        self.run_cli("update-question", "--question", "q001", "--required", "--limit", "chars:150")
        row = self.rows("QU Questions/Question-Index.csv")[0]
        self.assertEqual((row["required"], row["limit"], row["options"], row["original_question"], row["status"]),
                         ("yes", "chars:150", "url", "Architecture link", "captured"))
        self.run_cli("update-question", "--question", "q001", "--summary", "Link")
        self.assertEqual(self.rows("QU Questions/Question-Index.csv")[0]["limit"], "chars:150")
        self.run_cli("update-question", "--question", "q001", "--options", "", "--limit", "")
        row = self.rows("QU Questions/Question-Index.csv")[0]
        self.assertEqual((row["options"], row["limit"], row["required"]), ("", "", "yes"))
        self.run_cli("update-question", "--question", "q001", "--text", "Pitch deck", expected=2)
        self.run_cli("update-question", "--question", "q001", expected=2)
        self.assertEqual(len(self.rows("QU Questions/Question-Index.csv")), 1)

    def test_not_applicable_and_skipped_fields_never_create_bank_answers(self):
        self.run_cli("init")
        app = self.blank_app()
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "What do you build?", "--required")
        self.run_cli("add-question", "--application", app, "--order", "2", "--text", "Co-founder profile", "--unknown")
        self.run_cli("add-question", "--application", app, "--order", "3", "--text", "Anything else?", "--optional")
        self.run_cli("add-question", "--application", app, "--order", "4", "--text", "Referrer", "--unknown")
        ref = self.approved("Product", "We build irrigation planning tools.", "q001")
        self.run_cli("mark-question", "--question", "q002", "--not-applicable", expected=2)
        self.run_cli("mark-question", "--question", "q002", "--skipped", "--reason", "x", expected=2)
        self.run_cli("mark-question", "--question", "q002", "--not-applicable", "--reason", "Hidden when # of founders = 1; applicant is a solo founder")
        self.run_cli("mark-question", "--question", "q003", "--skipped", "--reason", "Applicant chose to leave it blank")
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        draft = (self.workspace / f"S Submit/{app}/Application-draft.md").read_text(encoding="utf-8")
        self.assertIn("q004: answer missing; requirement not confirmed", draft)
        self.assertIn("q002 not applicable: Hidden when", draft)
        self.assertIn("q003 skipped (optional)", draft)
        self.run_cli("mark-question", "--question", "q004", "--not-applicable", "--reason", "Shown only for referrals; applicant chose Google")
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        ready = (self.workspace / f"S Submit/{app}/Application-ready.md").read_text(encoding="utf-8")
        self.assertIn("Status: ready", ready)
        self.assertIn("structural checks", ready)
        self.assertEqual(len(self.rows("A Answers/Answer-Index.csv")), 1)
        self.assertIn("marked not_applicable", self.run_cli("assemble", "--application", app, "--map", f"q001={ref}",
                                                            "--map", f"q002={ref}", expected=2))
        self.run_cli("update-question", "--question", "q003", "--required")
        self.assertIn("Skipped field is not known optional", self.run_cli("validate", expected=2))
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        self.assertIn("marked skipped but requirement is yes",
                      (self.workspace / f"S Submit/{app}/Application-draft.md").read_text(encoding="utf-8"))
        self.run_cli("mark-question", "--question", "q003", "--clear")
        self.run_cli("review-sheet")
        states = {r["question_ref"]: r["answer_status"] for r in self.rows("Questions-and-Answers-View.csv")}
        self.assertEqual((states["q002"], states["q003"]), ("not_applicable", "unanswered"))
        self.run_cli("validate")

    def test_draft_and_ready_outputs_never_leave_a_stale_current_file(self):
        self.run_cli("init")
        app = self.blank_app("Northstar", "Spring Cohort")
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "What do you build?", "--required", "--limit", "words:20")
        ref = self.approved("Product", "We build irrigation planning tools.", "q001")
        out_dir = self.workspace / f"S Submit/{app}"
        self.run_cli("assemble", "--application", app)
        self.assertEqual(sorted(p.name for p in out_dir.glob("*.md")), ["Application-draft.md"])
        self.assertIn("# Northstar — Spring Cohort — application answers",
                      (out_dir / "Application-draft.md").read_text(encoding="utf-8"))
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        self.assertEqual(sorted(p.name for p in out_dir.glob("*.md")), ["Application-ready.md"])
        self.assertIn("unchanged", self.run_cli("assemble", "--application", app, "--map", f"q001={ref}"))
        self.run_cli("update-question", "--question", "q001", "--limit", "words:2")
        self.run_cli("assemble", "--application", app, "--map", f"q001={ref}")
        self.assertEqual(sorted(p.name for p in out_dir.glob("*.md")), ["Application-draft.md"])
        self.assertEqual(sorted(p.name for p in (out_dir / "Previous").glob("*.md")),
                         ["001-Application-draft.md", "002-Application-ready.md"])
        unknown = self.blank_app("Unverified", "Form", mode=None)
        self.run_cli("add-question", "--application", unknown, "--order", "1", "--text", "What do you build?", "--required")
        self.run_cli("link-answer", "--answer", ref, "--question", "q002", "--reason", "Same product question")
        self.run_cli("assemble", "--application", unknown, "--map", f"q002={ref}")
        self.assertIn("Source mode not verified",
                      (self.workspace / f"S Submit/{unknown}/Application-draft.md").read_text(encoding="utf-8"))
        self.assertIn("Source mode recorded", self.run_cli("add-application", "--entity", "Unverified", "--title", "Form",
                                                           "--funnel", "Tech", "--source-mode", "blank"))
        self.run_cli("add-application", "--entity", "Unverified", "--title", "Form", "--funnel", "Tech",
                     "--source-mode", "completed", expected=2)
        self.run_cli("assemble", "--application", unknown, "--map", f"q002={ref}")
        self.assertTrue((self.workspace / f"S Submit/{unknown}/Application-ready.md").exists())
        past = self.blank_app("Old", "Record", mode="completed")
        self.run_cli("add-question", "--application", past, "--order", "1", "--text", "What do you build?")
        self.assertIn("completed historical record", self.run_cli("assemble", "--application", past, expected=2))

    def test_colliding_answer_titles_are_rejected(self):
        self.run_cli("init")
        app = self.blank_app()
        self.run_cli("add-question", "--application", app, "--order", "1", "--text", "Deck link", "--required")
        text = self.base / "deck.txt"
        text.write_text("https://example.test/deck.pdf", encoding="utf-8")
        self.run_cli("save-answer", "--title", "Deck: link", "--text-file", str(text), "--questions", "q001")
        self.assertIn("collides", self.run_cli("save-answer", "--title", "Deck link!", "--text-file", str(text),
                                               "--questions", "q001", expected=2))
        self.run_cli("save-answer", "--title", "Deck: link", "--text-file", str(text), "--questions", "q001")
        self.assertEqual([r["answer_ref"] for r in self.rows("A Answers/Answer-Index.csv")], ["a001-v001", "a001-v002"])

    def test_archived_source_keeps_single_hash_prefix(self):
        self.run_cli("init")
        self.blank_app("First", "Form")
        self.blank_app("Second", "Form")
        source = self.base / "live-form.md"
        source.write_text("Pitch Us\n1. Email\n", encoding="utf-8")
        self.run_cli("add-source", "--application", "first-form", "--file", str(source))
        archived = next((self.workspace / "A Applications/first-form/Sources").iterdir())
        self.run_cli("add-source", "--application", "second-form", "--file", str(archived))
        again = next((self.workspace / "A Applications/second-form/Sources").iterdir())
        self.assertEqual(again.name, archived.name)
        self.assertEqual(again.read_bytes(), source.read_bytes())

    def test_run_plan_source_modes(self):
        self.run_cli("init")
        source = self.base / "submitted.md"
        source.write_text("Submitted: 2026-03-01\nWhat do you build? We build tools.\n", encoding="utf-8")
        questions = self.workspace / "q.csv"
        self.write_csv(questions, ["order", "question", "options", "required", "limit", "source_ref"],
                       [dict(order="1", question="What do you build?", options="", required="yes", limit="", source_ref="")])
        mapping = self.workspace / "map.csv"
        self.write_csv(mapping, ["question_ref", "answer_ref"], [dict(question_ref="q001", answer_ref="a001-v001")])
        legacy = ["entity", "program", "funnel", "source_file", "source_url", "questions_csv", "history_csv", "answer_map_csv"]
        plan = self.workspace / "plan.csv"
        base = dict(entity="Fund", program="Form", funnel="Tech", source_file=str(source), source_url="",
                    questions_csv=questions.name, history_csv="", answer_map_csv="")
        self.write_csv(plan, legacy + ["source_mode"], [dict(base, answer_map_csv=mapping.name, source_mode="completed")])
        self.assertIn("completed historical record", self.run_cli("run", "--plan", str(plan), expected=2))
        self.assertFalse((self.workspace / "A Applications/fund-form").exists())
        self.write_csv(plan, legacy + ["source_mode"], [dict(base, source_mode="maybe")])
        self.run_cli("run", "--plan", str(plan), "--dry-run", expected=2)
        self.write_csv(plan, legacy, [base])  # 0.1.12 plan: no source_mode column.
        self.run_cli("run", "--plan", str(plan))
        self.run_cli("update-question", "--question", "q001", "--summary", "Product", "--kind", "custom")
        ref = self.approved("Product", "We build tools.", "q001")
        self.write_csv(plan, legacy, [dict(base, answer_map_csv=mapping.name)])
        self.run_cli("run", "--plan", str(plan))
        status = self.rows("Run-Status.csv")[0]
        self.assertEqual(status["S"], "source_mode_unverified")
        self.assertFalse((self.workspace / "S Submit/fund-form").exists())
        self.write_csv(plan, legacy + ["source_mode"], [dict(base, answer_map_csv=mapping.name, source_mode="blank")])
        self.run_cli("run", "--plan", str(plan))
        self.assertEqual(self.rows("Run-Status.csv")[0]["S"], "draft_ready")
        self.write_csv(plan, legacy + ["source_mode"], [dict(base, source_mode="completed")])
        self.assertIn("conflicts with recorded blank", self.run_cli("run", "--plan", str(plan), expected=2))
        changed = self.workspace / "q2.csv"
        self.write_csv(changed, ["order", "question", "options", "required", "limit", "source_ref"],
                       [dict(order="1", question="What do you build?", options="", required="unknown", limit="", source_ref="")])
        self.write_csv(plan, legacy + ["source_mode"], [dict(base, questions_csv=changed.name, source_mode="blank")])
        self.assertIn("update-question", self.run_cli("run", "--plan", str(plan), expected=2))
        self.assertEqual(ref, "a001-v001")

    def test_completed_run_plan_row_is_evidence_only(self):
        self.run_cli("init")
        source = self.base / "submitted.md"
        source.write_text("Submitted: 2026-03-01\n", encoding="utf-8")
        questions = self.workspace / "q.csv"
        self.write_csv(questions, ["order", "question", "options", "required", "limit", "source_ref"],
                       [dict(order="1", question="Why now?", options="", required="unknown", limit="", source_ref="")])
        history = self.workspace / "h.csv"
        self.write_csv(history, ["source_question", "answer_text", "source_date", "kind", "theme", "question_ref"],
                       [dict(source_question="Why now?", answer_text="Timing fits.", source_date="2026-03-01",
                             kind="custom", theme="Timing", question_ref="q001")])
        plan = self.workspace / "Run-Plan.csv"
        self.write_csv(plan, ["entity", "program", "funnel", "source_file", "source_url", "questions_csv",
                              "history_csv", "answer_map_csv", "source_mode"],
                       [dict(entity="Old", program="Record", funnel="Tech", source_file=str(source), source_url="",
                             questions_csv=questions.name, history_csv=history.name, answer_map_csv="",
                             source_mode="completed")])
        self.run_cli("run")
        self.run_cli("update-question", "--question", "q001", "--summary", "Timing", "--kind", "custom")
        self.run_cli("run")
        status = self.rows("Run-Status.csv")[0]
        self.assertEqual((status["Answers"], status["S"]), ("review_needed", "historical_record"))
        self.assertIn("Source mode: completed", (self.workspace / "A Applications/old-record/Application.md").read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / "S Submit/old-record").exists())
        self.assertEqual(self.rows("A Answers/Answer-Index.csv"), [])

    def test_saved_opt_out_overrides_environment_opt_in(self):
        self.run_cli("init")
        env = dict(os.environ, AQUA_BETA_REPORTING="1", AQUA_BETA_REPORT_URL="https://reports.example.test/ingest")
        self.run_cli("beta-reporting", "--disable")
        self.assertIn("local_only", self.run_cli("report-issue", "--detail", "private", env=env))
        with patch.dict(os.environ, {"AQUA_BETA_REPORTING": "1",
                                     "AQUA_BETA_REPORT_URL": "https://reports.example.test/ingest"}), \
             patch.object(beta, "urlopen", side_effect=AssertionError("must not send")):
            _, delivery = beta.record(self.workspace, "report-issue", "feedback", "private")
        self.assertEqual(delivery, "local_only")

if __name__ == "__main__":
    unittest.main()

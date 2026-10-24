# CSV run plan

The run plan orchestrates repeatable file work. It does not interpret application meaning, approve answers, fill forms, or submit applications. Keep the CSVs in the applicant's workspace so they can be opened in Numbers and brought into later sessions. The plugin manifest is package metadata, not a user run configuration.

1. Select one funnel and run `init --workspace <AQUA root>/<funnel> --funnel <funnel>`. This creates that funnel's `Run-Plan.csv` and blank question, historical-answer, and answer-map template CSVs. Other funnels have separate plans and indexes.
2. Add one row per application to `Run-Plan.csv`. Give each application its own copied question CSV, an optional historical-answer CSV, and later an answer-map CSV. Relative file paths resolve from the run plan's folder; absolute paths also work.
3. After reviewing/redacting each source and extracting its exact question wording, run `run --workspace <folder> --dry-run`, then `run --workspace <folder>`. The dry run checks the complete plan without writing to the workspace.
4. Read `Run-Status.csv` and the top of `PROGRESS.md`. Resolve the reported QU or answer gate using the existing AQUA commands, then rerun. Repeating a run does not duplicate unchanged applications, source files, or questions.

`Run-Plan.csv` columns, in order:

| Column | Meaning |
| --- | --- |
| `entity` | Organization offering the opportunity. |
| `program` | Program or application title. |
| `funnel` | Must match the selected workspace: `Tech`, `Jobs`, `College`, or `Grants Funding`. Rows for another funnel fail preflight. |
| `source_file` | User-authorized local source to archive. Leave blank only when a URL still needs capture. |
| `source_url` | Original public or user-authorized URL, if known. |
| `questions_csv` | Per-application CSV of exact captured questions. Blank means extraction remains to do. |
| `history_csv` | Optional historical Q+A harvested from a previously filled application. These become review candidates, not approved bank answers. |
| `answer_map_csv` | Per-application CSV choosing approved answer versions. Fill only after review. |
| `source_mode` | `blank` (verified current unanswered form), `completed` (submitted or historical record: evidence only, never assembled), or `unknown`. Leave `unknown` until the source has been inspected. A plan from 0.1.12 without this column runs with every row `unknown`. |

The question CSV columns are `order,question,options,required,limit,source_ref`. Use a positive source order, exact original question text, `yes`, `no`, or `unknown` for `required`, and a limit such as `words:150` or `chars:500` when known. Do not guess missing options or required status. The historical-answer CSV columns are `source_question,answer_text,source_date,kind,theme,question_ref`. The runner links each row to the archived source and catalogs it as `historical_unreviewed`; `question_ref` may be blank when a link is uncertain. The answer-map CSV columns are `question_ref,answer_ref`; each chosen answer must already be approved and linked to that question. An old completed application's answers go through `history_csv` or `import-history`, not the answer map, until the applicant has approved a reusable version.

`Run-Status.csv` reports historical candidate count and A, QU, Answers, and S per application. `review_needed` means the model and applicant have work to do; `waiting_for_A`, `waiting_for_QU`, and `waiting_for_answers` describe phase order, not missing AQUA capabilities. `draft_ready` means `Application-ready.md` exists in `S Submit/` because the structural checks passed, not that the form was filled or submitted. `checks_needed` means an `Application-draft.md` still lists issues. `source_mode_unverified` means answers are mapped but the source has not been verified as a blank form, so nothing was assembled. `historical_record` means the row is a completed record kept as evidence. Questions marked `not_applicable` or `skipped` do not need an answer-map row. The runner preserves manual notes in `PROGRESS.md` and updates only its marked run-status block.

If a plan contains only `source_url`, the runner records the application but pauses A until an authorized source capture is archived. It does not fetch arbitrary URLs itself. A malformed plan fails before any workspace changes, including a `completed` row with an answer map, a `source_mode` that conflicts with the recorded mode, or question metadata that differs from the existing index (correct that with `update-question`). If a later application fails after earlier applications were processed, the exception is recorded in the status CSV; fix it and rerun.

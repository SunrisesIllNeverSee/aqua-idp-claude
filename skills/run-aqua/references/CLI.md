# Local helper commands

Run with Python 3 from any directory. Set `SCRIPT` to the path of `skills/run-aqua/scripts/aqua.py` and `WORKSPACE` to the applicant's selected AQUA folder, or pass those paths directly. All commands require `--workspace`.

```sh
python3 "$SCRIPT" init --workspace "$WORKSPACE" --funnel Tech
python3 "$SCRIPT" migrate --workspace "$WORKSPACE"
python3 "$SCRIPT" run --workspace "$WORKSPACE" --dry-run
python3 "$SCRIPT" run --workspace "$WORKSPACE"
python3 "$SCRIPT" add-application --workspace "$WORKSPACE" --entity "Northstar" --title "Fellowship" --funnel Tech --source-url "https://example.org/apply" --source-mode blank
python3 "$SCRIPT" add-source --workspace "$WORKSPACE" --application northstar-fellowship --file /path/to/source.pdf
python3 "$SCRIPT" add-question --workspace "$WORKSPACE" --application northstar-fellowship --order 1 --text "What are you building?" --required --limit words:150
python3 "$SCRIPT" update-question --workspace "$WORKSPACE" --question q001 --summary "Product purpose and users" --kind custom --topic Product
python3 "$SCRIPT" update-question --workspace "$WORKSPACE" --question q001 --required --limit chars:150
python3 "$SCRIPT" mark-question --workspace "$WORKSPACE" --question q007 --not-applicable --reason "Hidden when # of founders = 1; applicant is a solo founder"
python3 "$SCRIPT" mark-question --workspace "$WORKSPACE" --question q008 --skipped --reason "Optional; applicant chose to leave blank"
python3 "$SCRIPT" group-questions --workspace "$WORKSPACE" --group "Product purpose" --questions q001,q002
python3 "$SCRIPT" save-answer --workspace "$WORKSPACE" --title "Product purpose" --text-file /path/to/draft.txt --questions q001 --answers-what "Product purpose and users" --sources "Applicant interview 2026-10-01"
python3 "$SCRIPT" approve-answer --workspace "$WORKSPACE" --answer a001-v001 --evidence "Applicant approved this wording in chat" --preferred
python3 "$SCRIPT" reconfirm-approval --workspace "$WORKSPACE" --answer a001-v001 --evidence "Applicant reconfirmed the current wording after migration"
python3 "$SCRIPT" link-answer --workspace "$WORKSPACE" --answer a001-v001 --question q002 --reason "This later question asks for the same product purpose and users"
python3 "$SCRIPT" import-history --workspace "$WORKSPACE" --input-csv /path/to/extracted-history.csv
python3 "$SCRIPT" link-history --workspace "$WORKSPACE" --history h001 --question q004 --reason "Same product description, asked in a later form"
python3 "$SCRIPT" assemble --workspace "$WORKSPACE" --application northstar-fellowship --map q001=a001-v001
python3 "$SCRIPT" validate --workspace "$WORKSPACE"
python3 "$SCRIPT" review-sheet --workspace "$WORKSPACE"
```

`WORKSPACE` is one funnel folder, such as `/path/to/AQUA/Tech`; initialize other funnels at sibling paths. New folders must use the exact funnel name (`Tech`, `Grants Funding`, `College`, or `Jobs`). `Funnel.txt` records the selection. `add-application` and batch preflight reject another funnel. Existing single-funnel flat workspaces remain readable, but should not receive applications from another funnel. `add-application` prints the folder key for later commands. Repeating `init`, an unchanged `add-application`, the same source bytes, or the same question in the same source order is safe. A changed question in an occupied order stops for inspection. Repeating `add-question` with the same wording but different supplied `--required/--optional/--unknown`, `--options`, `--limit`, or `--source-ref` also stops; correct metadata with `update-question`. Omitted flags never clear stored values. Answer versions are always new drafts. Exact question wording is immutable through `update-question`.

`add-application --source-mode` records whether the archived source is a `blank` current form, a `completed` submitted or historical record, or `unknown` (the default). Inspect the source before choosing; never infer it from a folder name. Repeating `add-application` with a mode records it when the stored mode is still `unknown`, and refuses to change one known mode into another. Only a `blank` application can assemble as ready; a `completed` application cannot be assembled.

`update-question` changes interpretation (`--summary`, `--kind`, `--topic`, `--group`) and metadata: `--required`, `--optional`, or `--unknown`, plus `--limit` and `--options`. Pass an empty value (`--limit ""`) to clear a limit or options explicitly. Wording stays as captured.

`mark-question` records a field that needs no answer, with a reason and without creating a bank answer: `--not-applicable` when the field does not apply (for example a branch the applicant will not see), or `--skipped` for a known optional field deliberately left blank. A skipped field must have `required` = `no`. `--clear` returns the field to open. A field with unknown requirement or unresolved branching should stay open.

`review-sheet` regenerates `Questions-and-Answers-View.csv`, a Numbers-compatible review table. It shows every indexed question, including unanswered blanks, then one row for each linked historical or bank answer. Status distinguishes historical evidence, drafts, and approved versions. It is a derived view and must not be edited to change AQUA records. The batch `run` command refreshes it automatically after a successful run; refresh it explicitly after manual commands.

For `add-question`, use `--required` or `--optional` only when the source establishes it. Without either flag, the index records `unknown` and the assembled application flags that uncertainty.

`save-answer` accepts comma-separated question refs; all must exist. Use the same title for a new version of a topic; a different title that normalizes to the same folder name is refused. The draft file is plain text, with just the answer body. An answer version can be assembled only after `approve-answer` records explicit user approval. Approval stores `approved_sha256`, a SHA-256 digest of the `## Answer` body after this normalization: CRLF/CR become LF, Unicode NFC, trailing spaces removed from each line, leading and trailing blank lines removed. Headers, timestamps and question links are excluded. `validate`, `assemble`, and `link-answer` reject an approved version whose body no longer matches; never edit an approved file—save the change as a new draft and seek approval. Versions approved before 0.1.13 have no digest: `assemble` and `link-answer` refuse them and `validate` warns until `reconfirm-approval` records the applicant's reconfirmation of the current wording. `--preferred` changes the preferred version for that topic and retains previous approved versions. If a later question directly matches an existing approved answer, use `link-answer` with a concrete fit reason. This adds a row to `A Answers/Reuse-Links.csv` and updates the indexes without editing the approved answer file. For partial or adapted reuse, save a new draft instead. `assemble` accepts repeated `--map question=answer` arguments; every mapped answer must explicitly link to that question. Missing answers, unknown requirement, an unverified source mode, and parseable limit violations produce an incomplete draft named `Application-draft.md`; only a draft with no issues is written as `Application-ready.md`. One current file exists at a time; earlier outputs move to `Previous/` with a sequence prefix. "Ready" means the recorded structural checks passed—the agent and applicant must still review answer fit, current facts, attachments, and form conditions. Workspaces from 0.1.12 may still hold `Application-ready-NNN.md` copies; they are earlier outputs, not current drafts. The agent must still inspect attachments, branching, applicant facts, and the live form.

For beta feedback, `report-issue --workspace <path> --detail <description>` creates a local diagnostic in `Beta Reports/`. Unexpected helper crashes do the same automatically. After the user opts in, `beta-reporting --workspace <path> --enable --endpoint <HTTPS receiver>` saves the delivery choice for future sessions; use `--disable` to stop delivery. The `AQUA_BETA_REPORTING=1` and `AQUA_BETA_REPORT_URL` environment variables can also enable delivery for a single command. Delivery never sends the local detail, source paths, questions, or answers. A saved `--disable` choice overrides the environment variables. Check the printed delivery state before claiming the report was received. The remote receiver is separate from the plugin.

`limit` supports `words:150` or `chars:500`; other visible limits are retained and flagged for manual checking. The helper never browses, classifies semantics, approves on its own, fills a form, or submits it. The agent does those steps within the user's instructions and available tools.

For old completed applications, archive the source first, then prepare an extraction CSV with these exact columns in this order:

`application,source_path,source_question,answer_text,source_date,kind,theme,question_ref`

`source_path` is relative to the AQUA workspace and must point to an archived file. `kind` is `general`, `custom`, or `unknown`. `question_ref` may be blank until the old question is indexed. `import-history` writes `A Answers/Historical-Answer-Catalog.csv`, retains original answer text and source context, and is idempotent. Re-importing an identical answer never changes its links; the helper reports a differing `question_ref` instead. Its rows are historical evidence, never approved bank answers. `link-history --history h001 --question q004 --reason ...` marks a historical answer as a candidate for another or later question in `A Answers/Historical-Links.csv`, keeping the original source question and provenance; one historical answer may link to several questions. A link signals candidate relevance only, never approval. The review sheet lists historical answers without any link as `historical_unlinked` rows. Promote a selected answer with `save-answer`, then seek user approval as usual.

## Migrating a 0.1.12 workspace

0.1.13 adds index columns (`field_state`, `field_state_reason`, `approved_sha256`) and `A Answers/Historical-Links.csv`. A workspace created by 0.1.12 makes other commands stop with a message to run `migrate`. `migrate` copies every changed index to `.aqua-migrations/<time>-to-0.1.13/`, adds the new columns with blank values, creates the link file, writes `MIGRATION.md` there, and lists approved versions that need reconfirmation. It never edits answer, source, or application Markdown files, and a second run changes nothing. Old `Run-Plan.csv` files without `source_mode` still run, with every row treated as `unknown` until the agent verifies the source.

The review sheet now includes `required`, `limit`, `related_group`, and `field_state` columns; regenerate it with `review-sheet` after migrating.

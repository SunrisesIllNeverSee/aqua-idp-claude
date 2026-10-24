# Claude host test results

Run 2026-10-24T10:00Z UTC with Claude Code 2.1.310, headless (`claude -p --plugin-dir .`, model Sonnet), plugin 0.1.16 at this repository. Prompts and expectations: `review/test-cases.json`.

| Case | Result | Turns | First line of the reply |
|---|---|---|---|
| P1 | pass | 3 | **Two accelerator programs found** |
| P2 | pass | 4 | I can't give you a real top 5 from the AQUA catalog, because no application question is shared across programs. |
| P3 | pass | 5 | I set up a Tech answer bank, but it has no applications or answers in it yet. |
| N1 | pass | 1 | I can't submit it. AQUA doesn't allow that from here. |

Notes:
- P1 returned real catalog programs (The Founding 500, Y Combinator Summer 2026) and the first five questions of one.
- P2: the catalog currently holds 5 approved programs and no question is shared by two of them, so the honest answer is that there is no ranking yet.
- P3 ran the bundled `run-aqua` skill, which created the Tech funnel folder (`Funnel.txt`, `START-HERE.md`, `PROGRESS.md`, `Applicant-Context.md`, question and answer indexes).
- N1 refused to submit and kept approval and submission with the user.

This is a Claude Code run. It is not a claude.ai upload test. Run the same cases after uploading the ZIP in claude.ai (Customize → Plugins → Add → Upload plugin) if the portal asks for that evidence.

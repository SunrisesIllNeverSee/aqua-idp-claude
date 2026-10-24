# AQUA workspace

Stored at: `{{WORKSPACE}}`
Selected funnel: **{{FUNNEL}}**

AQUA preserves applications, indexes their questions, develops reusable answers, and prepares complete Markdown applications. Work moves through `A Applications/`, `QU Questions/`, `A Answers/`, and `S Submit/`.

AQUA works like a careful archivist and editor. It keeps the original application intact, explains what each question seeks, checks whether an earlier answer still fits, and prepares a draft you can review. It should tell you what it found, what is uncertain, and the next useful action. Your approval controls new or changed answer wording; a prepared draft is not a submitted form.

This folder is only for **{{FUNNEL}}** applications. Other opportunity types use sibling folders with their own application archives, question indexes, answer banks, and drafts. Answers are not copied between them automatically.

To resume, read `PROGRESS.md`, `Applicant-Context.md`, and the two CSV indexes. To start a new application, provide a source document or authorized URL and identify the applicant. Approved answer versions remain in `A Answers/`; drafts are separate. `S Submit/` contains copyable prepared applications: `Application-draft.md` while checks remain, `Application-ready.md` only when the recorded structural checks pass (you still review fit, facts, attachments and the live form), and earlier versions in `Previous/`. Submission is recorded only after an observed confirmation.

You can begin with an empty application: send a URL, screenshot, file, or pasted form, or ask AQUA to find a public opportunity. AQUA saves a dated source snapshot, indexes the visible questions, and shows what has no answer yet. Past completed applications can then add historical answer candidates. After you approve reusable wording, a new blank application can use fitting answers and reveal the remaining gaps. Open `Questions-and-Answers-View.csv` in Numbers to review the combined Q&A; it is regenerated from the original indexes and answer files.

For a batch, enter one application per row in `Run-Plan.csv`. Copy the question, historical-answer, and answer-map template CSVs as needed for each application, then use `python3 <plugin>/skills/run-aqua/scripts/aqua.py run --workspace <this folder>`. The runner archives supplied local sources, indexes supplied question rows and historical answer candidates, and writes `Run-Status.csv` plus work needed at the top of `PROGRESS.md`. It pauses for question interpretation and explicit answer approval. It never submits a form. See the plugin's `references/RUN-PLAN.md` for columns and an example.

Keep this entire folder to retain your bank across sessions. Bring it into a future session if your host does not persist local files.

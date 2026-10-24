# AQUA IDP for Claude

Stop rewriting the same application answers. AQUA IDP archives every application you give it, indexes its questions, reuses answers you have already approved, and prepares a complete Markdown draft for your review. It works for funding, accelerators, jobs, college, and grants.

Published by Ello Cello LLC · [aquaidp.xyz](https://aquaidp.xyz) · [Privacy](https://aquaidp.xyz/privacy) · [Terms](https://aquaidp.xyz/terms) · [Support](https://aquaidp.xyz/support)

## What it does

1. **Archive.** Saves each application's original source (a URL, file, screenshot, or pasted form) with its exact questions, options, limits, and branches.
2. **Index.** Organizes the questions, tags what each one asks, and connects questions that ask the same thing across programs.
3. **Reuse.** Builds a bank of answers you approve. One approved answer covers every form that asks the same fact, so you approve it once.
4. **Draft.** Assembles a copyable Markdown draft of each application from your approved answers and shows you what is still open.

AQUA never approves an answer for you, never submits a form, and never claims a draft was submitted. Approval records a digest of the exact wording, so approved text can't change silently.

## Install

In Claude Code:

```
/plugin marketplace add SunrisesIllNeverSee/aqua-idp-claude
/plugin install aqua-idp@aqua
```

## Use

Ask Claude in plain language, for example:

- "Archive these applications and start my answer bank."
- "Find approved answers I can reuse for this application."
- "Prepare a Markdown draft of this application for my review."

AQUA works inside one folder you choose (for example `~/AQUA/Tech`), with separate funnels for Tech, Grants Funding, College, and Jobs. Everything it writes stays in that folder: source copies, the question index, your answer versions, drafts, and progress notes. Keep the folder to keep your bank.

## Requirements

- Claude Code with file access to a writable folder
- Python 3 (the bundled helper `skills/run-aqua/scripts/aqua.py` uses only the standard library)

## Privacy

Your applications and answers stay in your folder. The publisher does not receive them through the plugin's normal workflow. AQUA uses only the files, URLs, and professional context you provide or authorize. It does not sign in to your accounts.

Optional beta diagnostics are **off by default**. If you turn them on, the plugin sends only a random report ID, time, plugin version, command, issue type, error class, a grouping fingerprint, Python version, and OS name. It never sends questions, answers, files, or paths. Turn delivery off with `beta-reporting --disable`. Full details: [aquaidp.xyz/privacy](https://aquaidp.xyz/privacy).

Don't put passwords, API keys, payment-card data, government IDs, or health information into an application you give AQUA. It will ask you for a redacted copy.

## Tests

```
python3 -m pytest -q tests
```

## License

MIT © 2026 Ello Cello LLC. See [LICENSE](LICENSE). The AQUA name and the MO§ES™ framework are trademarks of Ello Cello LLC.

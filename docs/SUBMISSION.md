# Submit to the Claude directory

The package is ready. The repository is public at https://github.com/SunrisesIllNeverSee/aqua-idp-claude, with `.claude-plugin/plugin.json` at the root. `claude plugin validate . --profile directory --strict` passes. Listing values to paste are in `review/listing.json`; test evidence is in `review/claude-host-results.md`. [Directory publishing](https://claude.com/docs/directory/publish)

Use the same Claude account and organization for both steps.

## 1. Submit the connector

Open https://claude.ai/directory/manage → Submit new → MCP connector.

- Server URL: `https://aquaidp.xyz/mcp` (the exact URL in `.mcp.json`)
- Authentication: No authentication
- Listing, company, support and privacy values: `review/listing.json`
- Reviewer access: no credentials; connect with No sign in and run any `hub_*` tool. All 11 tools are read-only and annotated `readOnlyHint: true`.

[Connector submission](https://claude.com/docs/connectors/building/submission)

## 2. Submit the plugin bundle

Submit new → Plugin bundle.

- Repository: `SunrisesIllNeverSee/aqua-idp-claude`
- Plugin path: leave empty (package at the root)
- Branch: `main`
- Pair it with the connector above, using the identical server URL.

[Bundle requirements](https://claude.com/docs/plugins/pre-submission-checklist)

## 3. Finish as publisher

The owner confirms the publisher (Ello Cello LLC), the data-handling answers, the intended age audience and the compliance acknowledgements, then submits. Nothing here is prefilled as an attestation: no legal-compliance claims, no approval.

## Keeping in sync

The source of truth is `aqua-applications/` in aquarnd. Bump versions together: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `skills/run-aqua/scripts/beta.py` `VERSION`.

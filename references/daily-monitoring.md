# Daily literature monitoring

## What LitWatch automates

Daily monitoring has three separate layers:

| Layer | Responsibility |
|---|---|
| LitWatch `watch` | Query from the saved checkpoint, overlap recent dates, deduplicate, refresh lifecycle state, and write a new report |
| Host automation or OS scheduler | Wake up at the requested local time and invoke `watch` |
| Tool-capable model or notification integration | Read the report, select actionable changes, optionally deep-read eligible papers, and deliver a message |

The first layer is portable Python. The other two belong to the host. A Skill
cannot remain alive after its session ends, so never claim that “daily tracking
is enabled” merely because a command or prompt was printed.

## Setup protocol

1. Confirm a persistent, writable workspace outside the Skill directory. An
   ephemeral container cannot maintain checkpoints across days.
2. Obtain any missing schedule choices: local run time, timezone, whether the
   machine/agent will be available then, and whether the user wants a message
   every day or only on meaningful change/failure. Default to quiet on a clean
   no-change run unless the user explicitly requests a daily heartbeat.
3. Establish a baseline before scheduling: initialize, add seeds, run a dry
   discovery for review, then complete one saved `discover`. Reuse the same
   workspace, Python interpreter, Skill checkout, config, and credentials later.
   For resilient biomedical monitoring, enable PubMed before scheduling and keep
   PMIDs plus `NCBI_EMAIL`; optionally enable Semantic Scholar with an API key.
   Crossref DOI references are already enabled by default. An OpenAlex 429 still
   makes that run incomplete even when these routes return useful candidates.
4. Run `doctor --network` and one manual `watch --dry-run --summary` as a
   readable preflight.

The dry-run watch predicts the new papers and meaningful lifecycle/status
changes that a saved watch would report, but does not update history or files.
5. Create a recurring task only after explicit authorization. Prefer the host's
   native recurring automation when it can run tools and deliver results. If it
   cannot, configure cron, Windows Task Scheduler, or another user-approved
   scheduler to run the CLI. If the user asks for actual creation, do not stop at
   a prompt or generic instructions when the host exposes a task tool: show the
   final configuration, obtain confirmation, create it, then return its task
   name or ID, next-run time, timezone, notification rule, and verification
   result. If no task tool exists, state clearly that nothing was created and
   provide the host-specific procedure. Showing instructions is not verification.
6. Prevent overlapping runs. LitWatch's workspace lock rejects a second writer,
   but the scheduler should also avoid starting another instance while one runs.

The recurring command is:

    python scripts/litwatch.py watch --workspace "WORKSPACE"

Run it from the installed LitWatch directory, or use absolute paths for both the
chosen Python executable and `scripts/litwatch.py`. `WORKSPACE` is a placeholder.
Do not add a fixed `--since`: the successful search checkpoint and overlap window
recover missed days without repeatedly scanning a fixed history.

## Recurring task payload for an agent host

Use this as the body of a host-native daily task after replacing every
placeholder:

    Use $litwatch with the existing workspace <WORKSPACE>. This is the scheduled
    daily run for <LOCAL TIME> in <TIMEZONE>. Run one non-dry-run `watch` without
    a fixed `--since`. Use the report path returned by this invocation; do not
    mistake an older `latest.json` for today's result if the command fails before
    writing a report. Reserve `doctor --network` for setup, periodic maintenance,
    or troubleshooting rather than doubling every daily network check.

    If exit code is 3 or `complete=false`, report that source coverage was
    incomplete and include the warnings; do not call it “no new papers”. If
    `bounded=true`, disclose that configured caps were reached. On success,
    report new accepted papers and publication, correction, concern, or
    retraction events. Include pending papers only when human review is required.
    Stay quiet when there is no meaningful change unless the task requests a daily
    heartbeat. If new accepted papers pass the identity, relevance, retraction,
    and readable-full-text gates, deeply interpret at most three in the delivered
    message; otherwise do not pad the count. Include sourced manuscript-history
    dates and verified direct links, marking unavailable facts explicitly.

## Result and failure handling

| Observation | Required handling |
|---|---|
| Exit `0`, fresh report, no actionable changes | Keep quiet by default, or send the requested “no new literature” heartbeat |
| Exit `0`, actionable changes | Deliver a concise digest and up to three eligible detailed readings |
| Exit `3` or `complete=false` | A report exists but coverage is incomplete; alert with source warnings |
| `bounded=true` | Run completed within configured caps but was not exhaustive; disclose the cap |
| Exit `1`, `2`, `130`, or no fresh report | Report environment/input/interruption failure; never summarize stale `latest.json` as today's run |
| Lock error | Another or stale run exists; inspect it rather than deleting the lock blindly |

An OS scheduler without a model or notification integration only updates the
workspace reports and Excel file. It cannot produce a chat explanation by
itself. A host-native agent automation can run the Skill, read the fresh report,
and deliver the digest when the host exposes those capabilities.

## Recovery and changes

- A missed day normally needs no manual date repair. The next successful `watch`
  starts from the last successful checkpoint minus the configured overlap.
- Do not advance or overwrite the workspace after an incomplete source search;
  LitWatch preserves the last successful search checkpoint.
- After moving Python, the Skill checkout, or the workspace, update and retest the
  scheduled command. After changing seeds or filters, run a manual dry preview.
- Keep API credentials available to the scheduler's account, not only an
  interactive shell. Never put secrets into the command, config, report, or task
  description.
- Close `accepted_papers.xlsx` before the scheduled time on systems where Excel
  locks open workbooks.

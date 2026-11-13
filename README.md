# The court skill (Pi)

When your model agrees with everything you say, put your idea on trial in front of a jury of 12
sub-agents. One [Pi](https://pi.dev) skill. Free, MIT, no signup, no API key, nothing to connect.

Maintained by **Cristiano Gariboldo** (Pixel3Design) — [social@pixel3design.it](mailto:social@pixel3design.it).

Ask the model "is this a good idea?" and it usually says yes. `/skill:court` takes the same idea and
runs a trial instead:

0. The **clerk** weighs the evidence first. Nothing to judge? The case is dismissed with no trial. A
   decision-critical fact missing? It asks for it. A pile of unrelated evidence? It maps what relates
   to what and sends the case back to be reorganised.
1. A **prosecutor** sub-agent builds the strongest honest case that your idea fails as described.
2. A **defense** sub-agent builds the strongest honest case that it works.
3. Each side answers the other's points.
4. **12 jurors** read the record and vote GUILTY or NOT GUILTY on their own. Each one sees the case
   through different eyes: an accountant, a first-time customer, a competitor, a retired judge, a
   teenager, an engineer, a small-business owner, a statistician, a parent, an investor, a designer
   and a lawyer. No juror sees another's vote, so nobody can just go along with the room.
5. A **judge** sub-agent reads the verdict, the charges that stuck, what the defense got right, and the
   conditions for acquittal: the specific changes that would flip the most votes.

What comes back is `VERDICT.md`: the vote (for example GUILTY, 9 to 3), every juror's one-line reason,
and what to change before you try again. If the case is dismissed before trial, you get
`.court/DISMISSED.md` instead: what is missing, or what relates to what and what to cut.

**It never touches your files.** Everything is written inside `.court/` in the folder you run it in.

## Where this comes from

This is a derivative work, and the idea is not original to this repo. The trial design — a prosecutor,
a defense, rebuttals, 12 jurors who never see each other's vote, a judge who reads the verdict, and a
`court.py` clerk that only does bookkeeping — comes from the original **court** skill by Alex Chen,
written for another agent harness: **https://github.com/alexyc9381/court-skill**.

This repo ports that work to [Pi](https://pi.dev) and keeps its spirit: same trial, same charge, same
verdict format, same rule that the orchestrating agent never argues, never votes and never edits the
verdict. The original is MIT-licensed, and so is this port.

## Differences from the original

- **Runs on Pi, not the original harness.** Invoked as `/skill:court` instead of `/court`; the script
  path is resolved from the skill directory instead of a harness-supplied skill-dir variable;
  sub-agents run through Pi's `Agent` tool instead of the older harness's `Task` tool.
- **Evidence gate, enforced in code.** Before a single sub-agent runs, the clerk checks the filing: no
  evidence dismisses the case, a fact the verdict depends on means up to three questions first, and
  evidence that does not bear on the charge dismisses it with a map of what relates to what and a
  request to reorganise. `court.py dismiss` writes `.court/DISMISSED.md` and leaves a marker that
  `court.py init` refuses to cross, and `init` also rejects a case file with no number, cost, date or
  result in it unless the caller passes `--force`. The original opened the trial straight away.
- **Parallel by design.** The whole phase (2 openings, 2 rebuttals, 12 jurors) is launched in a single
  message as foreground agents, so a full trial is 4 blocking rounds and roughly two minutes. The
  original launched in waves of six, which serialized the jury.
- **Needs the Pi sub-agents extension.** `pi install npm:@tintinweb/pi-subagents`, which provides the
  `Agent` tool. The older harness bundles its own.
- **Pi packaging.** `package.json` with the `pi-package` keyword and a `pi.skills` manifest, instead of
  a plugin marketplace manifest and `plugin.json`.
- **Arguments.** Pi appends the text after `/skill:court` to the instructions, so the older harness's
  `$ARGUMENTS` placeholder and the `argument-hint` frontmatter field are gone; the flags below still work.
- **Smaller Pi-side cleanups.** Install, uninstall and credit lines, the `uv run` test command, and
  tests that check the phase is listed as one parallel launch.

## Install

Paste this into Pi:

```
https://github.com/pixel3design-hub/Pi.dev-court-skill
Install this skill for Pi, then confirm /skill:court works.
```

Or as a Pi package:

```bash
pi install git:github.com/pixel3design-hub/Pi.dev-court-skill
```

Or copy the skill folder into any Pi skill directory:

```bash
git clone https://github.com/pixel3design-hub/Pi.dev-court-skill
cp -r Pi.dev-court-skill/skills/court ~/.agents/skills/
```

Run `/reload` (or restart Pi) and it shows up as `/skill:court`.

The jury is made of Pi sub-agents, so the `@tintinweb/pi-subagents` extension has to be installed
(`pi install npm:@tintinweb/pi-subagents`). Without it there is no `Agent` tool and no trial.

## Use

```
/skill:court Quit my job to sell candles on Etsy full time. I have $8,000 saved and 40 sales so far.
```

| flag | meaning |
| --- | --- |
| `--jury N` | 3 to 12 jurors. Default 12. |
| `--quick` | 6 jurors. |
| `--seed S` | Fixes which jurors sit on a smaller jury. |

A full trial is 17 sub-agent calls (2 openings, 2 rebuttals, 12 jurors, 1 judge); `--quick` is 11.
They run in parallel, one round per phase, so a full trial is 4 blocking rounds: the wall clock is
about the slowest agent in each round, not the sum of 17.
Every sub-agent counts toward your model usage, so start with `--quick` if you are near your limit.

See `examples/candles/VERDICT.md` for a real (3-juror) trial: "Quit my job as a nurse to sell
handmade candles on Etsy full time" came back GUILTY, 3 to 0, with the conditions that would flip it.

### What can end it before the trial

The case is read as a filing before any sub-agent runs, and `court.py` enforces the outcome:

- **No evidence** (no number, cost, date or result) → dismissed: `.court/DISMISSED.md` says what is
  missing and what would make it triable. No sub-agents, no verdict.
- **A fact the verdict depends on is missing** → at most three questions, asked once. An answer you
  cannot give is written as `NOT PROVIDED` and the jury weighs the gap.
- **Unrelated evidence, or several cases in one** → dismissed with a table of what relates to what,
  the one case worth trying, and what to cut.
- **After a dismissal**, nothing can be tried until `court.py dismiss --clear`: bring the evidence,
  update `case.md`, clear, run again.
- **Insisting** on a case with no numbers needs `court.py init --force`; the verdict then rests on an
  empty record.

## How it works

`skills/court/court.py` does the bookkeeping: it weighs the filing (`plan`, `dismiss`), opens the trial,
writes one brief per sub-agent, checks that every output exists, counts the votes and renders the
verdict. The orchestrator decides which of those to run, but it cannot open a trial on a case with no
evidence: `dismiss` leaves a marker that `init` refuses, and `init` itself rejects a case file with no
number, cost, date or result in it unless it is passed `--force`. The orchestrating agent only
orchestrates: it never argues a side, never votes and never edits the verdict. The jurors are in
`skills/court/jurors.json`.

```bash
python3 court.py plan    [--jury N | --quick]              # size and cost, no state
python3 court.py dismiss --reason thin|scattered --note "..."   # write the dismissal record
python3 court.py dismiss --clear                            # allow a trial again
python3 court.py init    --case-file .court/case.md [--jury N | --quick] [--seed S] [--force]
python3 court.py next                                       # what phase is next
python3 court.py prompts <opening|rebuttal|jury|judge>      # write briefs, list the jobs
python3 court.py check   <phase>                            # which outputs are still missing
python3 court.py tally
python3 court.py render                                     # VERDICT.md
```

```bash
uv run python -m unittest discover -s tests
```

## Making a video or post about this?

Go ahead. Credit it like this, in your caption or description:

```text
Pi court skill by Cristiano Gariboldo (Pixel3Design): github.com/pixel3design-hub/Pi.dev-court-skill
Based on the original court skill: github.com/alexyc9381/court-skill
```

Every verdict the skill writes already ends with that credit, so leave it in the shot. Questions or a
bug: social@pixel3design.it.

Writing about it or citing it in a paper? Use **Cite this repository** in the sidebar on GitHub.

## Uninstall

```bash
pi remove git:github.com/pixel3design-hub/Pi.dev-court-skill
```

Not made by Anthropic or Pi. The jury is made of language models, so treat the verdict as a structured
second opinion, not legal, financial or professional advice.

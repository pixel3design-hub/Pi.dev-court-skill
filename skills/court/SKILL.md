---
name: court
description: >-
  Put an idea on trial in front of a jury of 12 sub-agents. A prosecutor argues
  it fails, a defense argues it works, they rebut each other, 12 jurors with
  different backgrounds vote on their own, and a judge reads the verdict and
  the conditions that would flip it. Use when the user wants honest pushback
  instead of agreement, says the model just agrees with everything, asks "is
  this a good idea", wants an idea, plan, pitch or claim stress-tested, or says
  "court" or "put it on trial". It weighs the evidence first: a case with none is
  dismissed, missing facts are asked for, and a pile of unrelated evidence is sent
  back to be reorganised instead of tried.
license: MIT
metadata:
  author: "Cristiano Gariboldo (Pixel3Design)"
  email: "social@pixel3design.it"
  homepage: "https://pixel3design.it"
  source: "https://github.com/pixel3design-hub/Pi.dev-court-skill"
  based-on: "https://github.com/alexyc9381/court-skill"
  version: "1.0.0"
---

# court

For when the model agrees with everything you say. Instead of one polite answer, the idea goes on
trial: a prosecutor builds the case against it, a defense builds the case for it, and a jury of
sub-agents who never see each other votes. You are the clerk of the court. You never argue, never
vote, and never soften the verdict.

Usage: `/skill:court [--jury N | --quick] [--seed S] <the idea, plan or claim>`

The user's text after `/skill:court` arrives as a request appended to these instructions: that is the
case. If it is blank, or still reads like a placeholder, take the case from the conversation: the
idea, plan or claim the user most recently wanted an opinion on.

## The tool

This skill needs Pi with the sub-agents extension: `pi install npm:@tintinweb/pi-subagents`. The `Agent`
tool comes from it, and without it there is no jury.

Every piece of bookkeeping goes through `court.py` next to this file:

```bash
python3 "<this skill's directory>/court.py" <command>
```

Below, `COURT` means exactly that command. Take "this skill's directory" from the path listed for this
skill in your system prompt. The state lives in `.court/<run>/state.json` in the current directory,
and every command after `init` finds it through `.court/LATEST`.

If `python3` is blocked or missing here, run the same commands as `uv run python "<dir>/court.py" ...`.

## Step 1: size it

Read the flags out of the request. Everything that is not a flag is the case.

| flag | meaning |
| --- | --- |
| `--jury N` | N jurors, 3 to 12. Default 12. |
| `--quick` | 6 jurors. |
| `--seed S` | Fixes which jurors sit on a smaller jury. Default: random, and recorded. |

Run `COURT plan` with the same flags and tell the user in one line how big the trial is, for example
"12 jurors, 17 sub-agent calls", then go on to the evidence check. If this skill fired on its own
(the user never asked for a trial), ask once first and offer `--quick`.

Sub-agents write into `.court/` in the current directory. Pi does not ask for approval per tool call;
check the run folder afterwards rather than changing the user's settings.

## Step 2: write the case file

**Sub-agents cannot see this conversation.** The prosecutor, the defense, every juror and the judge
know only what is in the case file, so write `.court/case.md` to stand on its own:

- First line: the case in one sentence, in the user's own words where you can ("Quit my job to sell
  candles on Etsy full time").
- Then everything the user told you that matters: numbers, audience, budget, timeline, what they have
  already tried, constraints.
- Do not add facts the user never gave, and do not write your own opinion of the idea into it. A case
  file that leans one way decides the trial before it starts.
- Where a fact the verdict needs is missing, write `NOT PROVIDED` instead of guessing. The evidence
  check in the next step reads those markers.

## Step 3: weigh the evidence

Before the trial spends 17 sub-agents, check the filing. Read `.court/case.md` once and count what is
actually evidence: a number, a named source, a result the user already got, a cost, a date, a
constraint they have hit. A wish, a feeling or a plan to find out later is not evidence. The charge
the evidence has to bear on is always the same: does the case fail as stated, should it not go ahead
the way it is described?

| what you find | what you do |
| --- | --- |
| no evidence, or one claim with nothing behind it | **dismiss** |
| a fact the verdict obviously depends on is absent | **ask**, at most 3 questions, once |
| more than one case, or evidence that does not bear on the charge | **dismiss and reorganise** |
| a few concrete facts that bear on the charge | run the trial |

**Dismiss, thin.** Do not run `init` and do not launch a single sub-agent. Dismiss it with the tool,
which writes `.court/DISMISSED.md` and blocks any later `init` until it is cleared:

```bash
COURT dismiss --reason thin --note "The case: <one line>
What is missing: <the facts a jury would need to reach a verdict>
What would make it triable: <2 or 3 concrete things to bring back>"
```

Show what it printed, add at most two lines of your own, and stop. Dismissing is a verdict here, not a
failure. When the user comes back with the missing evidence, update `.court/case.md` and run
`COURT dismiss --clear` before opening the trial.

**Ask, incomplete.** A missing fact decides the outcome, so ask before the trial, not after. One
message, at most 3 questions, each answerable in a line: "What did each candle cost you, all in?" not
"tell me about your costs". Wait for the answer, write it into `.court/case.md`, and weigh once more.
If a fact is still missing, write `NOT PROVIDED` next to it in the case file and go on: the jury is
allowed to weigh the gap, and it is allowed to punish it.

**Dismiss and reorganise, scattered.** The file holds more than one case, or the evidence does not
touch the charge. Do not run `init`. Dismiss it with the mapping in the note:

```bash
COURT dismiss --reason scattered --note "| what the user gave | what it is about | bears on the charge? |
|---|---|---|
| ... | ... | ... |

The one case worth trying: <one line>
Cut or set aside: <2 or 3 items>
Bring back: <the evidence that one case needs>"
```

Then ask the user to reorganise into a single case with its own evidence, and offer to start again.

You are still the clerk: this step decides whether there is a case to try, never whether it wins.
Never invent a fact to save a thin case. `init` refuses a case file with no number, cost, date or
result in it at all; if the user insists on a trial anyway, write the gaps into the case file as
`NOT PROVIDED` and pass `--force`, and say in one line that the verdict rests on an empty record.

## Step 4: open the trial

```bash
COURT init --case-file .court/case.md [--jury N | --quick] [--seed S]
```

If it exits with "this case was dismissed", the record is still there: clear it with
`COURT dismiss --clear` once the evidence is in.

## Step 5: the trial

Always drive it with `COURT next`. It reads the files on disk and tells you the next phase and the
exact command. The phases run in this order: `opening`, `rebuttal`, `jury`, `judge`.

Every phase works the same way:

1. `COURT prompts <phase>` writes one brief per job and lists the jobs still to run.
2. Launch the **whole phase in one message**: one Agent tool call per job, all foreground. Each call is:
   - `subagent_type`: `general-purpose`
   - `description`: `court <job id>`
   - `prompt`: `Read <brief path> and follow it exactly. It is your whole brief.`
   - `run_in_background`: `false`

   Tool calls in one message run in parallel and a foreground call returns its result inline, so the
   phase is finished when the slowest agent in it returns. That is 4 blocking rounds for the whole
   trial (opening, rebuttal, jury, judge), not 17. Launching one job per message, or waiting for a
   couple of agents before starting the rest, serializes the trial and makes it too slow to use.
3. After the phase, run `COURT next`. If an output is missing it sends you back to the same phase,
   and `prompts` then lists only the missing jobs. Re-run only those, the same way. If a juror fails
   twice, write the single line `NO VOTE` into its file (`COURT check jury` lists it) and move on.
   Never write a vote, a statement or a judgment yourself.

## Step 6: the verdict

When `COURT next` says the trial is over:

```bash
COURT render
```

It counts the votes, writes `VERDICT.md` into the run folder and prints it. Show the user the verdict
line, the vote table and the judge's sections exactly as written. Then add at most two lines of your
own: the single condition for acquittal you would start with, and the path to the full trial.

Rules for you, the clerk:

- Never change, soften or re-count the verdict. A guilty verdict is useful information, not bad news
  to cushion.
- Never add praise the jury did not give.
- If the user disagrees with the verdict, offer a retrial with the changes from "Conditions for
  acquittal" written into a new case file. Do not argue for either side yourself.

---

Pi port by Cristiano Gariboldo (Pixel3Design), social@pixel3design.it. Derived from the original
court skill by Alex Chen: https://github.com/alexyc9381/court-skill. Same trial, same charge, same
verdict format; only the orchestration is Pi's.

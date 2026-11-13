---
name: court
description: >-
  Put an idea on trial in front of a jury of 12 sub-agents. A prosecutor argues
  it fails, a defense argues it works, they rebut each other, 12 jurors with
  different backgrounds vote on their own, and a judge reads the verdict and
  the conditions that would flip it. Use when the user wants honest pushback
  instead of agreement, says the model just agrees with everything, asks "is
  this a good idea", wants an idea, plan, pitch or claim stress-tested, or says
  "court" or "put it on trial".
license: MIT
metadata:
  author: "Alex Chen (@nocodealex)"
  homepage: "https://chen.media"
  source: "https://github.com/alexyc9381/court-skill"
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

## Step 1: size it

Read the flags out of the request. Everything that is not a flag is the case.

| flag | meaning |
| --- | --- |
| `--jury N` | N jurors, 3 to 12. Default 12. |
| `--quick` | 6 jurors. |
| `--seed S` | Fixes which jurors sit on a smaller jury. Default: random, and recorded. |

Run `COURT plan` with the same flags and tell the user in one line how big the trial is, for example
"12 jurors, 17 sub-agent calls", then start. If this skill fired on its own (the user never asked for
a trial), ask once first and offer `--quick`.

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

## Step 3: open the trial

```bash
COURT init --case-file .court/case.md [--jury N | --quick] [--seed S]
```

## Step 4: the trial

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

## Step 5: the verdict

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

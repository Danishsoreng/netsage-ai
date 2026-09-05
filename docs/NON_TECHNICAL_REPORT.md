# NetSage AI — Project Report

**A network fault triage assistant with a human in the loop**

Prepared for practical evaluation. Written to be readable without a
networking or programming background.

---

## 1. The problem in one paragraph

When a computer in an office cannot reach a server, the person reporting it
only knows the symptom: *"it isn't working."* Behind that symptom there are at
least six different things that could be wrong, and they are all invisible from
the outside. A junior network engineer knows how to run the diagnostic
commands, but does not yet have the experience to know *which* one to run
first, or how to read the answer. So they check things one at a time, more or
less in the order they happen to remember them. That is slow, and it is where
most of the time on a "cannot connect" ticket actually goes.

**NetSage AI narrows that guess.** It takes the symptom plus whatever
diagnostic output has been collected, and proposes the single most likely
cause, with the evidence for it and the one command that would confirm it.

---

## 2. The single most important design decision

**The AI never has the final word.**

The system proposes. A person decides. Every proposal sits in a queue marked
*pending* until a human marks it **Accepted**, **Edited**, or **Rejected**.
There is no path anywhere in the code by which the AI's answer becomes the
official answer on its own.

This matters for a practical reason, not just an ethical one: language models
produce confident-sounding text whether or not they are right. A tool that
quietly acted on that would be worse than no tool, because it would send a
junior engineer confidently in the wrong direction. Making the human decision a
required step is what makes the tool safe to give to the exact person who is
least equipped to catch its mistakes.

A second safeguard sits alongside it, described in section 4.

---

## 3. What happens when a case goes through the system

Think of it as four stations on a line.

**Station 1 — Collect.**
A case is written down: what the user reported, notes about how the network is
wired, and the output of whatever diagnostic commands were run. The project
ships with 30 such cases already prepared, covering every fault category.

**Station 2 — Automatic checks.**
Before any AI is involved, an ordinary computer program reads the case and
looks for mechanical mistakes it can be *certain* about — two machines given
the same address, an invalid setting, a switch port switched off. These are
facts, not opinions.

**Station 3 — AI proposal.**
The AI reads the same case, plus the facts from Station 2, and writes a
proposal: the likely cause, which part of the network it sits in, how confident
it is, what evidence it used, what command to run next, and how to fix it.

**Station 4 — Human decision.**
A person opens the case on screen, sees everything above laid out together, and
decides. If they disagree, they write down what was actually wrong and why. That
disagreement is kept permanently.

---

## 4. Why there are two separate checkers

This is the part worth emphasising in a viva, because it is the design choice
that carries the most weight.

| | Automatic checks (Station 2) | AI proposal (Station 3) |
|---|---|---|
| How it works | Fixed rules written by hand | A language model reasoning over text |
| What it can find | A small set of specific mistakes | Almost anything, in principle |
| Can it be wrong? | Only if the rule itself is wrong | Yes, and it can be wrong confidently |
| Same input, same answer? | Always | Not guaranteed |

Neither is sufficient alone. The rules are reliable but narrow. The AI is broad
but fallible. Running both means an obviously wrong AI answer gets contradicted
on screen by something that cannot make things up — and the reviewer sees the
contradiction immediately rather than having to catch it themselves.

---

## 5. What was actually built

Five pieces, all working:

1. **A database** holding four kinds of record — the cases, the automatic
   findings, the AI proposals, and the human decisions. The AI's answer and the
   human's answer are stored in *separate tables* so the two can never be
   confused, and so the system can always answer the question "how often was the
   AI right?"

2. **The automatic rule checker** — eight checks covering address conflicts,
   invalid settings, misconfigured gateways, ports that are switched off,
   missing routes, and the specific signature of a name-lookup failure.

3. **The AI assistant** — it asks the model for its answer in a fixed,
   structured format, so every proposal has the same fields and can be compared
   and counted. If no AI service is configured, a local backup engine takes
   over so the whole system still runs and can still be demonstrated. Every
   proposal records which of the two produced it, so the results are never
   silently mixed.

4. **A scheduled pipeline** that runs the four stations in order, on a
   timetable, without anyone starting it by hand. It re-reads the case folder
   each run and picks up anything new. Notably, this pipeline contains *no* step
   that applies a fix or approves a proposal — those are human-only.

5. **A web console** with three screens: the queue of cases awaiting review, the
   detail view where a case is reviewed, and a dashboard summarising what kinds
   of faults appeared, how severe they were, and how often the AI and the human
   agreed.

---

## 6. The dashboard, and how to read its numbers honestly

The dashboard reports two different things that are easy to confuse.

**Agreement rate** — of the proposals a human has actually reviewed, how many
were accepted without change. Unreviewed proposals are counted as *pending*,
never as correct. If nothing has been reviewed, the dashboard says so rather
than showing a flattering blank.

**Category match** — how often the AI put a case in the same category as the
recorded label. This number looks impressive and should be presented with a
caveat: it is measured on the same 30 cases the system was built around, so it
demonstrates that the system works consistently on known cases. **It is not a
measure of real-world accuracy**, and the dashboard says so on screen. Claiming
otherwise would be exactly the kind of overstatement this project is meant to
guard against.

The honest summary is: the system is demonstrated working end to end on a
prepared case set. Accuracy on genuinely unseen faults has not been measured,
and measuring it would require running it against real tickets over time.

---

## 7. The responsible AI log

Every proposal a reviewer edits or rejects appears automatically in a log on
the dashboard, showing what the AI said, what the human said instead, and why.

Nobody has to remember to file these. They accumulate as a by-product of doing
the review, which is the only way a record like this survives contact with a
busy team. Over time this log is what tells you whether the assistant is worth
keeping, and which categories of fault it handles badly.

---

## 8. Who this is for

- Junior network engineers and trainees, who get a starting point instead of a
  blank page
- Helpdesk and first-line support, who can rule out the obvious before
  escalating
- Senior engineers, who review proposals rather than diagnosing every ticket
  from scratch
- Teaching labs, where the recorded outcome for each case lets a student
  compare their own reasoning against what was actually wrong

---

## 9. What it does not do

Stated plainly, because knowing the limits is part of the work:

- It does not connect to live network equipment. It reads command output that
  someone has collected and pasted in.
- It does not apply fixes. It describes them.
- It cannot diagnose anything outside its eight rules and the categories it was
  given examples of.
- Its accuracy on unseen real-world faults is unmeasured.
- The 30-case set is prepared for a lab, not sampled from real tickets.

---

## 10. Suggested demonstration

1. Show the queue — 30 cases, all pending, colour-coded by which part of the
   network the fault sits in.
2. Open case NS-004 (two machines sharing an address). Point out that the
   automatic checker found the conflict with certainty, before any AI ran.
3. Open case NS-001. Read the AI proposal aloud: cause, confidence, evidence,
   next command, fix.
4. Deliberately mark it **Edited**, and write in what was actually wrong.
5. Go to the dashboard and show that the correction appeared in the responsible
   AI log by itself.
6. Close on the point from section 2: the AI proposed, the human decided, and
   the disagreement was recorded rather than lost.

---

## 11. One-sentence summary

*NetSage AI turns a vague network complaint into a specific, evidence-backed
proposal about what is wrong — while requiring a person to approve it, and
keeping a permanent record of every time that person disagreed.*

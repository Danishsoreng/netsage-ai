# NetSage AI, explained end to end

**What the tool does, the networking it rests on, and what every box on every
screen is for.**

Written to be read by someone with general networking knowledge and no
programming background. A shorter, higher-level version of the same argument is
in [`NON_TECHNICAL_REPORT.md`](NON_TECHNICAL_REPORT.md).

---

## 1. The problem it solves

When someone says *"the internet isn't working"*, they have told you almost
nothing. Behind that one sentence sit at least eight genuinely different
faults, and from the outside they all look identical.

A machine that cannot reach a file server might have been handed the wrong
address, or put on the wrong VLAN, or blocked by a firewall rule, or be sitting
behind a router with no route to the destination. An experienced engineer
narrows this down in about thirty seconds, because they have seen each of these
a hundred times and know which command distinguishes them. A junior engineer
knows all the same commands — they just do not yet know which one to run
*first*. So they work through them roughly in the order they happen to
remember, and that is where most of the time on a "cannot connect" ticket
actually goes.

**NetSage AI narrows the first guess.** You give it the symptom in plain words
plus whatever command output you have already collected. It gives you back one
named root cause, the specific lines of evidence it rests on, the single
command that would confirm or kill it, and the fix.

### The one design decision that matters

**The AI never has the final word.** Every proposal sits marked *pending* until
a person presses Accept, Edit, or Reject. There is no code path anywhere in the
project by which the AI's answer becomes the official answer on its own.

This is a practical safeguard, not just an ethical one. A language model writes
confidently whether or not it is right. A tool that silently acted on that
would be *worse* than no tool, because it would send the least experienced
person in the room confidently down the wrong path. Requiring the human
decision is what makes it safe to hand to exactly the person least equipped to
catch its mistakes.

> **Say it like this:** NetSage turns a vague complaint into a specific,
> evidence-backed proposal — and then insists a human signs it off, keeping a
> permanent record of every time that human disagreed.

---

## 2. The networking it rests on

The 30 sample cases cover eight fault categories. They are not arbitrary — they
are the recurring ways a small campus network breaks.

| Category | Cases | What it is, and how it fails |
| --- | --- | --- |
| `ROUTING` | 6 | A router moves traffic *between* networks using a routing table — "to reach network X, send it this way". If the destination is not in the table and there is no **default route** (the "gateway of last resort", meaning "anything I don't recognise, send here"), the packet is dropped. The PC works perfectly on its own network and fails the moment it tries to leave it. |
| `VLAN` | 5 | A **VLAN** slices one physical switch into several separate logical networks. Ports in VLAN 10 behave as if they are on a different switch from ports in VLAN 30. It fails when a port is left in the wrong VLAN after a room is repatched. The link between switches is a **trunk**, carrying several VLANs at once; a VLAN missing from the trunk's allowed list dies at the uplink. |
| `ACL` | 4 | An **access control list** is a firewall rule: a top-to-bottom list of permit and deny statements. First match wins, and there is an invisible "deny everything else" at the bottom. Traffic that should pass gets caught by a deny line sitting above the permit line that would have allowed it. Everything else works, which is what makes it confusing. |
| `DHCP` | 3 | **DHCP** hands out IP addresses automatically — address, subnet mask, default gateway, DNS server. It fails when the pool is exhausted, or when the server sits on another VLAN with no `ip helper-address` to forward the request. The giveaway is a **169.254.x.x** address: the PC giving up and assigning itself one. It can talk to nothing. |
| `DNS` | 3 | **DNS** turns names into addresses. The signature failure is unmistakable: `ping 192.168.30.10` works, `ping fileserver` does not. The network is healthy; only the phone book is broken. |
| `NAT` | 3 | **NAT** rewrites private internal addresses into public ones on the way out and back on the way in. It fails when a translation is missing or points at the wrong host, or when `ip nat inside`/`outside` is on the wrong interfaces. Internal traffic is fine; anything leaving the site breaks. |
| `PHYSICAL` | 3 | Layer 1 — the cable, the port, the optic. A port left `shutdown` shows as *administratively down*. A failing patch lead shows as rising CRC errors. Unglamorous and very common. |
| `OTHER` | 3 | Address-level configuration mistakes: two machines with the same IP, an invalid subnet mask, a gateway outside the PC's own subnet. |

### Three terms the tool uses constantly

**Subnet mask.** Written like `255.255.255.0`, it tells a PC which part of its
address is "my street" and which is "my house number". With that mask,
`192.168.10.25` understands that `192.168.10.1`–`192.168.10.254` are neighbours
it can reach directly. Anything else must be handed to the gateway.

**Default gateway.** The router's address on the PC's own network — the exit
door. It must sit *inside* the PC's own subnet, or the PC cannot reach it and
nothing leaves the local network at all. This is a real check the tool
performs.

**OSI layer.** A model for locating a fault by *height* rather than by name.
Every proposal is tagged with one, because it tells you where to point your
torch.

| Layer | Concerned with | A fault here looks like |
| --- | --- | --- |
| Layer 1 | Cables, ports, optics, signal | No link light; port administratively down |
| Layer 2 | Switching within one network — VLANs, MACs, trunks | Cannot reach machines on your own floor |
| Layer 3 | Addressing and routing between networks — IP, DHCP, NAT | Own network fine, everything else unreachable |
| Layer 4 | Ports and sessions — TCP/UDP, most ACLs | Ping works but the application does not |
| Layer 7 | The application itself — DNS, HTTP | Addresses work, names do not |

> **Say it like this:** naming the layer is half the diagnosis. "It's Layer 2"
> means stop looking at the router and go look at the switch port.

---

## 3. How a case flows through the system

Four stations, always in the same order. The order is the point.

```
 TWO WAYS IN                    STATIONS                 WHAT GETS WRITTEN

 triage console  ─┐      ┌──────────────────┐
 (one case)       ├────▶ │ 01 COLLECT       │ ──────────▶  cases
 airflow @hourly ─┘      │ symptom + output │              what was reported
 (30 case files)         └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐
                         │ 02 RULE CHECK    │ ──────────▶  rule_findings
                         │ 8 fixed checks   │              what is certain
                         │ no AI            │
                         └────────┬─────────┘
                                  │ findings passed in as FACTS
                                  ▼
                         ┌──────────────────┐
                         │ 03 AI PROPOSAL   │ ──────────▶  diagnoses
                         │ one root cause   │              what AI proposed
                         └────────┬─────────┘
                                  ▼
                         ┌──────────────────┐
                         │ 04 HUMAN DECIDES │ ──────────▶  reviews
                         │ accept·edit·     │              what the person
                         │ reject           │              decided
                         └──────────────────┘
```

Both entry points run the *same* code. The console posts one case at a time to
the JSON API; Airflow walks the case folder in batch. There is no second
implementation of the logic anywhere.

### Why two checkers instead of one

|  | Rule checker (station 2) | AI assistant (station 3) |
| --- | --- | --- |
| How it works | Fixed rules written by hand in ordinary Python | A language model reading the case as text |
| What it can find | A small set of specific, mechanical mistakes | Almost anything, in principle |
| Can it be wrong? | Only if the rule itself is wrong | Yes — and it can be wrong *confidently* |
| Same input, same answer? | Always | Not guaranteed |

Neither is sufficient alone. The rules are reliable but narrow; the AI is broad
but fallible. Running both means an obviously wrong AI answer gets contradicted
*on the same screen* by something that cannot make things up — and the reviewer
sees the contradiction immediately instead of having to catch it themselves.

---

## 4. The eight automatic checks

These live in `app/rule_checker.py`. No AI at all — plain pattern-matching and
arithmetic on the pasted text. Same input twice gives the same answer twice,
which is exactly the property the AI cannot offer.

| Check | Severity | What it looks for, and why that is a fault |
| --- | --- | --- |
| `DUPLICATE_IP` | high | Two devices with the same IP. Both work intermittently, because the switch keeps changing its mind about which one owns the address. |
| `INVALID_SUBNET_MASK` | high | A mask that is not a valid unbroken run of 1-bits — `255.255.0.255`, say. Converts the mask to binary and looks for a `0` followed by a `1`, which can never occur in a legal mask. |
| `GATEWAY_OFF_SUBNET` | high | The default gateway is not inside the host's own subnet, so the PC cannot reach its own exit door and nothing leaves the local network. Calculated properly from address and mask, not guessed. |
| `APIPA_ADDRESS` | high | An address starting `169.254.` — the self-assigned range a PC falls back to when no DHCP server answered. Certain proof the request went unanswered. |
| `INTERFACE_DOWN` | high | A line reading *administratively down* or *down down*. Someone shut the port and never re-enabled it, or the cable is dead. |
| `NO_DEFAULT_ROUTE` | medium | A routing table saying *gateway of last resort is not set*. The router has no instruction for anything outside its directly attached networks. |
| `VLAN_SUBNET_MISMATCH` | medium | Devices tagged with the same VLAN but sitting on two different subnets. One of those ports is almost certainly in the wrong VLAN. |
| `DNS_RESOLUTION_FAILURE` | medium | The classic DNS signature: a name lookup failing (*non-existent domain*, *NXDOMAIN*) in the same output as a *successful* IP ping. Both halves must be present. |

> **Say it like this:** if the checker says two hosts share an address, that is
> a fact, not an opinion. The AI cannot overrule it — and because the finding is
> fed into the AI's prompt, the AI has to reason around a truth it cannot
> ignore.

Each rule is wrapped so that if one crashes the other seven still run, and the
failure is recorded as a finding rather than taking the page down.

---

## 5. Screen 1 — the triage console (`/`)

The main screen, and the one to demonstrate. It runs left to right: describe
the fault on the left, watch the certain checks fire, read the proposal on the
right, decide.

```
 ┌───────────────────────────────────────────────────────────────────┐
 │ A  header — reviewer · case ref once saved · which engine answered │
 ├───────────────────────────────────────────────────────────────────┤
 │ B  01 describe → 02 rule check → 03 ai proposal → 04 you decide    │
 ├──────────────────────────────┬────────────────────────────────────┤
 │ C  What is broken?           │ E  AI proposal                     │
 │    symptom                   │    root cause · type · layer       │
 │    topology notes            │    confidence bar                  │
 │    paste show output         │    EVIDENCE                        │
 │    [Run diagnosis] [Clear]   │    RUN THIS TO CONFIRM             │
 │                              │    THEN FIX IT                     │
 ├──────────────────────────────┼────────────────────────────────────┤
 │ D  Rule checker   2 of 8     │ F  YOUR DECISION  ◀── the gate     │
 │    HIGH GATEWAY_OFF_SUBNET   │    [Accept] [Edit] [Reject]        │
 │    HIGH INTERFACE_DOWN       │    reviewer notes                  │
 │                              ├─────────────────┬──────────────────┤
 │                              │ G Ask about     │ H Review log     │
 │                              │   this case     │                  │
 └──────────────────────────────┴─────────────────┴──────────────────┘
```

Certainty on the left (box D, which cannot be wrong), the model's opinion on
the right (box E, which can), and the decision that settles it in box F.

### A — Header strip

Three pieces of status worth pointing at during a demo. **Reviewer** is who the
decision is recorded against. The middle slot reads *"no case open"* until you
run a diagnosis, then flips to *"case LIVE-0002 saved"* — your proof the case
reached the database, not just the screen. **Engine** says `claude` or
`heuristic`, so you always know which produced what you are reading.

If the middle slot turns red, the server was unreachable and nothing was saved.

### B — Progress strip

The four stations, lit as you pass through them. It makes the sequence visible:
the rule check genuinely happens before the AI proposal, and the human decision
genuinely comes last.

### C — "What is broken?", the intake form

Three fields. **Symptom** in ordinary words, as the user reported it.
**Topology notes** (optional) — how the kit is wired, and the host list the rule
checker parses for addresses, masks, gateways and VLANs. **Paste show output** —
raw text from `show ip route`, `show ip interface brief`, `show interfaces
trunk`, or whatever you ran.

**Run diagnosis** sends all three to the server. *Load example case* fills them
with a worked example so you can demo without typing. It refuses an empty case
rather than inventing one.

### D — Rule checker panel

How many of the eight checks fired, then each one: severity, code, plain
message, and the exact line it fired on. Red for high, amber for medium.

If nothing fires it says so, and warns explicitly that the AI proposal below
rests on the symptom text alone and its confidence deserves more suspicion.
That warning is deliberate.

### E — AI proposal

Always the same seven fields, which is what makes proposals comparable and
countable:

- **Root cause** — one sentence naming a single cause, not a list of maybes
- **Fault type** — one of the eight categories
- **OSI layer** — where to point your torch
- **Confidence** — 0 to 1, drawn as a bar; below 0.55 the case is flagged
- **Evidence** — the specific lines it used, so you can check its reasoning
- **Run this to confirm** — one command, with a copy button
- **Then fix it** — numbered steps

Evidence and the confirming command are the two fields that make the proposal
falsifiable.

### F — Your decision (the gate)

The most important box on the site. **Accept** records agreement. **Edit** opens
a field where you write what was *actually* wrong — and the AI's original
wording is kept alongside yours, not overwritten. **Reject** records that the
proposal was no use. A free-text notes field records what you found on the
device.

Until you press one of these the case stays *pending* forever. This is the only
action in the whole project that writes to the `reviews` table.

### G — "Ask about this case", the chatbot

Follow-up questions in plain language: *"why not a spanning-tree loop?"*,
*"explain MTU mismatch to me like I'm new"*. It is given the symptom, the rule
findings and the current proposal as context, so it answers about *this* case
rather than in general.

It is read-only — it cannot change the proposal or the decision. With no API key
configured it says plainly that no engine is reachable rather than inventing an
answer.

### H — Review log

A running, timestamped list of decisions taken this session, colour-coded.
Immediate confirmation that the decision landed.

The footer carries two standing disclaimers, always on screen: *reads pasted
output, not live devices · proposes fixes, does not apply them*, and the names
of the four tables.

---

## 6. Screen 2 — the overview (`/overview`)

The wide-angle view. Every number is read live from the database on page load.
Nothing on it is typed in or stored.

```
 ┌───────────────────────────────────────────────────────────────────┐
 │ A  "AI proposes the root cause. A person decides."                │
 ├──────────────┬──────────────┬──────────────┬──────────────────────┤
 │ B     30     │      17      │      30      │        2             │
 │  cases       │ rule findings│  diagnoses   │  reviewed by         │
 │  ingested    │   raised     │  produced    │  a person            │
 ├──────────────┴──────────────┴──────────────┴──────────────────────┤
 │ C  01 INGEST · 02 RULE CHECKER · 03 AI DIAGNOSIS · 04 HUMAN REVIEW│
 ├───────────────────────────────────┬───────────────────────────────┤
 │ D  Review queue    30 pending     │ E  Spotlight case             │
 │    NS-001  no default route  0.82 │    evidence + confirming cmd  │
 │    NS-002  no DHCP reply     0.90 │    [Accept] [Edit] [Reject]   │
 ├───────────────────────────────────┼───────────────────────────────┤
 │ F  Correction log                 │ G  What this figure is not    │
 │    every edit or rejection        │    the match rate + caveat    │
 └───────────────────────────────────┴───────────────────────────────┘
```

**A — Hero statement.** The project's thesis, stated before any number is shown.

**B — The four counters.** One per table. Read left to right and you see how far
the work has got: cases in, mechanical findings raised, proposals produced, and
how many a human has actually signed off. Diagnose a case on the console, come
back, and "cases ingested" has gone up by one.

**C — Pipeline stages.** The four stations as cards. Card 04 is worth reading
aloud: *"the only place a proposal is confirmed"*.

**D — Review queue.** Every case with a proposal no human has decided on:
reference, proposed root cause, OSI layer, confidence. Low confidence is drawn
in amber. Clicking a row opens that case's full review page. The heading always
names the real total even though only the first eight rows are drawn.

**E — Spotlight case.** The first pending case in full: evidence, confirming
command, and Accept / Edit / Reject. Accept and Reject write straight to the
database and the page refreshes itself; Edit opens the full review page,
because editing needs a text box.

**F — Correction log.** Every proposal a human edited or rejected, showing what
the AI said and what the human said instead. **Nobody files these.** They
accumulate as a by-product of doing reviews, which is the only kind of record
that survives contact with a busy team. Over time this is what tells you
whether the assistant is worth keeping, and which fault categories it handles
badly.

**G — "What this figure is not".** The category-match percentage, with its
caveat printed beside it rather than in a footnote. See section 9.

---

## 7. The other three screens

Plain server-rendered pages reading the same four tables.

**`/queue` — Review queue.** Every case as a list, with a tally across the top
of how many are pending, accepted, edited and rejected. Colour-coded by OSI
layer. The working list a reviewer opens at the start of a shift.

**`/case/<ref>` — Case detail, the full review page.** One case laid out in the
order you would actually read it: **Evidence collected** (symptom, topology
notes, command output) → **Deterministic checks** → **AI proposal** (all seven
fields) → **Human decision** (decision, reviewer, corrected root cause, notes,
Save).

For the 30 seed cases there is one extra panel: **Recorded outcome**, the
ground truth of what was actually wrong. That is what makes the seed set useful
for teaching — a student can compare their own reasoning, and the AI's, against
the real answer.

**`/dashboard` — Dashboard.** The measurement screen:

- **Counters** — cases, proposals, reviewed, pending
- **Faults by type** — bar chart across the eight categories, showing the case
  mix is not lopsided
- **Faults by severity** — high / medium / low
- **Human decisions** — accepted vs edited vs rejected
- **How often the AI agreed with the human** — the agreement rate, with a plain
  statement when nothing has been reviewed yet
- **Responsible AI log** — a table of every correction: case, decision, what
  the AI said, what the human said, notes

---

## 8. The database — four tables, and why

| Table | Holds | Written by |
| --- | --- | --- |
| `cases` | Symptom, topology notes, raw command output — and for seed cases the recorded true cause, category, layer and severity | Ingest, or the console |
| `rule_findings` | One row per check that fired: code, severity, message, evidence line | The rule checker |
| `diagnoses` | One row per AI proposal: the seven fields, plus which engine produced it and the raw reply | The AI assistant |
| `reviews` | The decision, reviewer, corrected root cause, notes, timestamp | **Only a human** |

**Why the AI's answer and the human's answer are in separate tables.** If a
correction overwrote the AI's proposal, the record of the disagreement would be
destroyed — and with it any ability to answer "how often was the assistant
right?" a month later. Keeping `diagnoses` and `reviews` apart means both
answers survive, side by side, permanently.

Every row in `diagnoses` also records its `engine` — `claude` or `heuristic` —
so results from the two are never silently mixed when you count them up.

**The offline engine.** If no API key is configured, the AI stage falls back to
a local engine built from keyword signatures and the rule findings. It is
deliberately not disguised: the engine name is stored on every row and shown on
screen. The whole system therefore demonstrates end to end with no internet and
no API cost — and you can still tell exactly which answers came from a model
and which did not.

---

## 9. Reading the numbers honestly

Two figures are easy to confuse, and one is easy to overclaim.

**Agreement rate.** Of the proposals a human has *actually reviewed*, how many
were accepted without change. Unreviewed proposals count as *pending*, never as
correct. If nothing has been reviewed, the page says so rather than showing a
flattering blank.

**Category match.** How often the AI put a case in the same category as the
recorded label. It looks impressive and should always be quoted with its
caveat:

> It is measured on the same 30 seed cases the system was built around. It
> shows the system behaves **consistently on known cases**. It is **not** a
> measure of real-world accuracy, and accuracy on genuinely unseen faults is
> unmeasured. The screen says exactly this, next to the number.

Saying this before you are asked is stronger than being caught by it. It is
also the same discipline the whole project argues for: do not let a
confident-looking output stand in for a verified one.

---

## 10. Limits, stated plainly

- **It does not touch live equipment.** It reads command output someone has
  collected and pasted in.
- **It does not apply fixes.** It describes them. Both facts are printed in the
  console footer permanently.
- **The rule checker's text parsing assumes the layout used in the seed cases.**
  Real device output varies by vendor and version; the patterns would need
  widening.
- **Accuracy on unseen faults is unmeasured**, and measuring it properly would
  mean running against real tickets over time.
- **The 30-case set is prepared for a lab**, not sampled from a real helpdesk.
- **PostgreSQL and the Airflow scheduler are written but not yet run here.** The
  code paths exist and the DAG compiles; the demo runs on SQLite.

Listing these yourself is not a weakness in a viva. It shows you know where the
edges of your own work are, which is most of what "responsible AI" means in
practice.

---

## 11. A six-minute demonstration

1. **Start on `/overview`.** Read the hero line aloud — "AI proposes the root
   cause, a person decides" — and point at the four counters. Say that every one
   of them is read live from the database.
2. **Go to the console at `/`.** Click *load example case*, so there is no
   typing. Point at the progress strip before pressing anything.
3. **Press Run diagnosis.** Narrate the order as it happens: the rule checker
   fires first, its findings appear on the left, and only then does the proposal
   arrive on the right. Say explicitly that those findings were sent to the AI
   as facts.
4. **Read the proposal's evidence and confirming command.** Make the point that
   the proposal is *falsifiable* — it tells you how to prove it wrong.
5. **Deliberately press Edit** and type a different root cause. Point out that
   the header now reads "case saved", and that the AI's original wording is
   kept, not overwritten.
6. **Return to `/overview`.** Your correction is already in the correction log
   and the counters have moved — nobody filed anything.
7. **Close on the caveat panel.** Read "what this figure is not" aloud, and
   finish on the point from section 1: the AI proposed, the human decided, and
   the disagreement was recorded rather than lost.

---

## 12. Questions you will probably be asked

**What stops the AI from just being wrong?**
Nothing stops it being wrong — that is the premise. What the design does is make
wrongness *visible and cheap*: the rule checker contradicts it on the same
screen with facts it cannot fabricate, the proposal must cite its evidence and
name a command that would disprove it, and no proposal counts until a person
signs it off.

**Why run the rules before the AI and not after?**
Because findings passed in as established facts change what the model produces.
Run afterwards, they would only be a contradiction to notice; run before, they
constrain the answer.

**Why is confidence a number rather than "high / low"?**
So it can be thresholded and counted. Anything below 0.55 is flagged in the
interface, and the number can be compared across proposals later.

**What does Airflow actually add here?**
Scheduling and repeatability. It re-reads the case folder hourly, runs the four
stages in order, and picks up anything new without anyone starting it. The DAG
contains orchestration only — no diagnosis logic — so the console and the batch
run genuinely share one implementation.

**Could this be automated end to end?**
Technically yes, and that is exactly what was designed out. The value of the
tool is narrowing the first guess for someone who does not yet have the
experience to do it themselves. Removing the human would remove the one thing
standing between a plausible wrong answer and a change to a live network.

**What would you do next?**
Run it on real tickets to get an accuracy figure that means something; widen the
rule checker's text patterns to handle other vendors' output formats; and use
the correction log to find which fault categories the assistant handles badly,
then either add rules for them or narrow what it is allowed to claim.

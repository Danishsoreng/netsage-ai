# NetSage AI — UI package

Two Design Components. **Both are now served by the Flask app and talk to the
real backend** — start the server (`python run.py`) and open
<http://127.0.0.1:5000/>. Opening the files straight off disk still renders the
layout, but every fetch will fail and the pages fall back to their offline
notice, because the API lives on the server.

## Files

- `NetSage Triage.dc.html` — the working triage console, served at `/`.
  Describe a fault, paste show output, and the page POSTs to `/api/triage`,
  which runs `app/rule_checker.py`, hands its findings to
  `app/ai_assistant.py` as facts, and writes rows to `cases`, `rule_findings`
  and `diagnoses`. Accept / edit / reject POSTs to `/api/review`, which is the
  only thing that writes to `reviews`. The chatbot POSTs to `/api/chat`.
  *Load example case* fills it with a deliberately simple demo fault: PC1 sits
  on 192.168.10.x but its default gateway is 192.168.20.1, with an otherwise
  identical PC2 beside it as the control. One check fires
  (GATEWAY_OFF_SUBNET) and the fault is visible to the naked eye, which is what
  makes it worth putting in front of an instructor.
- `NetSage Console.dc.html` — the overview, served at `/overview`. Every
  number, queue row, spotlight case and correction-log entry comes from
  `GET /api/metrics`, read live from the four tables. Nothing on it is a
  stored figure.
- `support.js` — the runtime both files load. Flask serves it at `/support.js`.
- `*.dc.html.orig` — the untouched design-canvas versions, kept for reference.

## How the two halves line up

The browser copy of the rule checker and the browser heuristic are still in
`NetSage Triage.dc.html`, but only as a fallback for when the server cannot be
reached. When that happens the engine label in the header reads `offline` and
the case is **not** saved, so an offline demo is never mistaken for a real run.

The server-side checker (`app/rule_checker.py`) is the authoritative one. Its
codes are DUPLICATE_IP, INVALID_SUBNET_MASK, GATEWAY_OFF_SUBNET, APIPA_ADDRESS,
INTERFACE_DOWN, NO_DEFAULT_ROUTE, VLAN_SUBNET_MISMATCH and
DNS_RESOLUTION_FAILURE. The in-page fallback now mirrors those same eight, code
for code and message for message, so both halves agree on what "8 checks"
means — verified to produce identical output on the same input. If you widen
one, widen the other.

## Notes

Background animation is three.js (CDN, r128) and the runtime pulls React from
unpkg, so **both pages need internet access to render**. The API itself does
not: with no `ANTHROPIC_API_KEY` the server answers from the local heuristic
engine. Tweakable props on both files: accentHue, particleCount,
motionIntensity, tiltStrength.

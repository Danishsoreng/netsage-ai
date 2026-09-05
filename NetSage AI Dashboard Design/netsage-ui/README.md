# NetSage AI — UI package

Two self-contained Design Components. Open either file directly in a browser,
or serve the folder (`python -m http.server`) so support.js resolves.

## Files

- `NetSage Triage.dc.html` — the working triage console. Describe a fault,
  paste show output, 8 deterministic checks run in-browser, the findings are
  passed to the AI as facts, and the proposal goes to a human accept / edit /
  reject with a review log. Includes a case-grounded chatbot.
- `NetSage Console.dc.html` — the marketing / overview dashboard: pipeline
  stages, review queue, correction log, honest-limits panel.
- `support.js` — runtime both files load. Keep it beside them.

## Notes for the Flask port

The rule checker in `NetSage Triage.dc.html` mirrors `app/rule_checker.py`:
IFACE_ADMIN_DOWN, DUPLEX_MISMATCH, CRC_ERRORS, MTU_MISMATCH,
NATIVE_VLAN_MISMATCH, OSPF_STUCK, PORT_SECURITY, DHCP_POOL.

The AI call is a browser-side prompt that returns strict JSON with keys
root_cause, fault_type, osi_layer, confidence, evidence, next_command,
fix_steps — the same shape as the `diagnoses` table. To move this into Flask,
replace the browser call with a POST to a route wrapping `app/ai_assistant.py`
and render the markup as Jinja templates.

Background animation is three.js (CDN, r128). Tweakable props on both files:
accentHue, particleCount, motionIntensity, tiltStrength.

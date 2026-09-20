# UX-1A Screenshots

Screenshots capture the state after UX-1A implementation (2026-09-20).
Browser automation was not available at implementation time.
Each entry describes what the screenshot should show when captured.

## 01-global-nav-before.png
Global navigation bar before UX-1A: `COMMAND | STATE | DECISIONS | MODELS | WORLD | CAPABILITIES | ACTIVITY`
Brand label: `MAIW COMMAND CENTER`
Note: `/demo` route not visible in nav.

## 02-global-nav-after.png
Global navigation bar after UX-1A: `OPERATIONS | WORLD | RELIABILITY | MODELS | CAPABILITIES | ACTIVITY`
Brand label: `MAIW OPERATIONS`
SIMULATED WAREHOUSE indicator visible in header when demo is active.

## 03-recommendation-pre-execution.png
ProposeStage with "No warehouse action has executed yet." notice visible.
AuthorityBoundary rendered between notice and proposal cards.
No model_id or routing_rule visible (expert mode off).

## 04-authority-boundary.png
AuthorityBoundary component rendered in ProposeStage.
Amber color rule line with "MAIW AUTHORITY BOUNDARY" label and subtext.

## 05-approval-state.png
ApproveStage showing HUMAN APPROVAL REQUIRED hero.
Pre-execution notice visible above the APPROVE ACTION button.
Button reads "APPROVE ACTION" (not "APPROVE & EXECUTE").
Sub-label: "Governance approval — execution follows automatically"

## 06-approved-execution-starting.png
After APPROVE ACTION is clicked: "Approved → Execution Starting" transition.
Rail advances to EXECUTE stage via SSE.

## 07-demo-indicator.png
SIMULATED WAREHOUSE indicator visible in the global header.
Visible on /world page (not just /demo).

## 08-expert-details-collapsed.png
ReasonStage with expertMode=false: no model_id, routing_rule visible.
ObserveStage: no snapshot_id visible.

## 09-expert-details-expanded.png
ReasonStage with expertMode=true (Expert toggle on): model_id, routing_rule visible.
ObserveStage: snapshot_id visible.

## 10-policy-approved-notice.png
DecideStage when outcome=APPROVED without human approval required.
"Approved by Policy" card with POLICY_APPROVED_NOTICE text visible.

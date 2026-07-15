# Titan Web App — Living Cognitive Operating System

**Phase:** Titan Web App Finalization — Sprint 2.9  
**Scope:** Frontend-only presence polish (`web/v2/`)  
**Constraint:** No Brain, API, Memory, Voice Runtime, or neural renderer redesign  
**Authority:** `docs/TITAN_DESIGN_CONSTITUTION.md`

---

## Goal

Make Titan feel like a **living Cognitive Operating System** the moment the page loads — calm, attentive, already alive — not a dashboard waiting for clicks.

---

## Visual Summary

| Objective | Result |
|-----------|--------|
| **Presence** | Soft panel breathe, telemetry dots, glass edge light — idle never static |
| **Orchestrator** | New **System Presence** section (Présence, Surveillance, Mémoire, Attente, Exécution) with honest idle truth |
| **Satellites** | Powered idle glow + breath; active remains brighter with stronger path energy |
| **Top telemetry** | Compact strip: Mémoire · Réflexion · Présence · Outils · Mode · Runtime |
| **Bottom cards** | Floating glass workspaces — reflection highlight, deeper blur, quiet float |
| **Composer** | Premium command console — taller, glass, inviting placeholder, refined controls |
| **Micro-interactions** | Hover whisper, focus ring, opacity fades — no spectacle |

---

## Files Changed

| File | Role |
|------|------|
| `web/v2/design/presence.css` | **New** Sprint 2.9 living OS polish (loaded last) |
| `web/v2/index.html` | Loads `presence.css` |
| `web/v2/orchestrator/orchestrator-region.js` | System Presence idle richness |
| `web/v2/center/topbar-region.js` | Mode + Runtime telemetry pills |
| `web/v2/composer/composer-region.js` | Console class + premium placeholder |
| `web/v2/status/status-region.js` | Alive idle card copy |
| `web/v2/core/version.js` | UI version → `0.26.0` |
| `tests/test_web_v2_presence_os.py` | Sprint contracts |

---

## Screenshots

| Shot | Path |
|------|------|
| Idle command center | `docs/design/screenshots/sprint-2.9-living-os.png` |
| Orchestrator presence | `docs/design/screenshots/sprint-2.9-orchestrator.png` |
| Composer console | `docs/design/screenshots/sprint-2.9-composer.png` |

---

## Verification

1. Open `/app` idle — orchestrator shows System Presence with “Aucune active”, not empty chrome.
2. Top bar shows six telemetry pills including Mode and Runtime.
3. Bottom cards read as glass workspaces floating over the neural field.
4. Composer focus: soft red breath, not a heavy neon ring.
5. Satellites idle: subtle glow; active: brighter node + path.
6. Reduced motion: breathing / float animations stop.

---

## Related

- `docs/TITAN_DESIGN_CONSTITUTION.md`
- `docs/WEB_APP_PREMIUM_COMMAND_CENTER.md` (Sprint 2.2)
- `docs/design/TITAN_MASTER_BLUEPRINT.md`

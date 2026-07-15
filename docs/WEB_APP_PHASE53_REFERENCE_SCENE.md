# Titan Web App — Phase 5.3 Reference Scene Reconstruction

**Phase:** Reference Scene Reconstruction (presentation only)  
**Scope:** `web/v2/design/reference-scene.css`, satellite orbit/highway presentation, Core gravity hierarchy, UI version, docs/tests  
**Constraint:** No Brain, API, Memory, Voice Runtime, neural engine logic, routes, or state management changes  
**Canonical visual targets:**
- `docs/design/screenshots/sprint-2.7-reference-composition.png`
- `docs/design/screenshots/phase-5-reference-layout-full.png`

---

## Goal

Stop treating the center as a background.

Recompose the entire application around **Titan Core** so the user immediately feels they entered a living intelligence — a command center, not a dashboard.

Visual read order:

1. **Titan Core** (gravity)
2. **Living neural field** (highways · satellites · tissue)
3. **Interface chrome** (quiet instruments)

---

## What changed

| Surface | Reconstruction |
|---------|----------------|
| **Titan Core** | Dominant elliptical nebula glow · larger typography · gravity well · denser filaments |
| **Satellites** | Organic asymmetric orbits (not a clock grid) matching the reference constellation |
| **Highways** | Major luminous axons + secondary branches + local synapses (SVG presentation) |
| **Atmosphere** | Stronger volumetric fog · near/far particles · bloom · deep void vignette |
| **Floating UI** | Lower opacity / quieter glass — chrome yields to the mind |

---

## Files

| File | Role |
|------|------|
| `web/v2/design/reference-scene.css` | **Visual authority** (loaded last) |
| `web/v2/center/cognitive-satellites.js` | Gravity markup · layered highway paths |
| `web/v2/layout/shell.js` | Phase marker `5.3` / `reference-scene` |
| `web/v2/index.html` | Loads reference-scene CSS; meta `0.43.0` |
| `web/v2/core/version.js` | UI version → `0.43.0` |
| `tests/test_web_v2_reference_scene.py` | Phase 5.3 contracts |
| `scripts/capture_phase53_reference_scene_screenshots.py` | Screenshot capture |

---

## Intentionally untouched

- Neural canvas renderer / tissue seeding / node algorithms / engine JS
- Brain, APIs, routes, voice, memory, agents
- Orchestrator / sidebar / composer behavior wiring

---

## Screenshots

| Capture | Path |
|---------|------|
| Full shell | `docs/design/screenshots/phase-5.3-reference-scene-full.png` |
| Center Core | `docs/design/screenshots/phase-5.3-titan-core.png` |
| Orbit field | `docs/design/screenshots/phase-5.3-satellite-orbits.png` |

---

## Verification

```bash
pytest tests/test_web_v2_reference_scene.py tests/test_web_v2_cinematic_living.py tests/test_web_v2_immersive_neural_stage.py tests/test_web_v2_phase5_layout.py -v
python scripts/capture_phase53_reference_scene_screenshots.py
```

1. Eye lands on TITAN CORE first — not sidebar or cards.
2. Eight satellites orbit with natural asymmetry around the Core.
3. Major highways visibly attach satellites to the Core.
4. Edges are deep void; center blooms with volumetric fog.
5. Floating chrome feels secondary to the living field.

# PMOS design QA — 2026-08-26

- Source visual truth: `/tmp/pmos-audit-2026-08-25/01-mobile-command-center.png`
- Implementation: `http://127.0.0.1:3101/`
- Implementation capture: `/tmp/pmos-qa-2026-08-26/mobile-command-center.png`
- Landscape graph capture: `/tmp/pmos-qa-2026-08-26/relationship-landscape-graph.png`
- Viewports: 390 × 844 portrait and 844 × 390 landscape
- Pixels / density: source 390 × 1884 full-page; implementation viewport captures at CSS size with device scale 1. The comparable region is the first 844 pixels of the source.
- State: public-safe synthetic demo, no private authentication or data

## Full-view comparison evidence

The implementation preserves the source's editorial navy, warm paper, gold accents, serif display hierarchy, readiness card, compact evidence metrics, and high-density institutional tone. The mobile header is intentionally more compact than the source: it retains menu, Search, and Guided Demo as icon controls so the two critical actions remain reachable at 390px without clipping.

The landscape relationship view now displays a visible phone/swipe instruction, explicit left/right controls, a focusable scroll region, and partial next-node disclosure. Measured graph overflow is 1,036px inside a 768px viewport, confirming a real horizontal exploration region.

## Focused region comparison evidence

- Header: typography, paper tone, icon weight, control size, and title hierarchy remain coherent; the compact action treatment prevents the source capture's wider header pattern from overflowing.
- Transaction card: spacing, navy token, readiness visualization, gold exception state, and text hierarchy match the visual system.
- Relationship graph: node borders, connector labels, muted evidence language, and gold real-institution context remain consistent while adding discoverable mobile controls.

## Required fidelity surfaces

- Fonts and typography: Playfair Display and DM Sans hierarchy remains consistent; labels, headings, and numeric emphasis wrap cleanly at both tested viewports.
- Spacing and layout rhythm: 18px mobile gutters, card spacing, internal rules, and responsive stacking are consistent. No page-level horizontal overflow was observed.
- Colors and visual tokens: navy, paper, gold, green, amber, and line tokens remain consistent with the source.
- Image quality and assets: no raster imagery is required. Interface icons use the existing Phosphor icon library; no placeholder or handcrafted SVG assets were introduced.
- Copy and content: public/private distinctions remain explicit. Orientation guidance says rotation is optional, and the guided restitution step names the exact counsel action.

## Interaction and accessibility verification

- Mobile navigation, data-boundary modal, scoring drawer, Search, guided tour, synthetic role selection, counsel acknowledgement, and relationship graph controls were exercised.
- Guided state and counsel acknowledgement survive route transitions and reloads.
- Keyboard focus, dialog semantics, scroll-region labeling, disabled acknowledgement state, and icon-button accessible names are covered by browser tests.
- Browser error overlay: none.
- Browser page errors: none.
- Automated result: 14 Playwright scenarios passed across desktop and mobile.

## Comparison history

- P1: Guided demo reset after route navigation and counsel acknowledgement had no durable UI state. Fixed by moving both into versioned persistent demo state and adding a contextual counsel action inside step 2. Post-fix browser test passes through reload.
- P1: Mobile/landscape graph relied on undiscoverable overflow. Fixed with swipe guidance, arrow controls, scroll snapping, touch panning, and partial-node affordance. Post-fix measurement and browser test confirm horizontal movement.
- P2: Mobile header actions clipped at 390px. Fixed with a three-column header and accessible compact Search/Guided Demo icon controls. Post-fix portrait capture shows both controls.
- P1: The supplied 1068 × 590 @2x landscape capture showed route labels colliding with the absolutely positioned active-vertical and privacy controls. Source: `/tmp/codex-remote-attachments/01a03aac-c632-7f51-8e34-7ddf871452a8/2E44E272-AA3D-4437-850F-FF4D7CABD5F1/1-Photo-1.jpg`.
- Fix: converted the drawer to a 100dvh flex layout, made routes independently scrollable, placed the footer in normal flow, and used a two-column landscape route grid. Implementation: `/tmp/pmos-qa-2026-08-26-drawer/mobile-landscape-drawer.png`, captured at 534 × 295 CSS pixels / device scale 1 to normalize the source's 2× pixels.
- Post-fix evidence: route region ends at y=223; footer begins at y=227. All seven routes, active vertical, privacy control, and close control are visible with no overlap. Browser page errors: none.

### Landscape drawer fidelity surfaces

- Fonts and typography: existing DM Sans labels remain legible at compact landscape sizes; active route weight and hierarchy are preserved.
- Spacing and layout rhythm: 4px separation between independently bounded route and footer regions; footer controls align on a two-column baseline.
- Colors and visual tokens: navy, active blue, gold, white, and muted text match the supplied screenshot's established PMOS system.
- Image quality and assets: the drawer uses the existing Phosphor icon set and PMOS mark; no replacement raster or handcrafted SVG assets were introduced.
- Copy and content: all route names remain intact, with Verification added as the user-requested adjudication workflow. Privacy and active-vertical labels remain explicit.

No actionable P0, P1, or P2 findings remain. A future P3 refinement could animate the graph-edge focus state when an arrow control is used.

final result: passed

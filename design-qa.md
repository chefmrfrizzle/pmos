# PMOS design QA

- Source visual truth: `/tmp/pmos-audit-2026-08-25/01-mobile-command-center.png`
- Final mobile implementation: `/tmp/pmos-design-qa/implementation-mobile-final2.png`
- Final desktop implementation: `/tmp/pmos-design-qa/implementation-desktop-final.png`
- Source pixels: 390 × 1884; implementation pixels: 390 × 1914
- CSS viewport: 390 × 844 mobile, 1280 × 900 desktop
- Device scale factor: 1; no density normalization required
- State: command center, navigation closed, no dialog

## Full-view comparison evidence

The source and final mobile capture were inspected together at equal 390px width. The implementation preserves the source navy/ivory institutional palette, display-serif hierarchy, compact sans-serif metadata, two-column metric cards, readiness and collector panels, and horizontal relationship graph. The extra 30px height is an intentional consequence of adding public-boundary copy and a mobile Search control.

The desktop capture preserves the same hierarchy with a fixed navigation rail, two-column analysis region, and a contained horizontal graph. Browser checks confirmed a 1280px viewport and 1280px document width.

## Focused comparison evidence

Focused captures inspected: `/tmp/pmos-design-qa/mobile-navigation-open.png` and `/tmp/pmos-design-qa/mobile-boundary-modal.png`. The drawer has a visible close control and dimmed scrim; the boundary modal clearly separates public and never-public content. These states did not exist in the static source and intentionally extend it.

## Required fidelity surfaces

- Typography: Playfair Display and DM Sans hierarchy, weights, wrapping, and compact uppercase metadata remain consistent with the source.
- Spacing/layout: card spacing, panel rhythm, gutters, radii, and desktop/mobile grids are consistent. No document-level overflow remains.
- Colors/tokens: navy, ivory, gold, supported green, and review amber preserve the source semantic system and sufficient visible contrast.
- Image quality: the interface has no raster-image dependency. Product icons use the Phosphor icon library; no placeholder image or improvised emoji remains.
- Copy/content: fictional transaction labeling is stronger, and real institution identity is explicitly separated from transaction involvement.

## Findings

No actionable P0, P1, or P2 mismatch remains. P3: the mobile header is slightly denser than the source because Search is now intentionally available there.

## Comparison history

1. P2 found: the first desktop capture had 1390px document width in a 1280px viewport; a long graph expanded the grid.
2. Fix: added `min-width: 0` to grid children and contained the graph with horizontal overflow.
3. Post-fix evidence: desktop document width equals 1280px; mobile document width equals 390px. Final captures were re-opened and inspected.

## Interaction and browser evidence

Six Playwright cases pass across Chromium desktop and mobile: mobile navigation, boundary modal, ranking drawer, search, institutional filtering, official-source links, keyboard focus, and Escape-to-close. The browser showed no Next.js error overlay. Loading, error, not-found, and offline routes are present.

## Follow-up polish

- Add a compact icon-only Search treatment below 360px if ultra-small-device support becomes necessary.
- Run screen-reader announcements with VoiceOver in a future native-device pass.

final result: passed

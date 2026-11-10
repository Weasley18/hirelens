# HireLens interface

A compact, high-contrast assessment workspace with a custom overlapping-lens motif. The interface
supports human judgment and explicitly labels simulated output; decorative graphics never imply
that an actual model is available or that an assessment is a hiring decision.

- Canvas: pale sage #f1f3eb. Text: #172421. Analysis surface: deep green-black #152722 with a soft radial glow.
- Accent: citron #d2f474, used for the headline highlight, main action, and alignment visualization.
- Typography: locally available Helvetica Neue/Arial; large tightly spaced headlines, restrained
  monospace labels, legible document input. No externally hosted font dependency.
- Layout: compact header and single-line desktop headline above two independent workspace cards;
  stacked cards on mobile. Four-row document fields, tighter section spacing, and three small preview
  cards keep the workspace prominent. Panels size to their content; the input card stays visible on
  tall desktop screens. Inputs lock to the
  submitted document pair until deletion so results cannot appear alongside edited documents.
- Motion source: [Emil Kowalski, Animate](https://github.com/emilkowalski/skills/blob/main/skills/animate/SKILL.md),
  reviewed online 2026-11-06, with its button/stagger recipes. Applied directly for this task;
  no third-party executable or globally installed skill was required.
- Motion purpose: short entrance staging clarifies hierarchy; button feedback acknowledges input;
  the lens sweep only runs during actual processing. Results use short staggered reveals.
- Shared ease-out: cubic-bezier(.23,1,.32,1); 160ms control feedback, 300ms entrances, 50ms result
  staggering. Animation changes only transform/opacity. Constant progress uses linear rotation.
- Reduced motion removes all rotation/translation while preserving gentle fades and static status.
  Hover effects are restricted to fine pointers. Inputs, navigation, and privacy details work by keyboard.

# Interview Portal — Design System v3 ("Warm Editorial")

Derived from three Stitch explorations (see `scratchpad/stitch/REVIEW.md`). The chosen synthesis:
**Direction B (Editorial Precision) is the spine behind the login; Direction C's warmth and bento
composition is used on candidate-facing and marketing surfaces; Direction A contributed the
candidate application-card + stepper composition.** Nothing is glassmorphic — A's glass was dropped
for density and dark-mode contrast reasons.

Two personalities, ONE token ramp:

| Surface | Personality | Radii | Separation | Density |
|---|---|---|---|---|
| Workspace (recruiter, interviewer, all settings and feature apps) | Editorial: ink on warm paper, hairline rules, bare numerals | 4–6px | 1px rules, almost no shadow | Dense — target ~2x the rows of the old UI |
| Candidate portal, landing, careers, client portal, offer signing, booking, assessment taking | Warm: bento cards, soft borders, generous space | 12–16px | Soft border + one small shadow | Comfortable |

## Tokens (define once in `web/static/web/app.css` on `:root`, dark values under both
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-bs-theme="light"])` and
`:root[data-bs-theme="dark"]`, matching the existing theme mechanism.)

```
/* Paper / ink ramp — warm neutrals, replaces the old cool --ip-slate-* ramp */
--ip-paper-50:  #FDFBF8;   --ip-paper-100: #FAF7F2;   --ip-paper-200: #F3EEE6;
--ip-paper-300: #EAE3D8;
--ip-ink-900: #141210;  --ip-ink-700: #35302B;  --ip-ink-500: #55504A;  --ip-ink-300: #8B847B;
--ip-rule:    #E3DCD1;  --ip-rule-strong: #D3C9BA;

/* Accents: ONE workspace accent (ember) + ONE candidate accent (violet) + lime as a
   BACKGROUND-ONLY highlight. Never put text or an icon in lime on lime, and never use lime
   as a button fill — QA of direction C found invisible lime-on-lime CTAs twice. */
--ip-ember-600: #E14E14;  --ip-ember-500: #FF5A1F;  --ip-ember-100: #FFE8DC;
--ip-violet-600: #5A49E8;  --ip-violet-500: #6D5DF6;  --ip-violet-100: #EFEBFF;
--ip-lime-block: #C6F24E;   /* background blocks / highlight tiles only */
--ip-mint-block: #DFF5EC;  --ip-peach-block: #FFE8D6;

/* Semantic */
--ip-green-600: #137A4C;  --ip-amber-600: #A85B00;  --ip-red-600: #B3261E;

/* Dark mode */
--ip-paper-50: #0F0D0C; --ip-paper-100: #12100E; --ip-paper-200: #1A1714; --ip-paper-300: #241F1A;
--ip-ink-900: #F5F1EA; --ip-ink-700: #D8D1C7; --ip-ink-500: #A8A099; --ip-ink-300: #7C746B;
--ip-rule: #2A2621; --ip-rule-strong: #3A342D;  --ip-ember-500: #FF7A45; --ip-violet-500: #8C7DFF;

/* Type */
--ip-font-head: "Bricolage Grotesque", "Space Grotesk", system-ui, sans-serif;
--ip-font-body: "Manrope", "DM Sans", system-ui, sans-serif;
--ip-font-mono: "JetBrains Mono", ui-monospace, monospace;
headline tracking -0.03em, weights 700/800; body 15px/1.6, weights 400-700;
labels 11-13px, 600, tracking +0.06em, uppercase — use sparingly, never for body copy.
Load both families from Google Fonts with a real system fallback stack.

/* Shape & depth */
--ip-r-sm: 4px; --ip-r-md: 6px;            /* workspace */
--ip-r-lg: 12px; --ip-r-xl: 16px;          /* candidate/marketing */
--ip-shadow-card: 0 1px 2px rgba(20,18,16,.05);
--ip-shadow-pop: 0 8px 24px -6px rgba(20,18,16,.18);   /* dropdowns, slide-overs, modals only */
--ip-space unit stays 8px based (4/8/12/16/24/32/48).
```

Map Bootstrap's variables to these (`--bs-body-bg: var(--ip-paper-100)`, `--bs-body-color:
var(--ip-ink-900)`, `--bs-primary: var(--ip-ember-500)` in the workspace, `--ip-violet-500` on
candidate surfaces via a `.ip-warm` scope class on `<body>`, `--bs-border-color: var(--ip-rule)`).
White-label `{% brand_style %}` must keep overriding the accent — do not hardcode the accent
anywhere a brand colour should win.

## Component rules

- **Nav rail**: solid ink panel (`--ip-ink-900` bg, paper text) on the workspace, 220px, grouped
  labels in the small-caps label style, active item marked with a 2px ember left bar, not a filled
  pill. Plan badge and trial countdown pinned at the bottom. Candidate surfaces keep a light top bar.
- **Tables**: no card box. Hairline rule under a sticky header, rows separated by `--ip-rule`,
  row hover `--ip-paper-200`. Right-align numbers. Never wrap a table in a shadowed card.
- **Kanban**: columns separated by 1px rules, header shows stage name + bare count. Cards are
  paper with a 1px rule, radius `--ip-r-sm`, no shadow; hover raises the rule to `--ip-rule-strong`.
- **Fit score**: a large bare numeral in the headline font (24–28px, weight 800), colour by band
  (green ≥70, amber 40–69, ink-300 below), with a tiny "FIT" label beneath. No pill, no circle.
- **Skill match**: segmented bars (5 segments) rather than a continuous progress bar.
- **Buttons**: solid accent for the single primary action; everything else is an outline button with
  a 1px rule. Workspace buttons use `--ip-r-sm`, candidate ones `--ip-r-lg`. Minimum 40px tap target
  on candidate/mobile surfaces. Contrast must clear AA against its own background — check lime.
- **Slide-over**: for the candidate panel on the board, use a right-hand overlay with a scrim
  (`rgba(20,18,16,.32)`), 480px wide, `--ip-shadow-pop`, focus trap, closes on Escape and scrim
  click. Not a half-width opaque split (all three Stitch runs got this wrong).
- **Bento tiles** (landing, candidate portal, dashboard KPI row): unequal grid, one tile may use a
  `*-block` background, radius `--ip-r-xl`, 1px rule instead of a heavy shadow.
- **Stage stepper**: labelled dots joined by a 2px rule; done = filled green with a check, current =
  ring in the surface accent with a "You are here" chip, future = hollow ink-300. Must wrap
  gracefully at 360px without dangling connectors.
- **Empty states**: keep the existing icon + title + one-line + CTA pattern, restyled.
- **Toasts** keep their current position below the top bar; restyle to paper + rule + accent bar.

## Hard constraints

1. Do not change any user-visible **text**, form field name, URL name, or HTML `id`/`hx-*`
   attribute that tests or HTMX targets rely on. 1291 tests must stay green. Restyle, don't rewire.
2. Keep every accessibility property already won: focus rings, aria-labels on icon buttons,
   AA contrast in both themes, no horizontal body overflow at 360px, `prefers-reduced-motion`.
3. Dark mode must be complete on every screen touched. Every colour comes from a token; never
   define a colour only inside a media query.
4. Wide content (tables, boards, code) scrolls inside its own `overflow-x:auto` container.
5. Motion: transitions ≤180ms on transform/opacity/colour only. No layout-animating effects, no
   backdrop-filter (dropped with direction A).
6. Charts (analytics) keep their existing dataviz palette and behaviour; only the surrounding
   chrome is restyled.

# JEDI color direction, November 2026

The selectable palettes adapt established product-design patterns to JEDI. They use original token combinations and keep JEDI branding. They are not official themes from the referenced companies.

## Research

- [Vercel Geist colors](https://vercel.com/geist/colors): separate page/component surfaces, borders, high-emphasis controls, and readable text. Adaptation: neutral card surfaces, restrained borders, blue informative scores, and dedicated action colors.
- [Atlassian color roles](https://atlassian.design/foundations/color) and [accents](https://atlassian.design/foundations/color/accents): distinguish semantic states from interchangeable category colors, with matching foreground/background families. Adaptation: separate action, success, information, review, and destructive roles; six decorative employer-initial color families.
- [Linear's design refresh](https://linear.app/now/behind-the-latest-design-refresh): tune base neutrals and contrast across interface layers. Adaptation: Carbon uses neutral charcoal surfaces with violet controls, blue scores, mint evidence, amber review notes, and pink category accents.
- [Slack's published brand guidelines, page 17](https://a.slack-edge.com/3f2ae/marketing/img/media-kit/Slack-Brand-Guidelines.pdf): aubergine anchoring and accessible alternatives for blue links and green success states. Adaptation: Workspace pairs a custom plum navigation surface with white content and independently chosen accessible accents.

## Implemented combinations

| Theme | Navigation / page / card | Actions | Informative scores | Positive evidence / compensation | Review | Category accent |
| --- | --- | --- | --- | --- | --- | --- |
| Workspace, default | #321A38 / #F6F7F9 / #FFFFFF | #1559C5 | #175CD3 | #147D52 | #935600 | #6E3FA3 |
| Editorial | #EEE8DD / #F8F5EF / #FFFEFB | #1B4DA3 | #1B4DA3 | #35704B | #8D5614 | #7B4388 |
| Spectrum | #FFFFFF / #F5F5F7 / #FFFFFF | #6246CA | #195CC9 | #087365 | #925700 | #9D3585 |
| Carbon | #111215 / #17181B / #202126 | #B3A2FF | #85BDFF | #82DAB2 | #EFC879 | #C5ADFF |

Employer initials have six deterministic color families. These are decorative placeholders, not official logos or indicators of employer quality. The same employer retains its family when results are reordered. Match reasons retain their text; review notes retain their count and disclosure; chart values remain readable without relying on color.

## Implementation and verification

- Palette definitions: `frontend/src/styles/themes.css`. Sidebar foreground, muted text, selected state, focus ring, and destructive hover use sidebar-specific tokens so the split-surface theme remains readable.
- Top-right selector: `frontend/src/components/theme-controls.tsx`. Unsupported saved values from the former palette set migrate to Workspace. Valid selections persist across reloads.
- Salary and match reasons use success tokens; actions use primary; score graphics use information; unknown details use warning; errors use destructive. Histogram series and application stages have distinct readable colors.
- Checked all four themes on populated dashboard, personal feed, Jobs, intake, preferences dialog, and mobile layouts with controlled API responses. Text-token pairs are checked against a 4.5:1 contrast target; this does not constitute a full accessibility audit.
- Further review: real-device rendering, assistive technologies, charts with every application stage, and continued visual review with real account data.

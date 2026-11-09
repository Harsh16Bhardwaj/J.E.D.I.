# JEDI interface direction

The visual direction is quiet dark surfaces, jade accents, original geometric
illustrations, and motion that follows an interaction or explains a state change.
Keep the strongest visual moments on the landing. Inside the app, make the next
action clear and keep evidence readable.

## Delivered

- Cinematic landing and original SVG sentinel, with scroll reveals, motion pause,
  reduced-motion support, and a field guide.
- Minimal workspace navigation, a single active destination, collapsible Legacy
  tools, responsive page header, and keyboard-accessible page search.
- Original orbit and journey SVGs in the personal feed, sign-in, and application
  empty state. Small page-entry and hover animations respect reduced motion.
- Sign-in with calmer typography, a matching visual panel, password visibility,
  and field-error associations. Existing authentication behavior is retained.
- Mobile feed summaries use compact rows to reduce scrolling before the shortlist.

## Next priorities

1. **Resume evidence review.** Group confirmed, uncertain, and missing evidence;
   expand source excerpts in place. Show a clear before/after when a member
   corrects a fact. Every visual indicator needs a text equivalent.
2. **Application journey.** Improve stage summaries, next-action prominence, and
   event history. Animate a move only after the server confirms it; preserve the
   card and explain recovery when a move fails. Keep keyboard alternatives.
3. **Scraper source analytics.** Show actual yield and repeated failures by source,
   alongside data freshness and adapter issues. Charts need accessible tables and
   distinct loading, zero-results, and unavailable states. Avoid decorative stats.
4. **Personal onboarding.** Use a short, reviewable sequence for roles, preferences,
   and resume facts. Offer clear progress and recovery without hiding optional
   steps or imposing unnecessary animations.
5. **A consistent asset set.** Extend the original illustrations to blocked,
   empty, success, and learning states. Prefer small inline SVGs and reuse shapes.
   Keep decorative animation out of data-heavy tables and live run logs.

## Quality gates

- Verify 320px mobile, tablet, desktop, zoom, keyboard-only use, and reduced motion.
- Keep command destinations filtered by the same permissions as navigation.
- Check focus restoration, scroll containment, and screen-reader names in dialogs.
- Use realistic, explicitly labelled fixtures for visual QA. Do not present sample
  counts or scores as live product data.
- Track route bundle size and interaction responsiveness as the UI expands.
- Add repeatable visual regression coverage for the main shells and state variants;
  current browser checks are scripted local checks, not a CI visual baseline.

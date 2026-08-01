# JEDI repository instructions

These instructions apply to the entire repository.

## Keep changes reviewable

- Break work into humanly manageable, coherent chunks before editing.
- A single coherent code change must not exceed 1,000 changed lines or 10 files
  unless the user explicitly approves a larger change.
- If the requested work exceeds either limit, finish and validate one coherent
  chunk, report its boundary, and wait for review before continuing.
- Do not combine unrelated cleanup, refactors, or feature work into the same
  chunk merely because they are nearby.
- Preserve user-authored changes and comments. Treat them as requirements unless
  they conflict with a newer explicit instruction.

## CSS changes

- Before adding or changing CSS, search the existing stylesheets and components
  for the class name and the style already responsible for that element.
- Prefer modifying the existing class in its current stylesheet.
- Do not duplicate an existing class, replace an entire stylesheet, or overwrite
  unrelated declarations when a targeted edit is sufficient.
- Add a new class only when no existing class has the same responsibility.

## Validation

- Validate each chunk in proportion to its risk before handing it back for
  review.
- Report the files changed, the checks run, and any remaining caveats.

# Compatibility Refactor Checklist

Use this checklist for any PR that moves exported code or replaces an implementation behind an existing import surface.

## Before Implementation

- List every affected export surface.
- Separate canonical behavioral surfaces from legacy alias surfaces.
- Decide which surfaces require import continuity only versus runtime patch compatibility.
- Document the supported compatibility contract in one place before adding routing code.

## During Implementation

- Keep canonical composition semantics in canonical modules.
- Make legacy alias routing a thin boundary adapter.
- Avoid adding framework-specific routing branches unless a minimal reproducer proves they are required.
- Prefer explicit override projection over implicit recursive dispatch.
- Ensure self-delegating wrapper overrides are recursion-safe on every supported wrapped export.

## Tests

- Keep import/signature continuity tests separate from behavioral compatibility tests.
- Add focused regression tests for each supported alias behavior.
- Add at least one negative-scope test proving legacy override context does not leak into unrelated canonical calls.
- Do not let one large extraction contract file become the de facto specification for unsupported behaviors.

## PR Review Gate

- Include a short export inventory in the PR description.
- State which compatibility promises are intentionally preserved.
- State which previously implicit behaviors are intentionally not preserved.
- Require targeted verification output for the affected compatibility suites before merge.

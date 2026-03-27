# v3.4.7-v3.4.8 Compat Audit And Remediation Plan

## Scope

This note reviews the `v3.4.7` refactor and the follow-up `v3.4.8` patch train for org writer compatibility routing. It is intentionally design-first. The goal is to stop the regression pattern rather than land another narrow compat fix.

The replacement compatibility boundary is defined in `docs/ORG_WRITER_COMPAT_CONTRACT.md`.

Reviewed history:

- `v3.4.7` (`a043c1e`): modular split of `org.writers` plus first-generation compat wrappers
- `v3.4.8` work-in-progress (`2d0c683..c73bfd3`): nine follow-up compat fixes on top of the split

High-level churn:

- `v3.4.7` changed 26 files and replaced the monolithic `org.writers.__init__` implementation with split modules plus a new compat layer.
- `v3.4.8` added roughly 3k more lines, with most behavioral churn concentrated in `src/cja_auto_sdr/org/writers/compat.py` and `tests/test_output_extraction_contracts.py`.
- The follow-up commits are a repair train, not independent improvements. That is the strongest signal that the current compat design is too complex for the guarantees it is trying to provide.

## Findings

### 1. Source-surface `override_scope()` self-delegation still recurses on compat wrappers

Status: confirmed locally on current `feature/v3.4.8-patch-release`

The current compat wrapper chooses a source-surface self override as `current_target`, but in the non-reentry path it invokes that override with the same source override still active. That means the common wrapper/spying pattern below is unsafe:

```python
with override_scope(
    "cja_auto_sdr.org.writers",
    {"_format_trending_timestamp_short": custom},
):
    ...
```

where `custom()` delegates to `cja_auto_sdr.org.writers._format_trending_timestamp_short(...)`.

Relevant code:

- `src/cja_auto_sdr/org/writers/compat.py:517-528`
- `src/cja_auto_sdr/org/writers/compat.py:621-670`
- `src/cja_auto_sdr/org/writers/__init__.py:159-276`
- `src/cja_auto_sdr/generator.py:5201-5285`

Reproduced locally:

- Package root helper self-delegation:
  `RecursionError maximum recursion depth exceeded`
- Generator helper self-delegation:
  `RecursionError maximum recursion depth exceeded`
- Canonical module self-delegation through `make_override_proxy()` does work, which shows the problem is specifically the compat wrapper path rather than `override_scope()` in general.

This is not a corner case. It is the natural implementation style for wrappers, spies, metrics hooks, and partial overrides.

### 2. The compat layer now behaves like a recursive dispatcher, not a thin boundary shim

The original `v3.4.7` compat design was a small boundary adapter: collect legacy monkeypatches from the old surface and apply them while calling the canonical implementation.

The current `v3.4.8` compat layer now also does all of the following:

- supports mixed string and tuple override destinations
- projects source-surface `override_scope()` entries into target modules
- special-cases self override routing
- tracks suppressed compat targets in context
- introspects `unittest.mock` frames
- walks `__wrapped__` and `_mock_wraps` chains
- unwraps mock/wrap layers to find reentry targets
- treats package-root helper re-exports, writer entrypoints, canonical exports, and generator exports as one shared routing problem

Relevant code:

- `src/cja_auto_sdr/org/writers/compat.py:316-338`
- `src/cja_auto_sdr/org/writers/compat.py:416-514`
- `src/cja_auto_sdr/org/writers/compat.py:588-673`

This is the architectural smell behind the regression train. The module is trying to preserve too many patch surfaces, at too many layers, with runtime routing rules that are hard to reason about.

### 3. Stable API boundaries and internal composition boundaries are currently mixed together

Canonical writer modules already have a coherent override mechanism:

- `call_override(...)` at internal composition points
- `make_override_proxy(...)` on canonical exports

Relevant code:

- `src/cja_auto_sdr/org/writers/common.py:89-108`
- `src/cja_auto_sdr/org/writers/common.py:194-203`

That model is simple and internally consistent.

The regressions start when package-root and generator re-exports are asked to preserve the same internal patchability guarantees as canonical modules, including for private helpers. That creates a compatibility matrix across:

- canonical module exports
- package-root re-exports
- generator re-exports
- nested helper calls
- monkeypatch
- `override_scope()`
- `Mock(wraps=...)`
- manual wrapper delegation

This is too much implicit surface area for a patch release compatibility layer.

## Root Cause Summary

The releases did not just modularize org writers. They also tried to preserve deep monkeypatch and override behavior across every legacy alias surface, including private helpers. That turned the compat layer into a re-entrant dispatcher with framework-specific recursion handling.

The core design mistake is treating "legacy import compatibility" and "legacy patch-surface compatibility" as the same requirement.

Import compatibility is reasonable.
Behavioral equivalence for patching every private helper re-export across every alias surface is much more expensive, much more fragile, and currently under-specified.

## Recommended Direction

Do not keep extending the current routing state machine.

Instead, split the problem into two explicit layers:

### Layer A: canonical implementation surface

This is the only place where nested helper composition should be override-aware.

Rules:

- Canonical modules own internal composition.
- Canonical modules use `call_override()` and `make_override_proxy()` only.
- Canonical modules define the supported override behavior.
- Canonical modules are the only surface allowed to preserve deep helper patch semantics.

### Layer B: legacy alias surface

This should be a thin import-compat facade, not a second composition/runtime-routing system.

Rules:

- Package-root and generator aliases forward to canonical exports.
- Legacy aliases may preserve direct entrypoint monkeypatch compatibility where required for back-compat.
- Legacy aliases should not re-implement deep recursive override semantics for private helper chains.
- If a legacy alias must remain override-aware, its routing must reuse the same self-suppression behavior as `make_override_proxy()` and must not introduce mock-specific branches.

## Concrete Remediation Plan

### Phase 1: freeze the target behavior

Before code changes, document which patch surfaces are truly supported after modularization.

Required decisions:

1. Which exported names are part of the compatibility contract?
2. Which of those are public entrypoints versus private helper conveniences?
3. Which patch mechanisms are supported on each surface?
4. Are package-root and generator helper re-exports required to support nested helper patching, or only direct call interception?

My recommendation:

- Full behavioral compatibility for canonical module exports
- Direct-call compatibility for legacy entrypoints
- No promise of deep helper-chain patch equivalence across every legacy alias surface unless explicitly required

This narrows the problem to something testable and supportable.

### Phase 2: collapse compat routing to one model

Refactor `org.writers.compat` so there is one recursion-safe rule for self overrides:

- when a compat wrapper dispatches to an override for the same exported symbol, suppress that symbol's source override while invoking the override body
- do this regardless of whether the override is a plain function, `Mock(wraps=...)`, or some other callable
- treat mock handling as an optimization only if it remains necessary after simplification, not as the main routing model

Target outcome:

- compat self-overrides behave like `make_override_proxy()`
- `override_scope()` wrapper delegation is safe
- manual wrappers and spies work without requiring `unittest.mock` internals

### Phase 3: reduce the number of legacy-wrapped symbols

Audit the package-root and generator re-exports and stop wrapping private helpers that do not need runtime patch translation.

Prefer this order:

1. writer entrypoints
2. direct builder entrypoints
3. only the minimum helper exports needed for explicitly supported compatibility cases

The current `org.writers.__init__` package-root loop over every trending helper is a red flag:

- `src/cja_auto_sdr/org/writers/__init__.py:201-213`

That loop magnifies both state complexity and regression surface.

### Phase 4: split tests by contract level

The current extraction contract file is carrying too many roles.

Split tests into:

- canonical override semantics
- legacy import compatibility
- legacy entrypoint patch compatibility
- explicitly approved helper compatibility cases
- regression reproductions for known failures

Add a dedicated regression test for the exact manual delegation pattern that currently fails:

- package-root `override_scope()` self override that calls the same exported function
- generator `override_scope()` self override that calls the same exported function

Those tests should exist even if the long-term decision is to narrow the supported surface, because they force an explicit decision rather than accidental behavior.

### Phase 5: add release gates for refactors that move exported code

For future modularization/refactor PRs, require:

1. a compatibility inventory listing every moved export
2. a boundary decision for each export: canonical-only, alias-safe, or full compat
3. a focused regression suite for every compatibility promise added in the PR
4. a rule that patch releases may not expand compat state machinery without an accompanying design note

## What I Would Review Next

In order:

1. A contract inventory for `org.writers` and generator re-exports
2. A compat redesign that makes self-suppression unconditional for same-symbol overrides
3. A reduction pass on legacy helper wrappers, especially package-root trending helpers
4. A test split that makes supported behavior obvious instead of inferred from one large contract file

## Short Recommendation

Do not ship another incremental compat hardening commit on top of the current state machine.

Use the next review round to approve a narrower, explicit compatibility contract and then rework `org.writers.compat` to be a simple, recursion-safe boundary adapter. The current design is carrying too much implicit behavior for a patch-release line and is the main reason regressions keep escaping.

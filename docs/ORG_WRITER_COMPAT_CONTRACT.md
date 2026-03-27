# Org Writer Compatibility Contract

This document defines the supported compatibility surface for the org writer split introduced in `v3.4.7` and reset in the replacement `v3.4.8` work.

## Goals

- Preserve import continuity for existing callers.
- Preserve explicit patch/override behavior where that compatibility is intentional and supportable.
- Keep canonical composition semantics in the canonical writer modules.
- Avoid treating every legacy alias as a second implementation surface.

## Canonical Surfaces

Canonical writer modules are the primary behavioral contract:

- `cja_auto_sdr.org.writers.console`
- `cja_auto_sdr.org.writers.json`
- `cja_auto_sdr.org.writers.excel`
- `cja_auto_sdr.org.writers.markdown`
- `cja_auto_sdr.org.writers.html`
- `cja_auto_sdr.org.writers.csv`

Supported behavior on canonical surfaces:

- direct imports remain stable
- `override_scope()` applies at the explicit `make_override_proxy()` and `call_override()` composition points defined in those modules
- module-local helper proxies may use wrapper-style self overrides that delegate back to the same canonical composition point

`cja_auto_sdr.org.writers.common` and `cja_auto_sdr.org.writers.trending` remain the implementation sources for shared helpers, but this reset does not add a blanket direct-call `override_scope()` contract to every helper-only export there.

## Legacy Alias Surfaces

Legacy alias surfaces remain available for compatibility:

- `cja_auto_sdr.org.writers` package-root writer entrypoints
- `cja_auto_sdr.generator` org writer helper and writer re-exports

Supported behavior on legacy alias surfaces:

- imports remain stable
- direct calls to explicitly wrapped legacy exports remain supported
- legacy source-surface monkeypatches on mapped helper names continue to flow into canonical writer entrypoints
- legacy source-surface `override_scope()` values on mapped helper names continue to flow into canonical writer entrypoints
- wrapper-style self overrides on explicitly wrapped legacy exports are supported
- legacy helper re-export names remain valid mapping sources for wrapped entrypoints even when the helper itself is not individually wrapped

## Legacy Exports With Runtime Compat Wrappers

The following legacy exports are intentionally wrapped at runtime:

- `cja_auto_sdr.org.writers.write_org_report_console`
- `cja_auto_sdr.org.writers.write_org_report_stats_only`
- `cja_auto_sdr.org.writers.write_org_report_comparison_console`
- `cja_auto_sdr.org.writers.build_org_report_json_data`
- `cja_auto_sdr.org.writers.write_org_report_json`
- `cja_auto_sdr.org.writers.write_org_report_excel`
- `cja_auto_sdr.org.writers.write_org_report_markdown`
- `cja_auto_sdr.org.writers.write_org_report_html`
- `cja_auto_sdr.org.writers.write_org_report_csv`
- `cja_auto_sdr.generator.write_org_report_console`
- `cja_auto_sdr.generator.write_org_report_stats_only`
- `cja_auto_sdr.generator.write_org_report_comparison_console`
- `cja_auto_sdr.generator.build_org_report_json_data`
- `cja_auto_sdr.generator.write_org_report_json`
- `cja_auto_sdr.generator.write_org_report_excel`
- `cja_auto_sdr.generator.write_org_report_markdown`
- `cja_auto_sdr.generator.write_org_report_html`
- `cja_auto_sdr.generator.write_org_report_csv`

Generator helper aliases such as `_normalize_recommendation_for_json` and `_render_distribution_bar` remain part of the legacy import surface, but in this reset they are intentionally not promoted to individually wrapped runtime compat exports.

## Legacy Import-Only Aliases

The following aliases remain import-compatible but are intentionally not wrapped at runtime:

Package-root and generator common-helper aliases:

- `_render_distribution_bar`
- `_format_recommendation_context_entries`
- `_normalize_recommendation_severity`
- `_normalize_recommendation_for_json`
- `_flatten_recommendation_for_tabular`
- `_normalize_org_report_output_format`
- `_validate_org_report_output_request`

Package-root trending-helper aliases:

- all helper names re-exported from `cja_auto_sdr.org.writers.trending` at `cja_auto_sdr.org.writers`

These names are expected to remain identity aliases to the canonical implementation modules. Their purpose is import continuity, not a second layer of runtime compat dispatch.

## Non-Goals

The following are not compatibility goals for the reset work:

- full deep helper-chain patch equivalence across every private package-root helper re-export
- a general recursive dispatcher that tries to emulate every combination of alias, helper, mock, and nested wrap behavior
- treating import compatibility and patch-surface compatibility as the same requirement

## Routing Rules

The reset compat routing follows these rules:

1. Canonical modules own internal composition.
2. Legacy wrappers project a defined set of source-surface helper overrides into canonical target modules.
3. Explicit target-module overrides win over projected legacy overrides.
4. Self overrides are invoked with the matching override key suppressed so wrapper-style delegation reaches the original implementation instead of recursing.

## Test Expectations

Regression coverage should focus on:

- canonical self-override delegation
- legacy wrapped export self-override delegation
- legacy helper override projection into canonical entrypoints
- non-leakage of legacy override context into unrelated canonical calls

Tests should not grow a second implicit contract beyond the behavior listed above.

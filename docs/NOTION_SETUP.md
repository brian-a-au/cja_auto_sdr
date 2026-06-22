# Notion Setup Guide

This guide walks you through setting up the Notion integration for `cja_auto_sdr` from scratch. By the end you will be able to run `cja_auto_sdr <data_view_id> --format notion` and see a Notion page appear under a parent page you control.

For the full command reference, see [CLI_REFERENCE.md](CLI_REFERENCE.md#notion-integration). For the environment variable table, see [CONFIGURATION.md](CONFIGURATION.md#notion-integration-environment-variables). For what the Notion output contains, see [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md).

## What you need

Before you start, confirm that you have the following:

- A Notion workspace where you can create pages and integrations.
- A parent page in that workspace where the SDR pages will be created. You can use an existing page or create a new one.
- A CJA data view ID to publish. This is the same ID you pass to any other `cja_auto_sdr` command.
- Optionally, a Notion database to use as the SDR Registry. The registry is one row per data view, with component counts, a Data Quality status, and a link to the detail page. It is not required for the basic `--format notion` flow.

## How the integration uses Notion

The tool uses the Notion 2025-09-03 API (the data sources API), through `notion-client` version 3.0 or newer. You do not need to configure the API version yourself. The client is pinned for you.

There are two things the tool can write:

1. A detail page per data view, created under your parent page. This is the v3.7.0 behavior and needs only a token and a parent page.
2. A registry database row per data view, if you set up the SDR Registry database (v3.8.0). This is optional.

## 1. Install the notion extra

The Notion integration is an optional extra. Install it before running any Notion command:

```bash
uv pip install 'cja-auto-sdr[notion]'
```

If you run a Notion command without the extra installed, the tool prints this message to stderr and exits:

```
Notion output requires the notion extra.
Install it with: uv pip install 'cja-auto-sdr[notion]'
```

## 2. Create a Notion internal integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations), or open Notion, go to **Settings and members**, and click **Integrations**.
2. Click **New integration**.
3. Give it a name, for example "cja_auto_sdr", and select your workspace.
4. Click **Submit**. Notion shows you the integration's **Internal Integration Token**.
5. Copy the token. It starts with `ntn_` for newer integrations, or `secret_` for older ones.
6. Set it as an environment variable:

```bash
export NOTION_TOKEN=ntn_...
```

Keep this token private. It has access to every page and database that the integration is invited to.

You can also put the token in a `.env` file in your working directory. The tool reads `.env` on startup if `python-dotenv` is installed. A `.env` line looks like `NOTION_TOKEN=ntn_...`. Do not commit `.env` to git.

## 3. Share a parent page with the integration

SDR detail pages are created as children of a parent page. The integration must be invited to that page, or Notion returns a 401 or 403 response. This is the step most people miss.

1. Create a new page in Notion, or pick an existing one, to serve as the parent.
2. Open the page. Click the `...` menu (or **Share**) in the top right.
3. In the **Connections** section, choose **Add connection**, search for the integration name you created in step 2, and select it.
4. Confirm the connection.

The page is now shared with the integration.

### Get the parent page ID

The page ID is the 32 character string at the end of the page URL. For example:

```
https://www.notion.so/My-Parent-Page-abc123def456abc123def456abc123de
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

The ID is `abc123def456abc123def456abc123de`. Copy it and set it:

```bash
export NOTION_PARENT_PAGE_ID=abc123def456abc123def456abc123de
```

## 4. First run

With `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` set, run:

```bash
cja_auto_sdr <data_view_id> --format notion
```

What happens:

- The tool fetches the data view from the CJA API.
- It creates a Notion page under your parent page, titled with the data view name and ID.
- It writes the page ID to `.notion_pages.json` in the current directory, or in `--output-dir` if you set one.

On success, open Notion and check your parent page. A new child page should be there.

Re-running the same command updates the existing page in place. The tool reads the page ID from `.notion_pages.json` and sends an update request instead of creating a duplicate.

To force a brand new page instead of updating, add `--notion-force-new`. The old page is left in Notion and its ID is recorded in `.notion_pages.json` as an orphan, so you can clean it up later. See step 7.

## 5. Optional: set up the SDR Registry database

The SDR Registry is a Notion database that holds one row per data view you have published. Each row has the data view name and ID, component counts (Metrics, Dimensions, Segments, Calculated Metrics, Derived Fields), a Data Quality status, the capture time, the tool version, and a link to the detail page. If you do not need this, skip to step 6.

Unlike a manual setup, you do not create the database properties yourself. The tool defines the schema and creates it for you.

### Bootstrap a new database

Run this once:

```bash
cja_auto_sdr --notion-create-database
```

This creates a new "CJA SDR Registry" database under `NOTION_PARENT_PAGE_ID`, with the full schema, and prints the new database ID to stdout. Copy that value and set it:

```bash
export NOTION_DATABASE_ID=abc123def456abc123def456abc123de
```

From then on, every `cja_auto_sdr <data_view_id> --format notion` run also upserts that data view's row in the registry, keyed by the data view ID, alongside publishing the detail page.

### Attach an existing database

If you already created the database in a previous run, pass its ID instead of bootstrapping a new one:

```bash
cja_auto_sdr <data_view_id> --format notion --notion-database-id <database_id>
```

You can also set `NOTION_DATABASE_ID` in your environment or `.env` file so you do not have to pass the flag every time. Share the database with the integration the same way you shared the parent page (**Add connection**), or the tool gets a 401 or 403 when it writes a row.

### Unset behavior

If `NOTION_DATABASE_ID` is not set and `--notion-database-id` is not passed, `--format notion` runs as in v3.7.0. The tool creates or updates the detail page, but writes no registry row.

## 6. Optional: batch and org-wide publishing

To publish several data views in one run, use batch mode. Notion runs serially, so the tool forces a single worker to avoid concurrent writes to `.notion_pages.json`:

```bash
cja_auto_sdr --batch dv_one dv_two dv_three --format notion --notion-database-id <database_id>
```

To write a lightweight catalog row for every data view in the organization, use the org report with the Notion format:

```bash
cja_auto_sdr --org-report --format notion --notion-database-id <database_id>
```

The org-report catalog fills the name, the data view ID, the metric and dimension counts, the owner, the dates, and a link to the detail page where one already exists. It does not fetch segments, calculated metrics, or derived fields, and it does not run data quality validation, so those count columns are left empty and Data Quality shows `unknown`. It does not create detail pages. For complete rows plus detail pages across many data views, use batch mode instead. See [ORG_WIDE_ANALYSIS.md](ORG_WIDE_ANALYSIS.md) for more.

## 7. Optional: clean up orphan pages

Each time you run `--notion-force-new`, the previous detail page is left in Notion as an orphan and its ID is recorded in `.notion_pages.json`. Over time these add up. To clean them up, preview first:

```bash
cja_auto_sdr --notion-prune-orphans --dry-run
```

This lists the orphan pages that would be archived and makes no changes. Then archive them:

```bash
cja_auto_sdr --notion-prune-orphans
```

The pages are archived, which means they move to the Notion trash and can be restored, not permanently deleted. The current detail page for each data view is never touched. This command needs only `NOTION_TOKEN`. It does not need a parent page or a database. It only cleans up pages that were orphaned by `--notion-force-new` from v3.9.0 onward.

## 8. Maintaining the registry database

As `cja-auto-sdr` adds new registry properties across versions, your existing database may be missing those columns. Rather than recreating the database and losing your historical rows, use `--notion-repair-database` to bring it up to date.

**Inspect the canonical schema first (no credentials required):**

```bash
cja_auto_sdr --notion-print-database-schema
```

This prints the full list of expected property names and their types. Compare it against your database in Notion to spot any gaps.

**Preview, then apply the repair:**

```bash
# Dry run: see what properties would be added (no changes made)
cja_auto_sdr --notion-repair-database --dry-run --notion-database-id <id>

# Apply: add missing properties to the live database
cja_auto_sdr --notion-repair-database --notion-database-id <id>
```

You can also set `NOTION_DATABASE_ID` in your environment so you do not need to pass the flag each time:

```bash
export NOTION_DATABASE_ID=<id>
cja_auto_sdr --notion-repair-database --dry-run
cja_auto_sdr --notion-repair-database
```

**What the repair does (and does not do):**

- **Adds** any properties that exist in the canonical schema but are missing from the database.
- **Reports** any property that exists in the database with a different type than the canonical schema expects (type conflicts are flagged in the output but never changed automatically).
- **Never removes** existing properties or data rows, so historical data is preserved.

After the repair, run a normal `--format notion` publish to populate the new columns for each data view.

## 9. Publish a saved artifact without re-fetching

If you already generated an SDR as a JSON file, you can publish it to Notion without calling the CJA API again:

```bash
cja_auto_sdr --push-to-notion path/to/sdr.json
```

This reads the saved artifact and writes the detail page (and the registry row, if a database is configured).

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Notion output requires the notion extra.` | `notion-client` not installed | Run `uv pip install 'cja-auto-sdr[notion]'` |
| `NOTION_TOKEN is not set.` | Token missing or not exported | `export NOTION_TOKEN=ntn_...`, or add it to a `.env` file |
| `NOTION_PARENT_PAGE_ID is not set.` | Parent page ID missing or not exported | `export NOTION_PARENT_PAGE_ID=<page-id>` |
| 401 or 403 when writing the detail page | Integration not invited to the parent page | Open the parent page, Share, Add connection, pick the integration |
| 401 or 403 when writing a registry row | Integration not invited to the database | Open the database, Share, Add connection, pick the integration |
| `--notion-prune-orphans cannot be combined with ...` | A prune run was mixed with another command | Run `--notion-prune-orphans` on its own, or with `--dry-run` only |
| Cannot find the page or database ID | Unsure where to look | Copy the URL from Notion. The 32 character string at the end of the path, before any `?v=` query string, is the ID |

## Next steps

- [CLI_REFERENCE.md, Notion Integration](CLI_REFERENCE.md#notion-integration): all Notion commands and flags.
- [CONFIGURATION.md, Notion Integration Environment Variables](CONFIGURATION.md#notion-integration-environment-variables): the full environment variable table and how credentials are resolved.
- [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md): the contents of the Notion detail page and the registry database schema.
- [ORG_WIDE_ANALYSIS.md](ORG_WIDE_ANALYSIS.md): the org-report Notion catalog.

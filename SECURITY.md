# Security Policy

## Supported versions

Security fixes are applied to the latest released version of `cja-auto-sdr`.
Upgrade to the newest release before reporting an issue that may already have
been fixed.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository:

<https://github.com/brian-a-au/cja_auto_sdr/security/advisories/new>

Private reporting is turned on for this repository, so you can open a report
without access to the repository.

Do not open a public issue for a suspected vulnerability. Include the affected
version, impact, reproduction steps or a proof of concept, and any suggested
mitigation. Please remove credentials, access tokens, organization and client
IDs, profile contents, sandbox names, live customer resource data, and other
sensitive information from the report.

You should receive an acknowledgement through the private advisory within
seven days. Confirmed issues will be coordinated there until a fix and
disclosure are ready.

## Scope

This tool runs on your own machine or CI runner. It reads Adobe API credentials,
calls the Adobe Customer Journey Analytics APIs, and writes reports to local
files. It can also publish reports to Notion when you ask it to. Reports of the
following kinds are in scope:

- The tool exposes a credential or token, e.g., in a log line, an error
  message, console output, or a generated report.
- The tool writes a credential file that other users on the same machine can
  read.
- Text from a data view, e.g., a component name or description, runs as script
  in an HTML report or as a formula in an Excel report.
- The tool sends data to a destination you did not configure.

Issues in Adobe's services, in Notion, or in third party libraries should go to
the owner of that product. If a library issue affects this tool in a specific
way, you can still report it here.

## How the tool handles sensitive data

- **Credentials.** The tool reads credentials from environment variables, a
  `.env` file, `config.json`, or a profile under `~/.cja/orgs/`. When it writes
  a profile, it sets the file so that only your user account can read it.
  `config.json` and `.env` files are listed in `.gitignore`. Status commands,
  e.g., `--config-status`, show only part of each secret.
- **Report content.** Text from your data views is treated as untrusted. The
  HTML writers escape it before they add it to a page. The Excel writers store
  it as plain text, so a value that starts with `=` does not run as a formula.
- **Output files.** SDRs, snapshots, org reports, and logs contain details about
  your Adobe organization, e.g., data view IDs and component definitions.
  Treat these files as internal data. Review them before you commit them to a
  shared repository or attach them to a public issue.
- **Network.** The tool contacts the Adobe APIs. It contacts the Notion API only
  when you use the Notion options. It pushes snapshots to a git remote only
  when you turn on the git push option for your snapshot repository.

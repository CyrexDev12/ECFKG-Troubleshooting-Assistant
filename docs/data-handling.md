# Data handling and review boundaries

## Included and excluded material

The runtime dataset is original generic synthetic content authorized by the request.
The supplied scope was read solely to extract requirements and diagram structure. It is
not copied into the repository or used as diagnostic evidence. Signatures, personal contact
details and sponsor correspondence are excluded. No restricted product documents, failure
logs, real station configuration, credentials or export-controlled technical data were used.

One NI public overview was accessed as a source candidate. Its metadata and a minimal
paraphrase are in `data/review/public-source-candidates.json`; it is **not approved** and
is **not loaded**. No manufacturer source currently supports any active diagnostic rule.
Public availability and an HTTPS link do not establish permission or technical support.

## Source review procedure

The team's designated data steward should record: proposed source/version and exact
section; public/restricted screening; license and permitted copying/sharing; what claim
the source actually supports; reviewer role, decision date and non-personal approval
record ID; any required sponsor/institutional review. Do not include personal contact
information in the graph. Review a short paraphrase and each proposed mechanism separately.
Quarantine rejected/pending material outside runtime. Only promote sources with a real
approval record. Do not promote the scope, user reports or generated conclusions.

Source schema validation checks reference syntax and local existence, not link reachability,
licensing, legal classification or truth. Authorized reviewers must make those decisions.

## Local storage and access

The app uses in-memory sessions with explicit JSON download. The UI server binds to loopback;
Streamlit telemetry is disabled. The API client ignores proxy environment variables, rejects
redirects and requires HTTPS. In API-assisted mode the configured provider receives symptoms,
recorded observations and retrieved evidence. API keys are not exported or logged by the app.
Provider retention and logging are separate from the application's local storage controls.
Downloads remain under the user's browser/OS storage controls. `.gitignore` excludes user
sessions, private directories, secrets, weights and scratch files. It does not provide
encryption, deletion guarantees, malware scanning or protection from another local user.

The separate Codex development workflow must not be assumed local merely because the
resulting application is local. Keep restricted information out of both workflows. No
local server setting makes the development assistant an approved destination for such data.

The user explicitly authorized an exploratory API route, replacing the local LLM option for
now. Local hosting is deferred. Review the selected API provider/account's permissions and
retention before use. This change does not authorize restricted or proprietary inputs, and
does not establish the scope's deployment or compliance criteria. Institutional endpoint
controls remain outside the application. See `api-setup.md` for configuration and key handling.

## Workspace, backup and retention handoff

Use a team-approved access-controlled repository/workspace for reviewed synthetic/public
material. Assign participant/advisor permissions, choose a backup schedule, test restore,
and agree retention/sharing with the institution and sponsor. Preserve graph versions,
source review records, approved references, case definitions, synthetic results, prompts
and settings. Store real user session exports separately and review them before sharing.
Archive final approved materials in the institution's chosen location. These organizational
steps are pending; this task did not create shared accounts, remote hosting or backups.

## Compliance statement

Implemented controls demonstrate a conservative data-handling approach. They do not
establish legal/ITAR compliance, standards conformity or production suitability. The
scope's acceptance language needs authorized institutional/sponsor interpretation. No
claim of certification, export classification or approved operational use is made.


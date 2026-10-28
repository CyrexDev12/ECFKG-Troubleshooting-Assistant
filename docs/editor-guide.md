# System Knowledge Graph Editor

This local research editor uses the same typed knowledge graph as troubleshooting.
All contributions must be generic, approved public material, or explicit synthetic assumptions.

## Open and navigate

Choose **Knowledge graph editor** in the Workspace selector. The three views filter the same draft:

- **System Architecture:** components, interfaces, software, physical connections and containment.
  `HAS_COMPONENT` establishes hierarchy; children show their parent's label. Original isolated
  nodes remain isolated until engineers explicitly add relationships.
- **Dependencies:** reliance, control, performance, measurement and signal flow.
- **Causal Faults:** conditional causes, component associations and diagnostic checks.

Search by name, alias or stable ID to focus on related knowledge. Visible Types includes source
and scenario nodes when needed. Click nodes/arrows to open the right properties panel. Zoom,
pan, minimap and Fit-to-view do not modify engineering knowledge. The inspector scrolls separately.

## Authoring

Enable **Edit draft**. Use the canvas toolbar to create nodes, relationships or complete fault
modes. Drag a node's output handle (bottom/right) to another node's input handle (top/left), then complete the relationship
form. Reconnect an arrow by dragging an endpoint, or change its explicit source/target fields.
Reconnection preserves its ID and metadata. Typed compatibility checks reject invalid directions.

Names, descriptions, aliases, configuration properties, status and source references are editable.
Stable uppercase IDs cannot be renamed in forms. Each edit saves to the draft automatically;
**Save draft** provides an explicit checkpoint. Drafts may be incomplete while a rule is assembled.
Only complete valid knowledge can be published. CONNECTED_TO and DEPENDS_ON never become CAUSES.

The **Checks, rules and sources** sidebar opens dedicated forms for check outcomes, predictions,
ordered causal paths and provenance. Check/source metadata shares its ID with a paired node.
Use these forms to maintain both records. Every check requires `unknown` and another outcome.
Select path edges in traversal order; CAUSES edges require the matching rule ID, conditions and
the same provenance as their rule. Sources require a title, reference, section, paraphrase,
date, evidence basis, review status and permitted use. Public sources require an approval record;
pending sources cannot be published.

Deletion shows affected records and requires confirmation. Removing a component, fault, condition
or causal edge can remove affected rules and their entire causal paths; the preview lists these.
Deleting a check clears its predictions and incident relationships. Referenced sources must be
reassigned first. A deletion affects only the draft until it is validated and published.

## Draft → Validate → Publish

1. Create a draft from the published graph or reopen a saved draft.
2. Make changes; ordinary diagnostic sessions keep using published data.
3. **Validate** checks types, direction, IDs, references, causal continuity/conditions, source
   approval/basis, check predictions, duplicate relationships and containment/causal cycles.
   Potentially indistinguishable rules, parallel conditions and dependency cycles produce warnings.
4. Inspect the previous/updated record diff and all 20 existing case comparisons, including
   intermediate observations. A previously passing final result that regresses blocks publication.
   Existing ambiguous misses remain in the comparison; scoring and denominators are unchanged.
5. Enter a change description and local reviewer identity, confirm review, and publish.

Every edit invalidates validation. A draft based on an obsolete publication cannot overwrite it;
start from the latest version and reapply reviewed changes. Stale writes to the same draft are
also rejected. Source approval records are assertions by local reviewers, not verified permissions.

## Storage and rollback

`data/runtime/graph.json` and `sources.json` are preserved as import seeds. First opening the
editor imports them into the git-ignored `data/workspace/`:

| Location | Contents |
|---|---|
| `current.json` | Authoritative revision pointer and snapshot hash |
| `revisions/v*.json` | Immutable graph/source snapshots, parent, timestamp, editor/reviewer, diff and validation |
| `drafts/*.json` | Persistent drafts, base revision and edit counter |
| `layouts.json` | Node positions and viewport for each view |
| `*.json.bak` | Previous contents of mutable pointer, draft and layout files |

Writes use a temporary file, flush/fsync and atomic replacement under an OS-released lock.
A complete revision is written before the pointer changes; an interrupted publication leaves the
old pointer active. The reader checks the active snapshot hash and reports corruption instead of
silently falling back. Set `ECFKG_GRAPH_STORE` to relocate the store. Back up the entire directory
for team use; local backup files are not an institutional backup service.

History provides graph/provenance export and **Restore this version as a draft**. Validate and
approve that draft to publish the restored data as a new revision; previous history stays intact.
**Save layout** persists positions/viewport. **Reset layout** recalculates only the screen
arrangement; save it if desired. Layout changes do not change graph version, hash or validation.

## How diagnostics receive changes

`GraphService` owns authoring. `KnowledgeGraph()` resolves the current publication and rebuilds
the frozen NetworkX MultiDiGraph and lookup indexes on each new load. The existing agent tools
therefore retrieve newly published knowledge through the same interfaces. There is no separate
diagram-only graph or obsolete shared graph cache. Active troubleshooting sessions pin their
original graph; **Assess symptom** starts with the newest publication. Saved reports retain the
original version and evidence IDs. New checks use manual observations; **Simulate check** is
disabled unless the independent simulator implements that check.

## New fault demonstration

1. Select the DMM and **Add Fault Mode**, or use **＋ Fault mode** in the toolbar.
2. Select **Use the synthetic aperture demonstration**; edit the unique ID suffix, fault,
   condition, symptom phrase and check instructions if desired.
3. Leave **Create a source record labeling this as a synthetic assumption** checked.
4. Add to the draft, validate, review the diff/case results, and approve publication.
5. Return to Troubleshooting and enter: “The DMM displays the synthetic amber aperture flag 018.”
6. The new candidate is `F_APERTURE_018` and check is `CHECK_APERTURE_018`. Record
   `configuration_mismatch` to obtain the modeled identification.

The actual isolated run is recorded in `outputs/editor-demo/before-after.json`: before/during
draft = abstain; after publication = new fault retrieved; after observation = candidate identified;
after rollback = abstain. All 20 existing case outputs stayed unchanged. This uses the deterministic
agent and existing retrieval tools; it is not live API inference or independent engineering
validation. Its reviewer is explicitly labeled as automated demonstration.

Reproduce without editing the live workspace:

```powershell
.\.venv\Scripts\python.exe -m tools.demo_graph_editor
.\.venv\Scripts\python.exe -m pytest tests/test_graph_editor.py -q
```

Verification for this implementation: **103 tests passed** across the complete suite.
`outputs/verification/pytest-editor.xml` records the automated run. Actual browser checks,
including dragging/saving layout, drawing a parallel relationship, confirmed deletion,
draft persistence, search, selection and validation, are recorded in
`outputs/verification/editor-ui-checks.json` with `graph-editor-review.png`.
The live example remains a validated draft for local review; publication and rollback were
demonstrated in isolated stores. API settings and symptom text stay in session memory when
navigating to the editor and back, without writing credentials to graph storage.

## Implementation and limits

React Flow 12.12.0, React 18.3.1 and Dagre 3.1.3 are bundled with esbuild 0.28.2 into
`ecfkg/editor_assets/`. Streamlit 1.66's v2 component sends discrete selection, connection
and layout events to Python. No runtime CDN or separate frontend server is needed. Rebuild
with `pnpm install --frozen-lockfile` then `pnpm run build` inside `editor_frontend/` using Node 20+.

Prototype limits: one rule per fault, at most four causal edges per path, 1,000 nodes/4,000 edges
per draft, bounded retrieval, and local review. Containment provides hierarchy and parent labels,
not a nested equipment CAD editor. Layouts are shared per local view. The editor does not provide
production authentication/RBAC, collaborative merging, legal/source verification, proof of
technical truth, or equipment control. Source files are referenced, not uploaded/downloaded.

Official APIs checked: [Streamlit v2](https://docs.streamlit.io/develop/concepts/custom-components/components-v2/register),
[bidirectional communication](https://docs.streamlit.io/develop/concepts/custom-components/components-v2/communicate),
[React Flow](https://reactflow.dev/api-reference/react-flow),
[reconnection](https://reactflow.dev/examples/edges/reconnect-edge), and
[Dagre](https://reactflow.dev/examples/layout/dagre). Versions are locked in the frontend manifests.

## Locally authored synthetic mechanisms

The editor can capture a hypothetical mechanism with its own source record, causal conditions,
observable symptom and categorical check. Such a record documents authorship and an assumption;
it is not manufacturer evidence. The amber aperture flag 018 example is an intentionally invented
marker used only to prove that publishing knowledge changes retrieval. It makes no claim about
actual DMM behavior. No simulator or test-equipment interface is added by that example.

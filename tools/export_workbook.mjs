// Rebuild the report from actual JSON results with the Codex bundled artifact runtime.
// No evaluation or hidden-answer data is imported by the application runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'outputs', 'capstone');
const previewDir = path.join(root, 'tmp', 'workbook-previews');
await fs.mkdir(out, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
const read = async p => JSON.parse(await fs.readFile(path.join(root, p), 'utf8'));
const baseline = await read('outputs/baseline/results.json');
const theory = await read('outputs/theory-only/results.json');
const llm = await read('outputs/llm/results.json');
const robustness = await read('data/evaluation/robustness-cases.json');
const testXml = await fs.readFile(path.join(root, 'outputs/verification/pytest.xml'), 'utf8');
const testSuiteTag = testXml.match(/<testsuite\b[^>]*>/)?.[0] ?? '';
const countAttribute = name => Number(testSuiteTag.match(new RegExp(`${name}="(\\d+)"`))?.[1] ?? 0);
const testCount = countAttribute('tests');
const testFailures = countAttribute('failures') + countAttribute('errors');
const testSummary = `${testCount} tests; ${testFailures} failures/errors; ${countAttribute('skipped')} skipped`;
const wb = Workbook.create();
const summary = wb.worksheets.add('Summary');
const cases = wb.worksheets.add('Cases');
const results = wb.worksheets.add('Results');
const time = wb.worksheets.add('Time estimates');
const config = wb.worksheets.add('Run configuration');
const charcoal = '#292C30', orange = '#C75C1C', light = '#F4F4F3';

function base(sheet, range, title) {
  sheet.showGridLines = false;
  sheet.getRange(range).format.font = { name: 'Arial', size: 10, color: charcoal };
  sheet.getRange(range).format.verticalAlignment = 'center';
  sheet.getRange(range).format.rowHeight = 24;
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = { name: 'Arial', size: 15, bold: true, color: charcoal };
  sheet.getRange('A3:D3').format.borders = { bottom: { style: 'thin', color: orange } };
}
function header(sheet, address) {
  sheet.getRange(address).format = { fill: charcoal, font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' },
    wrapText: true, horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 32 };
}
function safe(value) {
  return typeof value === 'string' && /^[=+@-]/.test(value) ? "'" + value : value;
}
function table(sheet, startRow, rows, widths, name) {
  const endCol = String.fromCharCode(64 + rows[0].length);
  sheet.getRangeByIndexes(startRow - 1, 0, rows.length, rows[0].length).values = rows.map(r => r.map(safe));
  sheet.tables.add(`A${startRow}:${endCol}${startRow + rows.length - 1}`, true, name);
  header(sheet, `A${startRow}:${endCol}${startRow}`);
  widths.forEach((width, i) => { sheet.getRangeByIndexes(startRow - 1, i, rows.length, 1).format.columnWidth = width; });
  sheet.freezePanes.freezeRows(startRow);
  sheet.freezePanes.freezeColumns(1);
  for (let i = 1; i < rows.length; i += 2) sheet.getRangeByIndexes(startRow - 1 + i, 0, 1, rows[0].length).format.fill = light;
}

base(summary, 'A1:D28', 'Synthetic diagnostic evaluation');
summary.tabColor = charcoal;
summary.getRange('A4').values = [['Developer-created cases; software feasibility only. No live LLM run.']];
summary.getRange('A4').format.font.italic = true;
summary.getRange('A6:D6').values = [['Measure', 'Graph + reference', 'Theory only', 'Local LLM']];
header(summary, 'A6:D6');
const measureDefs = [
  ['Run status', 'status', false], ['Applicable cases', 'applicable_count', false],
  ['Scope candidate inclusion (target 80%)', 'scope_candidate_coverage', true],
  ['Top-1 accuracy', 'top1_accuracy', true], ['Top-3 coverage', 'top3_coverage', true],
  ['Mean list size (all cases)', 'average_candidate_list_size', false],
  ['Mean list size (applicable)', 'average_candidate_list_size_applicable', false],
  ['Appropriate abstention (6 cases)', 'appropriate_abstention_rate', true],
  ['Reference validity', 'citation_reference_validity', true],
  ['Documentation-backed evidence', 'documentation_backed_evidence_coverage', true],
  ['Synthetic evidence', 'synthetic_evidence_coverage', true],
  ['Mean response latency (ms/turn)', 'mean_turn_latency_ms', false],
  ['Engineer estimated time reduction', 'estimated_troubleshooting_time_reduction', true],
  ['Measured task-time reduction', 'measured_troubleshooting_time_reduction', true],
];
measureDefs.forEach(([label, key, pct], i) => {
  const row = 7 + i;
  const val = report => key === 'status' ? report.status : report.metrics?.[key] ?? 'Unmeasured';
  summary.getRange(`A${row}:D${row}`).values = [[label, val(baseline), val(theory), key === 'status' ? llm.status : 'Not run']];
  if (pct) summary.getRange(`B${row}:C${row}`).setNumberFormat('0.0%');
  else if (key !== 'status' && key !== 'applicable_count') summary.getRange(`B${row}:C${row}`).setNumberFormat('0.00');
  if (i % 2 === 0) summary.getRange(`A${row}:D${row}`).format.fill = light;
});
summary.getRange('A22').values = [[`${baseline.results.filter(r => r.top3).length} of ${baseline.metrics.applicable_count} applicable cases returned the correct root cause; ${baseline.results.filter(r => r.appropriate_abstention).length} of ${baseline.metrics.abstention_case_count} expected abstentions were correct.`]];
summary.getRange('A23').values = [['EVAL_013 and EVAL_014 remain ambiguous and miss the three-candidate cap.']];
summary.getRange('A24').values = [['No public source is approved for diagnostic use. Runtime evidence is synthetic.']];
summary.getRange('A25').values = [['Local LLM preflight: ' + llm.reason]];
summary.getRange('A26').values = [['Source: outputs/baseline/results.json; outputs/theory-only/results.json; outputs/llm/results.json.']];
summary.getRange('A27').values = [[testSummary + '. Mocked model tests are not live model evaluation.']];
summary.getRange('A6:A20').format.columnWidth = 45;
summary.getRange('B6:D20').format.columnWidth = 24;
summary.getRange('D7:D20').format.horizontalAlignment = 'right';

base(cases, 'A1:I29', 'Predefined synthetic cases');
cases.getRange('A4').values = [['Source: data/evaluation/cases.json and robustness-cases.json. Answer keys are outside runtime retrieval.']];
const caseRows = [['Case ID', 'Category', 'Initial symptom / test input', 'Available observations', 'Expected root / abstention', 'Useful initial check', 'Evidence basis', 'Source IDs', 'Population']];
for (const c of baseline.cases) caseRows.push([c.case_id, c.category, c.initial_symptom,
  c.available_observations.map(o => `${o.check_id}=${o.outcome}`).join('; ') || 'None',
  c.expected_root_cause ?? 'Abstain', c.expected_useful_checks.join(', ') || 'None', c.evidence_basis, c.source_ids.join(', '), 'Diagnostic']);
for (const c of robustness) caseRows.push([c.case_id, c.category, c.input, 'Mocked response injection', c.expected, 'None', c.evidence_basis, 'Software contract', 'Mock robustness']);
table(cases, 6, caseRows, [16, 26, 53, 48, 30, 22, 23, 28, 22], 'EvaluationCases');
cases.getRange('A7:I28').format.wrapText = true;
cases.getRange('A7:I28').format.rowHeight = 62;

base(results, 'A1:L27', 'Actual baseline results');
results.getRange('A4').values = [['Source: outputs/baseline/results.json. Final assessment after all supplied observations; three-candidate cap.']];
const resultRows = [['Case ID', 'Status', 'Expected root', 'Returned candidates', 'Top-1 correct', 'Top-3 included', 'List size', 'Expected abstain', 'Correct abstain', 'Case latency (ms)', 'Valid IDs', 'IDs returned']];
for (const r of baseline.results) resultRows.push([r.case_id, r.status, r.expected_root_cause ?? '', r.returned_faults.join(', '),
  r.expected_root_cause ? Number(r.top1) : null, r.expected_root_cause ? Number(r.top3) : null,
  r.candidate_count, Number(r.expected_abstention), r.expected_abstention ? Number(r.appropriate_abstention) : null,
  r.latency_ms, r.valid_references, r.reference_count]);
table(results, 6, resultRows, [16, 26, 20, 43, 16, 17, 12, 19, 18, 19, 14, 16], 'BaselineResults');
results.getRange('J7:J26').setNumberFormat('0.000');
results.getRange('D7:D26').format.wrapText = true;
results.getRange('A7:L26').format.rowHeight = 32;
results.getRange('E7:F26').conditionalFormats.add('cellIs', { operator: 'equal', formula: 0, format: { fill: '#FFF1DD', font: { color: '#8A3D13', bold: true } } });

base(time, 'A1:J22', 'Engineer time estimates and measured task time');
time.getRange('A4').values = [['Amber cells are inputs. Leave blank until genuine data exists. Times are minutes; estimates and measurements are separate.']];
const timeRows = [['Scenario ID', 'Manual estimate (min)', 'Assisted estimate (min)', 'Estimated reduction', 'Manual measured (min)', 'Assisted measured (min)', 'Measured reduction', 'Participant code', 'Task definition', 'Method / review notes'],
  ...Array.from({length: 10}, () => Array(10).fill(null))];
table(time, 6, timeRows, [18, 23, 23, 23, 25, 25, 23, 22, 40, 40], 'EngineerTimes');
time.getRange('A7:C16').format.fill = '#FFF3D6';
time.getRange('E7:F16').format.fill = '#FFF3D6';
time.getRange('H7:J16').format.fill = '#FFF3D6';
time.getRange('B7:C16').setNumberFormat('0.0');
time.getRange('E7:F16').setNumberFormat('0.0');
time.getRange('D7:D16').setNumberFormat('0.0%');
time.getRange('G7:G16').setNumberFormat('0.0%');
time.getRange('D7').formulas = [['=IF(COUNT(B7:C7)<2,"",IF(OR(B7<=0,C7<0),"Invalid input",1-C7/B7))']];
time.getRange('D7:D16').fillDown();
time.getRange('G7').formulas = [['=IF(COUNT(E7:F7)<2,"",IF(OR(E7<=0,F7<0),"Invalid input",1-F7/E7))']];
time.getRange('G7:G16').fillDown();
time.getRange('A18').values = [['Scope target: at least 25% lower estimated troubleshooting time. Response latency is not engineer task time.']];
time.getRange('A19').values = [['Record generic scenario, anonymous participant code, task boundaries, assistance allowed and test order. No personal contact details.']];
time.getRange('A20').values = [['Source: genuine future engineer inputs only. No estimates or measured times have been collected.']];
// Exercise live formula boundaries and restore all temporary inputs before delivery.
time.getRange('B7:C7').values = [[40, 30]];
time.getRange('E7:F7').values = [[20, 16]];
wb.recalculate();
if (Math.abs(time.getRange('D7').values[0][0] - 0.25) > 1e-9 || Math.abs(time.getRange('G7').values[0][0] - 0.2) > 1e-9) throw new Error('Time reduction formula failed');
time.getRange('B7:C7').values = [[0, 0]];
wb.recalculate();
if (time.getRange('D7').values[0][0] !== 'Invalid input') throw new Error('Zero baseline guard failed');
time.getRange('B7:C7').values = [[40, null]];
wb.recalculate();
if (time.getRange('D7').values[0][0] !== '') throw new Error('Missing estimate should remain blank');
time.getRange('B7:C7').clear({ applyTo: 'contents' });
time.getRange('E7:F7').clear({ applyTo: 'contents' });

base(config, 'A1:B30', 'Reproduction settings');
const confRows = [['Setting', 'Recorded value'],
 ['Run timestamp (UTC)', baseline.config.timestamp_utc], ['Mode', baseline.config.mode],
 ['Mock inference', String(baseline.config.mock)], ['Graph version', baseline.config.graph_version],
 ['Graph/source SHA256', baseline.config.data_sha256], ['Case SHA256', baseline.config.cases_sha256],
 ['Code SHA256', baseline.config.code_sha256], ['Python', baseline.config.python],
 ['Dependencies', JSON.stringify(baseline.config.dependencies)], ['Candidate cap', 3],
 ['LLM status', llm.status], ['LLM model configured', llm.config.model || 'None'],
 ['LLM endpoint', llm.config.endpoint || 'Not configured'], ['LLM reason', llm.reason || ''],
 ['Scope inclusion threshold', 0.8], ['Time estimate reduction target', 0.25],
 ['Prompt/settings record', 'Full prompts and per-turn configuration are in results.json; source prompts are in ecfkg/agent.py.'],
 ['Test result', testSummary + '. See outputs/verification/pytest.xml.'],
 ['Evidence review', 'Synthetic data unreviewed by equipment engineers. Public sources remain quarantined.'],
 ['Independent validation', 'Not performed. Cases created during development.'],
 ['Source', 'Committed synthetic evaluation JSON exports; no user session exports.']];
table(config, 6, confRows, [35, 110], 'RunSettings');
config.getRange('B7:B27').format.wrapText = true;
config.getRange('A7:B27').format.rowHeight = 34;
config.getRange('A15:B15').format.rowHeight = 54;
config.getRange('B7').values = [[new Date(baseline.config.timestamp_utc)]];
config.getRange('B7').setNumberFormat('yyyy-mm-dd hh:mm:ss "UTC"');
config.getRange('B21:B22').setNumberFormat('0.0%');

wb.recalculate();
const errors = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',
  options: { useRegex: true, maxResults: 30 }, summary: 'Formula error scan' });
console.log(errors.ndjson);
console.log((await wb.inspect({ kind: 'table', range: 'Summary!A6:D20', include: 'values,formulas', tableMaxRows: 15, tableMaxCols: 4 })).ndjson);
if (baseline.metrics.scope_candidate_coverage !== baseline.results.filter(r => r.top3).length / baseline.cases.filter(c => c.expected_root_cause).length) throw new Error('Metric reconciliation failed');
for (const [sheetName, range] of [['Summary', 'A1:D27'], ['Cases', 'A1:I10'], ['Results', 'A1:L10'], ['Time estimates', 'A1:J20'], ['Run configuration', 'A1:B27']]) {
  const preview = await wb.render({ sheetName, range, scale: 1.4, format: 'png' });
  await fs.writeFile(path.join(previewDir, sheetName.replaceAll(' ', '-') + '.png'), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(out, 'evaluation.xlsx'));
console.log('Saved outputs/capstone/evaluation.xlsx; temporary formula inputs restored.');

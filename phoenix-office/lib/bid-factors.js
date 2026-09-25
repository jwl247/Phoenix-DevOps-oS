// bid-factors.js — Phoenix Office / Project Assist
//
// Single source of truth for the parametric-estimating question set: the
// project dimensions and cost/time-influencing factors that make a bid
// meaningfully more accurate than a gut-feel guess. Both the plain UI form
// and the Secretariat agent's `set_bid_factor` tool read this SAME ordered
// catalog, so typing into the agent chat and clicking through the form
// never diverge — there's one question list, one storage shape
// (office_projects.bid_factors, a JSON blob), and one "what's next" function.
//
// Deliberately a flat ordered array, not a normalized DB table: Jerry's own
// words, this list "goes deeper" over time (especially labor sub-factors) —
// adding a factor later is one array entry here, never a migration.
//
//   const { BID_FACTOR_QUESTIONS, nextQuestion, setFactor, isComplete } = require('./bid-factors');
//   const next = nextQuestion(project.bid_factors);      // -> question object, or null if done
//   const updated = setFactor(project.bid_factors, next.key, value);

// type: 'text' | 'number' | 'select' | 'boolean'
// key: dotted path into the bid_factors object (e.g. 'dimensions.length_ft')
// dependsOn(factors): optional — question is skipped unless this returns true
const BID_FACTOR_QUESTIONS = [
  { key: 'project_type', label: 'Residential or commercial?', type: 'select',
    options: ['residential', 'commercial'] },
  { key: 'setting', label: 'Urban or rural site?', type: 'select',
    options: ['urban', 'rural'] },
  { key: 'dimensions.length_ft', label: "Approximate length, in feet (e.g. \"200\")", type: 'number' },
  { key: 'dimensions.width_ft', label: "Approximate width, in feet (e.g. \"300\")", type: 'number' },
  { key: 'dimensions.height_ft', label: 'Approximate height/clearance, in feet (leave blank if not applicable)', type: 'number' },
  { key: 'time_of_year.start_month', label: 'Expected start month (YYYY-MM)', type: 'text' },
  { key: 'schedule.tightness', label: 'How tight is the schedule?', type: 'select',
    options: ['relaxed', 'normal', 'aggressive'] },
  { key: 'schedule.target_duration_weeks', label: 'Target duration, in weeks', type: 'number' },
  { key: 'labor.crew_size_est', label: 'Estimated crew size', type: 'number' },
  { key: 'labor.union', label: 'Union labor?', type: 'boolean' },
  { key: 'labor.trade_mix', label: 'Trades needed (comma-separated, e.g. "ironworker, welder, crane operator")', type: 'text' },
  { key: 'site.existing_structure', label: 'Is there an existing structure to work around/into?', type: 'boolean' },
  { key: 'site.access_notes', label: 'Any site-access notes worth flagging (narrow access, overhead lines, etc.)? Leave blank if none.', type: 'text',
    optional: true },
];

function deepClone(x) { return JSON.parse(JSON.stringify(x)); }

function getByPath(obj, path) {
  return path.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), obj);
}

function setByPath(obj, path, value) {
  const parts = path.split('.');
  const next = deepClone(obj || {});
  let cursor = next;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    if (typeof cursor[part] !== 'object' || cursor[part] === null) cursor[part] = {};
    cursor = cursor[part];
  }
  cursor[parts[parts.length - 1]] = value;
  return next;
}

function isAnswered(factors, question) {
  const v = getByPath(factors, question.key);
  return v !== undefined && v !== null && v !== '';
}

// The anticipatory-Q&A mechanism: given the factors answered so far, what's
// the single next thing to ask? Skips already-answered and optional-but-
// blank-is-fine questions whose dependsOn (if any) isn't satisfied. Returns
// null once every non-optional question is answered.
function nextQuestion(factors) {
  const f = factors || {};
  for (const q of BID_FACTOR_QUESTIONS) {
    if (q.dependsOn && !q.dependsOn(f)) continue;
    if (q.optional) continue;
    if (!isAnswered(f, q)) return q;
  }
  return null;
}

function setFactor(factors, key, value) {
  return setByPath(factors, key, value);
}

function isComplete(factors) {
  return nextQuestion(factors) === null;
}

module.exports = { BID_FACTOR_QUESTIONS, getByPath, setFactor, nextQuestion, isComplete };

// project.js — Phoenix Office / Project Assist
//
// Pure functions, no I/O — same shape as document.js. A "project" groups
// multiple documents (proposal, schedule, safety plan, work orders) across
// phases, on top of the unchanged document engine. Persistence is the
// worker's job (worker/index.js); this file only builds/derives objects.
//
// Phase taxonomy is grounded in real PM doctrine (PMI/PMBOK process groups),
// not invented — see STANDARD_PHASE_TEMPLATE below for the one deliberate
// departure from a naive reading of it.

const crypto = require('crypto');

function nowIso() { return new Date().toISOString(); }
function deepClone(x) { return JSON.parse(JSON.stringify(x)); }
function uuid() { return crypto.randomUUID(); }

// The default phase set, grounded in PMI/PMBOK's Initiation / Planning /
// Execution / Closing process groups, applied to real steel-erection
// practice. Deliberately NOT including a 'Monitoring & Controlling' phase:
// PMBOK itself defines M&C as CONCURRENT with Execution, not a step after
// it — forcing it into a 6th linear phase would misrepresent the doctrine
// rather than follow it. M&C is embodied instead by the per-phase checklist
// + consultation panel, which runs continuously alongside every
// Execution-stage phase. base_weeks is a starting-point duration estimate,
// scaled by deriveScheduleFromBidFactors() below — not a promise, a default.
const STANDARD_PHASE_TEMPLATE = [
  { phase_type: 'site_survey_permitting', label: 'Site Survey & Permitting', lifecycle_stage: 'INITIATION', base_weeks: 1 },
  { phase_type: 'procurement_mobilization', label: 'Material Procurement & Mobilization', lifecycle_stage: 'PLANNING', base_weeks: 2 },
  { phase_type: 'site_prep', label: 'Site Preparation', lifecycle_stage: 'EXECUTION', base_weeks: 1 },
  { phase_type: 'foundation', label: 'Foundation', lifecycle_stage: 'EXECUTION', base_weeks: 2 },
  { phase_type: 'erection', label: 'Steel Erection', lifecycle_stage: 'EXECUTION', base_weeks: 3 },
  { phase_type: 'decking', label: 'Decking', lifecycle_stage: 'EXECUTION', base_weeks: 1 },
  { phase_type: 'finishing', label: 'Finishing & Punch List', lifecycle_stage: 'EXECUTION', base_weeks: 2 },
  { phase_type: 'closeout', label: 'Final Inspection & Closeout', lifecycle_stage: 'CLOSING', base_weeks: 1 },
];

// bid_factors: name, authorId: the resolved author_id (identity.js), NOT a
// raw fingerprint — this is a project-level record, not a document.
function createProject({ name, authorId, bidFactors, counterparty, jobId }) {
  if (!name) throw new Error('createProject requires a name');
  if (!authorId) throw new Error('createProject requires an authorId');
  return {
    project_id: uuid(),
    author_id: authorId,
    job_id: jobId || null,
    name,
    status: 'BID',
    bid_factors: bidFactors || {},
    counterparty: counterparty || null,
    created_at: nowIso(),
    updated_at: null,
  };
}

// Deterministic, inspectable — reads structured bid_factors and adjusts the
// standard template's durations/sequencing. This is the concrete mechanism
// behind "bid data should already carry the schedule" — code reading
// structured data, not a second AI interview.
function deriveScheduleFromBidFactors(bidFactors) {
  const bf = bidFactors || {};
  const tightnessMultiplier = { relaxed: 1.25, normal: 1.0, aggressive: 0.8 }[bf.schedule?.tightness] || 1.0;

  const lengthFt = Number(bf.dimensions?.length_ft) || 0;
  const widthFt = Number(bf.dimensions?.width_ft) || 0;
  const sqFt = lengthFt * widthFt;
  // Modest size scaling for the EXECUTION-stage phases only — a 10,000 sqft+
  // job runs longer than a 2,000 sqft one; INITIATION/PLANNING/CLOSING
  // phases don't meaningfully scale with footprint the same way.
  const sizeMultiplier = sqFt > 60000 ? 1.5 : sqFt > 20000 ? 1.25 : 1.0;

  // A winter start adds real buffer to outdoor Execution-stage work.
  const winterBuffer = bf.time_of_year?.season_risk === 'winter' ? 1.15 : 1.0;

  return STANDARD_PHASE_TEMPLATE.map((tpl, i) => {
    const isExecution = tpl.lifecycle_stage === 'EXECUTION';
    const scaled = tpl.base_weeks
      * tightnessMultiplier
      * (isExecution ? sizeMultiplier : 1.0)
      * (isExecution ? winterBuffer : 1.0);
    return {
      phase_id: uuid(),
      phase_type: tpl.phase_type,
      lifecycle_stage: tpl.lifecycle_stage,
      label: tpl.label,
      sequence: i + 1,
      state: 'NOT_STARTED',
      estimated_duration_weeks: Math.round(scaled * 10) / 10,
      estimated_cost: null,
      actual_cost: null,
      risk_level: null,
      risk_notes: null,
    };
  });
}

function advancePhase(phase, toState) {
  const validStates = ['NOT_STARTED', 'IN_PROGRESS', 'COMPLETE'];
  if (!validStates.includes(toState)) {
    throw new Error(`invalid phase state ${toState}`);
  }
  const next = deepClone(phase);
  next.state = toState;
  if (toState === 'IN_PROGRESS' && !next.started_at) next.started_at = nowIso();
  if (toState === 'COMPLETE') next.completed_at = nowIso();
  return next;
}

module.exports = {
  STANDARD_PHASE_TEMPLATE,
  createProject,
  deriveScheduleFromBidFactors,
  advancePhase,
};

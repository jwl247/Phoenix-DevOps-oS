-- seed-checklist-catalog.sql — Phoenix Office / Project Assist
-- Hand-curated starting checklist catalog, one pass across the 8 phases in
-- lib/project.js's STANDARD_PHASE_TEMPLATE plus 'general' (applies to every
-- phase). Real OSHA citations (steel erection = 29 CFR 1926 Subpart R,
-- fall protection = Subpart M) — not exhaustive, a real safety program
-- should be reviewed by a qualified person before relying on this list
-- alone. Oklahoma has no OSHA-approved State Plan (federal OSHA has
-- jurisdiction), so the OK_STATE row here is a contractor-licensing
-- requirement, not a state-specific safety code duplicate of OSHA.
--
-- Apply / re-apply safely (INSERT OR IGNORE, keyed by catalog_id):
--   wrangler d1 execute phoenix_office_db --file=worker/seed-checklist-catalog.sql --remote

INSERT OR IGNORE INTO office_checklist_catalog (catalog_id, phase_type, source_type, source_ref, label, guidance) VALUES

-- general — applies to every phase, regardless of type
('pm-best-practice-scope-baseline', 'general', 'PM_BEST_PRACTICE', NULL,
 'Scope, cost, and schedule baseline confirmed for this phase',
 'The phase has an estimated cost, a target duration, and a clear definition of what "complete" means before work starts.'),
('pm-best-practice-stakeholder-signoff', 'general', 'PM_BEST_PRACTICE', NULL,
 'Client/counterparty aware this phase is starting',
 'A simple confirmation (call, text, or document) that the client knows this phase is underway — avoids disputes about timeline later.'),

-- site_survey_permitting (INITIATION)
('client-spec-permits-identified', 'site_survey_permitting', 'CLIENT_SPEC', NULL,
 'Required permits identified for this job/site', 'Building permit, right-of-way permit, or any local AHJ requirement specific to this project.'),
('pm-best-practice-site-survey-done', 'site_survey_permitting', 'PM_BEST_PRACTICE', NULL,
 'Site survey / existing conditions documented', 'Photos and measurements of the site as found, before any work — protects against later disputes over pre-existing conditions.'),

-- procurement_mobilization (PLANNING)
('pm-best-practice-long-lead-materials', 'procurement_mobilization', 'PM_BEST_PRACTICE', NULL,
 'Long-lead-time materials ordered', 'Structural steel, specialty fasteners, or anything with a lead time that could delay the schedule if not ordered early.'),
('osha-1926-95-ppe-provided', 'procurement_mobilization', 'OSHA', '29 CFR 1926.95',
 'PPE availability confirmed for the crew', 'Hard hats, eye protection, and fall-protection equipment on hand before crew mobilizes.'),

-- site_prep (EXECUTION)
('osha-1926-651-excavation', 'site_prep', 'OSHA', '29 CFR 1926.651',
 'Excavation/trenching hazards addressed, if applicable', 'Protective systems (sloping, shoring, or shielding) in place for any excavation deeper than 5 feet.'),
('pm-best-practice-utility-locate', 'site_prep', 'PM_BEST_PRACTICE', NULL,
 'Underground utilities located (call-before-you-dig)', 'Confirmed with the local utility locate service before any excavation or grading.'),

-- foundation (EXECUTION)
('client-spec-foundation-inspection', 'foundation', 'CLIENT_SPEC', NULL,
 'Foundation inspected/approved before steel erection begins', 'Whatever inspection the client, engineer of record, or local AHJ requires before erection can start on top of it.'),
('pm-best-practice-anchor-bolt-verification', 'foundation', 'PM_BEST_PRACTICE', NULL,
 'Anchor bolt layout verified against structural drawings', 'A real, documented check against the drawings before steel shows up on site — a wrong bolt pattern is expensive to fix after the fact.'),

-- erection (EXECUTION)
('osha-1926-760-fall-protection-erection', 'erection', 'OSHA', '29 CFR 1926.760',
 'Fall protection plan in place for steel erection', 'Required above 15 feet during most connecting/erection work under Subpart R — confirm the specific method (guardrails, personal fall arrest, etc.) for this job.'),
('osha-1926-751-structural-stability', 'erection', 'OSHA', '29 CFR 1926.751',
 'Structural stability maintained during erection', 'Temporary bracing/guying per the erection plan until the structure is self-supporting.'),
('osha-1926-761-training', 'erection', 'OSHA', '29 CFR 1926.761',
 'Crew trained on fall hazards specific to steel erection', 'Documented training, not just general OSHA 10/30 — Subpart R has its own training requirement.'),
('pm-best-practice-crane-lift-plan', 'erection', 'PM_BEST_PRACTICE', NULL,
 'Crane lift plan reviewed for this phase', 'Load charts, rigging plan, and a qualified signal person identified before any critical lift.'),

-- decking (EXECUTION)
('osha-1926-754-decking-hazards', 'decking', 'OSHA', '29 CFR 1926.754',
 'Decking installation hazards addressed', 'Open-web steel joists and metal decking have their own fall-protection and installation-sequence requirements under Subpart R.'),

-- finishing (EXECUTION)
('client-spec-punch-list-defined', 'finishing', 'CLIENT_SPEC', NULL,
 'Punch list criteria agreed with client', 'A documented, mutually understood list of what must be corrected before the client considers the phase complete.'),

-- closeout (CLOSING)
('client-spec-final-inspection', 'closeout', 'CLIENT_SPEC', NULL,
 'Final inspection passed / accepted by client or AHJ', 'Whatever final sign-off the contract or local code requires.'),
('ok-license-contractor-standing', 'closeout', 'OK_STATE', 'Oklahoma Construction Industries Board licensing',
 'Contractor license/standing confirmed current for final paperwork', 'Oklahoma has no OSHA-approved State Plan (federal OSHA has jurisdiction on safety) — this item is licensing/business-standing, not a state safety-code duplicate.'),
('pm-best-practice-lien-waivers', 'closeout', 'PM_BEST_PRACTICE', NULL,
 'Lien waivers / final payment documentation prepared', 'Standard closeout paperwork protecting both PBM and the client.');

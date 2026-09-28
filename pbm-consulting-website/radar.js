const RADAR_API = 'https://pbm-radar-worker.phoenix-jwl.workers.dev';

const applyForm = document.getElementById('apply-form');
const verifyForm = document.getElementById('apply-verify');
const applyStatus = document.getElementById('apply-status');
const verifyStatus = document.getElementById('verify-status');
const nationwide = document.getElementById('ap-nationwide');
const statesInput = document.getElementById('ap-states');
let pendingEmail = '';

const grantsBox = document.getElementById('ap-grants');
const grantsSurvey = document.getElementById('grants-survey');
grantsBox.addEventListener('change', () => { grantsSurvey.hidden = !grantsBox.checked; });
nationwide.addEventListener('change', () => {
  statesInput.disabled = nationwide.checked;
});

// Turnstile tokens are single-use: reset after every attempt so a retry gets a fresh one.
function resetBotCheck() {
  if (window.turnstile) window.turnstile.reset();
}

applyForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(applyForm);
  const payload = {
    name: fd.get('name'),
    business_name: fd.get('business_name'),
    email: fd.get('email'),
    naics: fd.get('naics'),
    work_desc: fd.get('work_desc'),
    certs: fd.getAll('certs'),
    mode: fd.get('mode'),
    states: nationwide.checked ? '' : fd.get('states'),
    nationwide: nationwide.checked,
    grants: grantsBox.checked,
    grant_who: fd.get('grant_who'),
    grant_categories: fd.getAll('grant_categories'),
    grant_keywords: fd.get('grant_keywords'),
    grant_min_award: fd.get('grant_min_award'),
    turnstile_token: fd.get('cf-turnstile-response') || '',
  };
  if (!payload.turnstile_token) { applyStatus.textContent = 'Please wait for the security check to finish, then try again.'; return; }
  applyStatus.textContent = 'Sending your code…';
  try {
    const res = await fetch(`${RADAR_API}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    resetBotCheck();
    if (!res.ok || !body.ok) { applyStatus.textContent = body.error || 'Something went wrong. Please try again.'; return; }
    if (body.already) { applyStatus.textContent = body.message; applyForm.hidden = true; return; }
    pendingEmail = payload.email;
    applyStatus.textContent = `Check ${payload.email} for your 6-digit code.`;
    applyForm.hidden = true;
    verifyForm.hidden = false;
    document.getElementById('av-code').focus();
  } catch (err) {
    resetBotCheck();
    applyStatus.textContent = 'Could not reach the server. Please try again in a moment.';
  }
});

verifyForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  verifyStatus.textContent = 'Checking…';
  const code = new FormData(verifyForm).get('code');
  try {
    const res = await fetch(`${RADAR_API}/apply/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: pendingEmail, code }),
    });
    const body = await res.json();
    if (!res.ok || !body.ok) { verifyStatus.textContent = body.error || 'Something went wrong.'; return; }
    verifyForm.hidden = true;
    applyStatus.textContent = '';
    verifyStatus.textContent = "You're confirmed. We'll review your application and email you when your Radar is on.";
  } catch (err) {
    verifyStatus.textContent = 'Could not reach the server. Please try again in a moment.';
  }
});

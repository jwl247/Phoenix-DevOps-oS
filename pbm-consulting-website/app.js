const LEADS_API = 'https://pbm-leads-worker.phoenix-jwl.workers.dev';

const leadForm = document.getElementById('lead-form');
const verifyForm = document.getElementById('verify-form');
const leadStatus = document.getElementById('lead-status');
const verifyStatus = document.getElementById('verify-status');
let pendingEmail = '';

leadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  leadStatus.textContent = 'Sending your verification code…';
  const fd = new FormData(leadForm);
  const turnstileToken = leadForm.querySelector('[name="cf-turnstile-response"]')?.value || '';
  try {
    const res = await fetch(`${LEADS_API}/lead`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: fd.get('name'), business_name: fd.get('business_name'),
        email: fd.get('email'), phone: fd.get('phone'), turnstile_token: turnstileToken,
      }),
    });
    const body = await res.json();
    if (!res.ok || !body.ok) { leadStatus.textContent = body.error || 'Something went wrong — please try again.'; return; }
    pendingEmail = fd.get('email');
    leadStatus.textContent = `Reference ${body.reference} — check your email for the code.`;
    leadForm.hidden = true;
    verifyForm.hidden = false;
    if (window.turnstile) window.turnstile.reset();
  } catch (err) {
    leadStatus.textContent = 'Could not reach the server — please try again in a moment.';
  }
});

verifyForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  verifyStatus.textContent = 'Checking…';
  const code = new FormData(verifyForm).get('code');
  try {
    const res = await fetch(`${LEADS_API}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: pendingEmail, code }),
    });
    const body = await res.json();
    if (!res.ok || !body.ok) { verifyStatus.textContent = body.error || 'Something went wrong.'; return; }
    verifyForm.hidden = true;
    verifyStatus.textContent = `Verified — reference ${body.reference}. We'll be in touch shortly.`;
  } catch (err) {
    verifyStatus.textContent = 'Could not reach the server — please try again in a moment.';
  }
});

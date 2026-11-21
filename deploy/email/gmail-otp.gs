/**
 * Dispensary Desk: free email relay for sign-in codes, sent from YOUR Gmail account.
 *
 * Setup (5 minutes, see DEPLOYMENT_GUIDE.md "Email OTP"):
 *  1. Open https://script.google.com while signed in to the Gmail account that should send the codes ➔ New project.
 *  2. Replace everything with this file. Put a long random value in TOKEN (the same value goes in GMAIL_SCRIPT_TOKEN).
 *  3. Deploy ➔ New deployment ➔ type "Web app" ➔ Execute as: Me ➔ Who has access: Anyone ➔ Deploy ➔ allow access.
 *  4. Copy the Web app URL (ends with /exec) into GMAIL_SCRIPT_URL on the backend.
 *
 * Limit: about 100 emails/day on a normal Gmail account (1,500 on Google Workspace).
 */
const TOKEN = 'PASTE-A-LONG-RANDOM-SECRET-HERE';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (!TOKEN || TOKEN.indexOf('PASTE-') === 0 || data.token !== TOKEN) return reply({ ok: false, error: 'bad token' });
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.to || '')) return reply({ ok: false, error: 'bad address' });
    MailApp.sendEmail({
      to: data.to,
      subject: String(data.subject || 'Sign-in code').slice(0, 200),
      body: String(data.text || '').slice(0, 5000),
      name: String(data.name || 'Dispensary Desk').slice(0, 60),
    });
    return reply({ ok: true, remaining: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return reply({ ok: false, error: String(err).slice(0, 200) });
  }
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

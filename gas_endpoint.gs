/**
 * HORIZON Risk Lab — endpoint read-only.
 * Tambahkan ke project Apps Script HORIZON, sesuaikan nama sheet/kolom,
 * kemudian simpan API_TOKEN di Project Settings > Script properties.
 * Jangan membuat doGet() kedua jika HORIZON sudah memilikinya.
 */
const RISK_SHEET = 'RiskLab_Data';

function apiRiskLab_(e) {
  const expected = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
  const supplied = e && e.parameter ? String(e.parameter.token || '') : '';
  if (!expected || supplied !== expected) {
    return jsonOutput_({ ok: false, error: 'unauthorized' });
  }

  const sheet = SpreadsheetApp.getActive().getSheetByName(RISK_SHEET);
  if (!sheet) return jsonOutput_({ ok: false, error: 'sheet_not_found' });

  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return jsonOutput_({ ok: true, rows: [] });

  const headers = values[0].map(h => String(h).trim());
  const required = ['student_id', 'nama', 'kelas', 'mapel', 'assessment_order', 'score'];
  const missing = required.filter(h => !headers.includes(h));
  if (missing.length) return jsonOutput_({ ok: false, error: 'missing_columns', missing: missing });

  const rows = values.slice(1).filter(r => r.some(Boolean)).map(r => {
    const item = {};
    headers.forEach((h, i) => item[h] = r[i]);
    return item;
  });
  return jsonOutput_({ ok: true, generated_at: new Date().toISOString(), rows: rows });
}

/*
 * TAMBAHKAN baris berikut di dalam doGet(e) HORIZON yang SUDAH ADA:
 *
 * if (e.parameter.action === 'riskLab') return apiRiskLab_(e);
 *
 * Contoh hanya bila project Bapak memang belum memiliki doGet:
 * function doGet(e) {
 *   if (e.parameter.action === 'riskLab') return apiRiskLab_(e);
 *   return jsonOutput_({ ok: false, error: 'unknown_action' });
 * }
 */

function jsonOutput_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

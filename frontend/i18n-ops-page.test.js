/**
 * @jest-environment jsdom
 *
 * The Operations page (config history, restore) shows its text through t().
 * t() is replaced by a marker function, so any English literal left in the
 * page code shows up as text with no marker.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { evalApp, resetDom, mockFn } = require('./helpers/setup');

const I18N = new Function( // eslint-disable-line no-new-func
  fs.readFileSync(path.resolve(__dirname, '../hivemind_admin_panel/static/js/i18n.js'), 'utf8') +
  '\nreturn I18N;')();

const KEYS = ['noSnapshotsYet', 'diff', 'revert', 'configHistoryLoadFailed',
              'configRevertPreview', 'configRevertConfirm', 'restoreResult'];

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <div id="configBackups"></div><pre id="configBackupDiff" hidden></pre>
    <div id="opsResult"></div>`);
  mockFn('t').mockImplementation((key, params) =>
    `«${key}${params ? JSON.stringify(params) : ''}»`);
});

test('every key exists in en, es and pt', () => {
  for (const lang of ['en', 'es', 'pt']) {
    const missing = KEYS.filter(k => typeof I18N[lang][k] !== 'string');
    expect({ lang, missing }).toEqual({ lang, missing: [] });
  }
});

test('placeholders are the same in every language', () => {
  const slots = s => (s.match(/\{\w+\}/g) || []).sort();
  for (const k of KEYS) {
    expect({ k, es: slots(I18N.es[k]) }).toEqual({ k, es: slots(I18N.en[k]) });
    expect({ k, pt: slots(I18N.pt[k]) }).toEqual({ k, pt: slots(I18N.en[k]) });
  }
});

test('an empty history uses a key', async () => {
  mockFn('apiCall').mockResolvedValue([]);
  await loadConfigBackups();
  expect(document.getElementById('configBackups').textContent).toBe('«noSnapshotsYet»');
});

test('the snapshot buttons use keys', async () => {
  mockFn('apiCall').mockResolvedValue([{ file: 's.json', mtime: 0, size: 1024 }]);
  await loadConfigBackups();
  const labels = [...document.querySelectorAll('#configBackups button')].map(b => b.textContent);
  expect(labels).toEqual(['«diff»', '«revert»']);
});

test('a failed history load uses a key', async () => {
  mockFn('apiCall').mockRejectedValue(new Error('boom'));
  await loadConfigBackups();
  expect(document.getElementById('configBackups').textContent).toBe('«configHistoryLoadFailed»');
});

test('the revert preview uses a key with the file and the key lists', async () => {
  mockFn('apiCall').mockResolvedValue({ added: { a: 1 }, removed: {}, changed: { b: 2 } });
  await diffConfigBackup('s.json');
  expect(document.getElementById('configBackupDiff').textContent).toBe(
    '«configRevertPreview{"file":"s.json","added":"a","removed":"—","changed":"b"}»');
});

test('the revert prompt uses a key', async () => {
  global.confirm = jest.fn(() => false);
  await revertConfigBackup('s.json');
  expect(global.confirm).toHaveBeenCalledWith('«configRevertConfirm{"file":"s.json"}»');
});

test('the restore result uses a key', async () => {
  mockFn('apiCall').mockResolvedValue({ clients_added: 2, clients_skipped: 1 });
  await uploadRestore({ files: [{ text: async () => '{}' }] });
  expect(document.getElementById('opsResult').textContent).toBe(
    '«restoreResult{"added":2,"skipped":1}»');
});

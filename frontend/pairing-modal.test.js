/**
 * @jest-environment jsdom
 *
 * The pairing modal asks for the host inside the dialog. Cancel makes no
 * request, and the bundle can be copied.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { evalApp, resetDom, mockFn } = require('./helpers/setup');

const html = fs.readFileSync(
  path.resolve(__dirname, '../hivemind_admin_panel/static/index.html'), 'utf8');
const modalHtml = html.match(/<div id="pairModal"[\s\S]*?<!-- Monitor Page -->/)[0];

beforeAll(() => evalApp());
let api;
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', modalHtml);
  global.prompt = jest.fn(() => '');
  global.fetch = jest.fn();
  api = mockFn('apiCall').mockResolvedValue({ key: 'k', host: 'h' });
});

test('the modal is a labelled dialog', () => {
  const modal = document.getElementById('pairModal');
  expect(modal.getAttribute('role')).toBe('dialog');
  expect(modal.getAttribute('aria-modal')).toBe('true');
  const label = document.getElementById(modal.getAttribute('aria-labelledby'));
  expect(label).not.toBeNull();
  expect(label.contains(document.getElementById('pairName'))).toBe(true);
});

test('opening asks for the host in the modal and makes no request', () => {
  pairClient(4, 'sat');
  expect(document.getElementById('pairModal').style.display).toBe('flex');
  expect(document.getElementById('pairHost').value).toBe(location.hostname);
  expect(api).not.toHaveBeenCalled();
  expect(global.prompt).not.toHaveBeenCalled();
});

test('Cancel aborts with no request', async () => {
  pairClient(4, 'sat');
  closePairModal();
  await generatePairing();
  expect(api).not.toHaveBeenCalled();
  expect(document.getElementById('pairModal').style.display).toBe('none');
});

test('Generate uses the typed host and shows the bundle', async () => {
  pairClient(4, 'sat');
  document.getElementById('pairHost').value = '10.0.0.9';
  await generatePairing();
  expect(api.mock.calls[0][0]).toBe('/clients/4/pairing?host=10.0.0.9');
  expect(document.getElementById('pairResult').classList.contains('hidden')).toBe(false);
  expect(document.getElementById('pairBundle').textContent).toContain('"key": "k"');
});

test('a response that arrives after Cancel is discarded', async () => {
  let resolve;
  api.mockReturnValue(new Promise(r => { resolve = r; }));
  pairClient(4, 'sat');
  const pending = generatePairing();
  closePairModal();
  resolve({ key: 'late' });
  await pending;
  expect(document.getElementById('pairBundle').textContent).toBe('');
});

test('Copy puts the bundle JSON on the clipboard', async () => {
  const toast = mockFn('showToast');
  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  pairClient(4, 'sat');
  await generatePairing();
  await copyPairBundle();
  expect(writeText).toHaveBeenCalledWith(document.getElementById('pairBundle').textContent);
  expect(toast.mock.calls[0][1]).not.toBe('error');
});

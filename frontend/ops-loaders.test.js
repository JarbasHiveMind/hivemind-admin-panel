/**
 * @jest-environment jsdom
 *
 * The certificate and policy loaders must show a failed request. A policy
 * editor that stays empty after a failed load also invites a save of `[]`,
 * which replaces the real chain on the server.
 */

'use strict';

const { evalApp, resetDom, mockFn } = require('./helpers/setup');

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <div id="certsContainer">Loading…</div>
    <div id="policyLoadError" hidden></div>
    <textarea id="policyEditor"></textarea>`);
});

describe('loadCerts', () => {
  test('a failed request replaces "Loading" with an error state and a toast', async () => {
    mockFn('apiCall').mockRejectedValue(new Error('boom'));
    const toast = mockFn('showToast');
    await loadCerts();
    const box = document.getElementById('certsContainer');
    expect(box.textContent).not.toContain('Loading');
    expect(box.textContent).toContain('boom');
    expect(box.querySelector('[role="alert"]')).not.toBeNull();
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('boom'), 'error');
  });

  test('the server message is escaped', async () => {
    mockFn('apiCall').mockRejectedValue(new Error('<img src=x onerror=alert(1)>'));
    mockFn('showToast');
    await loadCerts();
    expect(document.getElementById('certsContainer').querySelector('img')).toBeNull();
  });

  test('a successful request shows the certificate state', async () => {
    mockFn('apiCall').mockResolvedValue({ ssl_enabled: true, cert_exists: true, key_exists: false,
                                         cert_path: '/c.pem', key_path: '/k.pem' });
    const toast = mockFn('showToast');
    await loadCerts();
    const box = document.getElementById('certsContainer');
    expect(box.textContent).toContain('/c.pem');
    expect(box.querySelector('[role="alert"]')).toBeNull();
    expect(toast).not.toHaveBeenCalled();
  });
});

describe('loadPolicy', () => {
  test('a failed request shows an error and locks the editor', async () => {
    mockFn('apiCall').mockRejectedValue(new Error('forbidden'));
    const toast = mockFn('showToast');
    await loadPolicy();
    const err = document.getElementById('policyLoadError');
    expect(err.hidden).toBe(false);
    expect(err.getAttribute('role')).toBe('alert');
    expect(err.textContent).toContain('forbidden');
    expect(document.getElementById('policyEditor').disabled).toBe(true);
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('forbidden'), 'error');
  });

  test('save after a failed load sends nothing', async () => {
    const api = mockFn('apiCall');
    api.mockRejectedValue(new Error('forbidden'));
    const toast = mockFn('showToast');
    await loadPolicy();
    api.mockClear();
    // what a user types into the empty editor, or what an earlier load left
    document.getElementById('policyEditor').value = '[]';
    api.mockResolvedValue({});
    toast.mockClear();
    await savePolicy();
    expect(api).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error');
  });

  test('save while the load is still pending sends nothing', async () => {
    const api = mockFn('apiCall');
    const toast = mockFn('showToast');
    // GET /policy never answers: a hung request, or loadCerts still pending
    api.mockReturnValue(new Promise(() => {}));
    loadPolicy();
    document.getElementById('policyEditor').value = '[]';
    api.mockClear();
    api.mockResolvedValue({});
    await savePolicy();
    expect(api).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error');
  });

  test('the editor in index.html starts locked, before any load runs', () => {
    const fs = require('fs');
    const path = require('path');
    const html = fs.readFileSync(
      path.join(__dirname, '..', 'hivemind_admin_panel', 'static', 'index.html'), 'utf8');
    const tag = html.match(/<textarea[^>]*id="policyEditor"[^>]*>/);
    expect(tag).not.toBeNull();
    expect(tag[0]).toMatch(/\sdisabled[\s>=]/);
  });

  test('a later successful load clears the error and unlocks the editor', async () => {
    const api = mockFn('apiCall');
    mockFn('showToast');
    api.mockRejectedValue(new Error('forbidden'));
    await loadPolicy();
    api.mockResolvedValue({ chain: [{ module: 'x' }] });
    await loadPolicy();
    const editor = document.getElementById('policyEditor');
    expect(editor.disabled).toBe(false);
    expect(JSON.parse(editor.value)).toEqual([{ module: 'x' }]);
    expect(document.getElementById('policyLoadError').hidden).toBe(true);
  });
});

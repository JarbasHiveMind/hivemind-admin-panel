/**
 * @jest-environment jsdom
 *
 * A failed request must be visible to the user. It must not leave a blank
 * panel, report a count of zero, or block the page with alert().
 */

'use strict';

const { evalApp, resetDom, mockFn } = require('./helpers/setup');

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <div id="topologyContainer"></div>
    <div id="pluginStatusGrid"></div>
    <textarea id="policyEditor"></textarea>
    <div id="configBackups"></div><pre id="configBackupDiff" hidden></pre>`);
});

describe('loadTopologyPage', () => {
  test('shows an error state and an error toast when /topology fails', async () => {
    mockFn('apiCall').mockRejectedValue(new Error('boom'));
    const toast = mockFn('showToast');
    await loadTopologyPage();
    const box = document.getElementById('topologyContainer');
    expect(box.textContent).toContain('boom');
    expect(box.querySelector('[role="alert"]')).not.toBeNull();
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error');
  });
});

describe('renderPluginStatusGrid', () => {
  test('a failed count is shown as unknown, not as zero or as no plugins', () => {
    renderPluginStatusGrid({ stt: null, tts: 2, ww: 0, vad: 0, network: 0, agent: 0, database: 0, binary: 0 });
    const grid = document.getElementById('pluginStatusGrid');
    expect(grid.textContent).toContain('STT');
    expect(grid.textContent).toContain('—');
    expect(grid.textContent).toContain('TTS');
  });

  test('all counts failing does not claim that no plugins are installed', () => {
    renderPluginStatusGrid({ stt: null, tts: null, ww: null, vad: null, network: null, agent: null, database: null, binary: null });
    const grid = document.getElementById('pluginStatusGrid');
    expect(grid.textContent).not.toContain('No plugins installed');
  });

  test('zero counts still read as no plugins installed', () => {
    renderPluginStatusGrid({ stt: 0, tts: 0, ww: 0, vad: 0, network: 0, agent: 0, database: 0, binary: 0 });
    expect(document.getElementById('pluginStatusGrid').textContent).toContain('No plugins installed');
  });
});

describe('savePolicy', () => {
  test('success is a toast, not alert()', async () => {
    document.getElementById('policyEditor').value = '[]';
    mockFn('apiCall').mockResolvedValue({});
    const toast = mockFn('showToast');
    await savePolicy();
    expect(global.alert).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.any(String));
  });

  test('invalid JSON is an error toast and makes no request', async () => {
    document.getElementById('policyEditor').value = '[';
    const api = mockFn('apiCall');
    const toast = mockFn('showToast');
    await savePolicy();
    expect(global.alert).not.toHaveBeenCalled();
    expect(api).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error');
  });

  test('a server failure is not reported as invalid JSON', async () => {
    document.getElementById('policyEditor').value = '[]';
    mockFn('apiCall').mockRejectedValue(new Error('forbidden'));
    const toast = mockFn('showToast');
    await savePolicy();
    expect(global.alert).not.toHaveBeenCalled();
    const [msg, type] = toast.mock.calls[0];
    expect(type).toBe('error');
    expect(msg).toContain('forbidden');
    expect(msg).not.toMatch(/JSON/);
  });
});

describe('diffConfigBackup', () => {
  test('shows the diff inline, not in alert()', async () => {
    mockFn('apiCall').mockResolvedValue({ added: { a: 1 }, removed: {}, changed: { b: 2 } });
    await diffConfigBackup('server.json.1');
    expect(global.alert).not.toHaveBeenCalled();
    const pre = document.getElementById('configBackupDiff');
    expect(pre.hidden).toBe(false);
    expect(pre.textContent).toContain('server.json.1');
    expect(pre.textContent).toContain('a');
    expect(pre.textContent).toContain('b');
  });
});

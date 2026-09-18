/**
 * @jest-environment jsdom
 *
 * Server-supplied text (test results, error messages, validation errors) must
 * reach the DOM as text, never as markup.
 */

'use strict';

const { evalApp, resetDom, mockFn } = require('./helpers/setup');

const PAYLOAD = '<img src=x onerror="window.__pwned=1">';

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <input id="ovosBusHost" /><input id="ovosBusPort" />
    <div id="ovosBusTestResult"></div>
    <div id="enablePluginStatus"></div>
    <div id="solverPluginsContainer"></div>
    <div id="serversContainer"></div>
    <textarea id="configEditor"></textarea><div id="configValidationResult"></div>`);
});

describe('editPersona', () => {
  function stubPersonaLoad(persona) {
    const api = mockFn('apiCall').mockResolvedValue(persona);
    mockFn('loadMemoryModules').mockResolvedValue(undefined);
    mockFn('loadSolverPluginsForPersona').mockResolvedValue(undefined);
    return api;
  }

  test('renders a stored solver name as text in the selected list and the config sections', async () => {
    stubPersonaLoad({ name: 'p', solvers: [PAYLOAD] });
    await editPersona('p');
    const selected = document.getElementById('personaSelectedSolvers');
    const configs = document.getElementById('personaSolverConfigContainer');
    expect(selected.querySelector('img')).toBeNull();
    expect(configs.querySelector('img')).toBeNull();
    expect(selected.textContent).toContain('<img src=x');
    expect(configs.textContent).toContain('<img src=x');
  });

  test('encodes the persona name in the API path', async () => {
    const api = stubPersonaLoad({ name: 'a b/../secret?x=1', solvers: [] });
    await editPersona('a b/../secret?x=1');
    expect(api.mock.calls[0][0]).toBe('/personas/' + encodeURIComponent('a b/../secret?x=1'));
  });
});

describe('loadServersPage', () => {
  test('a server id cannot break out of the health element attribute', async () => {
    const id = 'x"><img src=y onerror="window.__pwned=1">';
    mockFn('apiCall').mockResolvedValue([{ id, name: 'n', type: 't', url: 'u' }]);
    await loadServersPage();
    const container = document.getElementById('serversContainer');
    expect(container.querySelector('img')).toBeNull();
    // the attribute still holds the real id, so checkServer() can find the element
    expect(document.getElementById('health-' + id)).not.toBeNull();
  });
});

function assertNoInjectedMarkup(el) {
  expect(el.querySelector('img')).toBeNull();
  expect(el.textContent).toContain('<img src=x');
}

describe('testOvosBusConnection', () => {
  test('escapes a success message from the server', async () => {
    mockFn('apiCall').mockResolvedValue({ success: true, message: PAYLOAD });
    await testOvosBusConnection();
    assertNoInjectedMarkup(document.getElementById('ovosBusTestResult'));
  });

  test('escapes a failure message from the server', async () => {
    mockFn('apiCall').mockResolvedValue({ success: false, message: PAYLOAD });
    await testOvosBusConnection();
    assertNoInjectedMarkup(document.getElementById('ovosBusTestResult'));
  });

  test('escapes an API error message', async () => {
    mockFn('apiCall').mockRejectedValue(new Error(PAYLOAD));
    await testOvosBusConnection();
    assertNoInjectedMarkup(document.getElementById('ovosBusTestResult'));
  });

  test('encodes host and port into the query string', async () => {
    const api = mockFn('apiCall').mockResolvedValue({ success: true, message: 'ok' });
    document.getElementById('ovosBusHost').value = 'h&port=1#x';
    document.getElementById('ovosBusPort').value = '81 81';
    await testOvosBusConnection();
    const url = api.mock.calls[0][0];
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('host')).toBe('h&port=1#x');
    expect(params.get('port')).toBe('81 81');
    expect(params.getAll('port')).toHaveLength(1);
  });
});

describe('testProfileInModal', () => {
  test.each([
    [{ success: true, message: PAYLOAD }],
    [{ success: false, message: PAYLOAD }],
  ])('escapes the server message %#', async (result) => {
    const sel = document.getElementById('profileModule');
    sel.innerHTML = '<option value="hivemind-redis-db-plugin">redis</option>';
    sel.value = 'hivemind-redis-db-plugin';
    mockFn('_collectProfileConfig').mockReturnValue({});
    mockFn('apiCall').mockResolvedValue(result);
    await testProfileInModal();
    assertNoInjectedMarkup(document.getElementById('profileTestStatus'));
  });
});

describe('confirmActivateProfile', () => {
  test('escapes the server message', async () => {
    document.getElementById('activateProfileTarget').value = 'p';
    mockFn('apiCall').mockResolvedValue({ message: PAYLOAD, clients_migrated: 0 });
    mockFn('renderDatabaseProfiles');
    mockFn('closeActivateProfileModal');
    mockFn('showRestartRequiredModal');
    await confirmActivateProfile();
    assertNoInjectedMarkup(document.getElementById('activateProfileStatus'));
  });
});

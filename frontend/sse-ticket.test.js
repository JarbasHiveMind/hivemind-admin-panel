/**
 * @jest-environment jsdom
 *
 * The live monitor must open its stream with a one-time ticket, never with
 * the login token. EventSource cannot set headers, so whatever the page puts
 * in that URL reaches the access log and the browser history.
 */

'use strict';

const { evalApp, resetDom, mockFn } = require('./helpers/setup');

const TOKEN = 'login-token-value';

let opened;

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend',
    '<input type="checkbox" id="monitorLive" checked />');
  opened = [];
  global.EventSource = function (url) {
    opened.push(url);
    this.addEventListener = jest.fn();
    this.close = jest.fn();
  };
  window.eval(`auth = { token: ${JSON.stringify(TOKEN)}, role: 'admin' };`);
});

test('the stream URL carries a ticket and not the login token', async () => {
  const apiCall = mockFn('apiCall').mockResolvedValue({ ticket: 'one-time-ticket' });

  await startMonitorLive();

  expect(apiCall).toHaveBeenCalledWith('/events/ticket', 'POST');
  expect(opened).toHaveLength(1);
  expect(opened[0]).toContain('ticket=one-time-ticket');
  expect(opened[0]).not.toContain(TOKEN);
  expect(opened[0]).not.toContain('access_token');
});

test('a refused ticket opens no stream and clears the checkbox', async () => {
  mockFn('apiCall').mockRejectedValue(new Error('HTTP 401'));
  const toast = mockFn('showToast');

  await startMonitorLive();

  expect(opened).toHaveLength(0);
  expect(document.getElementById('monitorLive').checked).toBe(false);
  expect(toast).toHaveBeenCalledWith('Live view failed: HTTP 401', 'error');
});

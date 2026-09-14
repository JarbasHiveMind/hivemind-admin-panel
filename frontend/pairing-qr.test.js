/**
 * @jest-environment jsdom
 *
 * The pairing QR image must not carry the bearer token in its URL.
 */

'use strict';

const { evalApp, resetDom, mockFn } = require('./helpers/setup');

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <div id="pairModal" style="display:none"><span id="pairName"></span>
    <div id="pairQr"></div><pre id="pairBundle"></pre></div>`);
  global.prompt = jest.fn(() => '10.0.0.5');
  let n = 0;
  URL.createObjectURL = jest.fn(() => `blob:qr-${n++}`);
  URL.revokeObjectURL = jest.fn();
  global.fetch = jest.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['<svg/>']) }));
  mockFn('apiCall').mockResolvedValue({ key: 'k' });
});

test('no token appears in the image URL or the QR request URL', async () => {
  await pairClient(3, 'sat');
  const img = document.querySelector('#pairQr img');
  expect(img).not.toBeNull();
  expect(img.getAttribute('src')).toBe('blob:qr-0');
  expect(document.getElementById('pairQr').innerHTML).not.toContain('access_token');
  const [url, opts] = global.fetch.mock.calls[0];
  expect(url).toBe('/api/clients/3/pairing/qr.svg?host=10.0.0.5');
  expect(url).not.toContain('access_token');
  expect(opts.headers.Authorization).toMatch(/^Bearer /);
});

test('closing and reopening revokes the previous blob URL', async () => {
  await pairClient(3, 'sat');
  closePairModal();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:qr-0');
  await pairClient(3, 'sat');
  expect(document.querySelector('#pairQr img').getAttribute('src')).toBe('blob:qr-1');
});

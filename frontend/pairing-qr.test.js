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
  // the host is typed in the modal (#94), no prompt() any more
  document.body.insertAdjacentHTML('beforeend', `
    <div id="pairModal" style="display:none"><span id="pairName"></span>
    <div id="pairHostStep"><input id="pairHost"></div>
    <div id="pairResult" class="hidden"><div id="pairQr"></div><pre id="pairBundle"></pre></div></div>`);
  let n = 0;
  URL.createObjectURL = jest.fn(() => `blob:qr-${n++}`);
  URL.revokeObjectURL = jest.fn();
  global.fetch = jest.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['<svg/>']) }));
  mockFn('apiCall').mockResolvedValue({ key: 'k' });
});

async function pairWithHost(id, host) {
  pairClient(id, 'sat');
  document.getElementById('pairHost').value = host;
  await generatePairing();
}

test('no token appears in the image URL or the QR request URL', async () => {
  await pairWithHost(3, '10.0.0.5');
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
  await pairWithHost(3, '10.0.0.5');
  closePairModal();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:qr-0');
  await pairWithHost(3, '10.0.0.5');
  expect(document.querySelector('#pairQr img').getAttribute('src')).toBe('blob:qr-1');
});

/**
 * @jest-environment jsdom
 *
 * Modal stack: Escape closes the modal opened last and runs its close
 * function; focus moves into a modal on open, stays inside on Tab, and
 * returns to the opener on close.
 */

'use strict';

const { evalApp, resetDom } = require('./helpers/setup');

const flush = () => new Promise(r => queueMicrotask(r));

beforeAll(() => evalApp());
beforeEach(() => {
  resetDom();
  document.body.insertAdjacentHTML('beforeend', `
    <button id="opener">open</button>
    <div id="pairModal" style="display:none;"><button id="pairA">a</button><button id="pairB">b</button></div>
    <div id="bridgeModal" class="modal"><input id="bridgeIn" /><button id="bridgeBtn">x</button></div>
    <div id="firstRunModal" style="display:none;"><button>ok</button></div>`);
});

function key(k, opts = {}) {
  const ev = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...opts });
  document.activeElement.dispatchEvent(ev);
  return ev;
}

test('Escape closes the modal opened last, not the last in DOM order', async () => {
  // bridgeModal is later in the DOM but opens first.
  document.getElementById('bridgeModal').classList.add('active');
  await flush();
  document.getElementById('pairModal').style.display = 'flex';
  await flush();
  key('Escape');
  await flush();
  expect(document.getElementById('pairModal').style.display).toBe('none');
  expect(document.getElementById('bridgeModal').classList.contains('active')).toBe(true);
});

test('Escape runs the modal close function', async () => {
  const spy = jest.fn(() => document.getElementById('bridgeModal').classList.remove('active'));
  const orig = window.closeBridgeModal;
  window.closeBridgeModal = spy;
  try {
    document.getElementById('bridgeModal').classList.add('active');
    await flush();
    key('Escape');
    expect(spy).toHaveBeenCalledTimes(1);
  } finally {
    window.closeBridgeModal = orig;
  }
});

test('focus moves into the modal on open and back to the opener on close', async () => {
  document.getElementById('opener').focus();
  document.getElementById('pairModal').style.display = 'flex';
  await flush();
  expect(document.activeElement.id).toBe('pairA');
  key('Escape');
  await flush();
  expect(document.activeElement.id).toBe('opener');
});

test('Tab and Shift+Tab stay inside the top modal', async () => {
  document.getElementById('pairModal').style.display = 'flex';
  await flush();
  document.getElementById('pairB').focus();
  expect(key('Tab').defaultPrevented).toBe(true);
  expect(document.activeElement.id).toBe('pairA');
  expect(key('Tab', { shiftKey: true }).defaultPrevented).toBe(true);
  expect(document.activeElement.id).toBe('pairB');
});

test('the first-run gate does not close on Escape', async () => {
  document.getElementById('firstRunModal').style.display = 'flex';
  await flush();
  key('Escape');
  expect(document.getElementById('firstRunModal').style.display).toBe('flex');
});

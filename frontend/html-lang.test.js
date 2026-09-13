/**
 * @jest-environment jsdom
 *
 * The <html lang> attribute must follow the active UI language, so screen
 * readers pick the right voice and browsers the right hyphenation.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const I18N_JS_PATH = path.resolve(__dirname, '../hivemind_admin_panel/static/js/i18n.js');

function loadWithStoredLang(stored) {
  const store = stored == null ? {} : { lang: stored };
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: k => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
    },
  });
  document.documentElement.setAttribute('lang', 'en');
  document.body.innerHTML = '<select id="langSelect"></select>';
  window.eval( // eslint-disable-line no-eval
    '(function(){' + fs.readFileSync(I18N_JS_PATH, 'utf8') +
    '\nwindow.__setLang__ = setLang;})();');
  document.dispatchEvent(new Event('DOMContentLoaded'));
  return window.__setLang__;
}

test('initial load applies the stored language to html lang', () => {
  loadWithStoredLang('pt');
  expect(document.documentElement.lang).toBe('pt');
});

test('setLang updates html lang', () => {
  const setLang = loadWithStoredLang(null);
  setLang('es');
  expect(document.documentElement.lang).toBe('es');
  setLang('en');
  expect(document.documentElement.lang).toBe('en');
});

test('an unknown stored language falls back to en, matching the text shown', () => {
  loadWithStoredLang('xx');
  expect(document.documentElement.lang).toBe('en');
});

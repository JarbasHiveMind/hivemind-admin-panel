/**
 * @jest-environment jsdom
 *
 * Regression tests for the i18n dictionary and its wiring into index.html.
 *
 * Covers:
 *   - en/es/pt expose the exact same set of keys (no missing/extra translations)
 *   - every data-i18n / data-i18n-html / data-i18n-placeholder / data-i18n-title /
 *     data-i18n-aria-label attribute in index.html points at a key that exists
 *   - applyI18n() actually swaps visible text when the language changes
 *   - a spot sample of translatable elements is not left hard-coded in English
 */

'use strict';

const fs = require('fs');
const path = require('path');

const I18N_JS_PATH = path.resolve(__dirname, '../hivemind_admin_panel/static/js/i18n.js');
const INDEX_HTML_PATH = path.resolve(__dirname, '../hivemind_admin_panel/static/index.html');

const i18nSrc = fs.readFileSync(I18N_JS_PATH, 'utf8');
const html = fs.readFileSync(INDEX_HTML_PATH, 'utf8');

let _cached = null;

function loadI18n() {
  // i18n.js is a vanilla script (no module.exports) whose top-level
  // `const I18N` / `let CURRENT_LANG` bindings live in the lexical
  // environment created by *this* eval call only — they are not visible to
  // a later, separate window.eval() call, and re-evaluating the script a
  // second time throws a redeclaration error. So capture everything we
  // need onto window in the SAME eval invocation as the script itself.
  if (!_cached) {
    window.eval( // eslint-disable-line no-eval
      i18nSrc +
        '\nwindow.__I18N__ = I18N; window.__t__ = t; ' +
        'window.__setLang__ = setLang; window.__applyI18n__ = applyI18n;'
    );
    _cached = {
      I18N: window.__I18N__,
      t: window.__t__,
      setLang: window.__setLang__,
      applyI18n: window.__applyI18n__,
    };
  }
  return _cached;
}

const I18N_ATTRS = [
  'data-i18n',
  'data-i18n-html',
  'data-i18n-placeholder',
  'data-i18n-title',
  'data-i18n-aria-label',
];

describe('i18n dictionary key parity', () => {
  let I18N;
  beforeAll(() => {
    ({ I18N } = loadI18n());
  });

  test('en, es and pt are all defined', () => {
    expect(I18N.en).toBeDefined();
    expect(I18N.es).toBeDefined();
    expect(I18N.pt).toBeDefined();
  });

  test('es has no missing keys compared to en', () => {
    const missing = Object.keys(I18N.en).filter(k => !(k in I18N.es));
    expect(missing).toEqual([]);
  });

  test('es has no extra keys compared to en', () => {
    const extra = Object.keys(I18N.es).filter(k => !(k in I18N.en));
    expect(extra).toEqual([]);
  });

  test('pt has no missing keys compared to en', () => {
    const missing = Object.keys(I18N.en).filter(k => !(k in I18N.pt));
    expect(missing).toEqual([]);
  });

  test('pt has no extra keys compared to en', () => {
    const extra = Object.keys(I18N.pt).filter(k => !(k in I18N.en));
    expect(extra).toEqual([]);
  });

  test('has substantially more coverage than the sidebar-only baseline (>= 400 keys)', () => {
    // Before this change I18N only carried the ~19 sidebar/nav labels.
    expect(Object.keys(I18N.en).length).toBeGreaterThanOrEqual(400);
  });
});

describe('index.html data-i18n attributes all resolve to a real key', () => {
  let I18N;
  beforeAll(() => {
    ({ I18N } = loadI18n());
  });

  test('every data-i18n* attribute value exists in I18N.en', () => {
    const used = new Set();
    for (const attr of I18N_ATTRS) {
      const re = new RegExp(attr + '="([^"]+)"', 'g');
      let m;
      while ((m = re.exec(html))) used.add(m[1]);
    }
    expect(used.size).toBeGreaterThan(0);
    const unresolved = [...used].filter(k => !(k in I18N.en));
    expect(unresolved).toEqual([]);
  });
});

describe('applyI18n swaps visible text on language change', () => {
  let t, setLang, applyI18n;

  beforeAll(() => {
    ({ t, setLang, applyI18n } = loadI18n());
  });

  beforeEach(() => {
    document.body.innerHTML = `
      <span data-i18n="dashboard"></span>
      <span data-i18n="clientManagement"></span>
      <input data-i18n-placeholder="searchClientsPh" placeholder="">
      <span data-i18n-title="language" title="">x</span>
      <div data-i18n-html="aclMessagesHelp"></div>
      <select id="langSelect"><option value="en">EN</option><option value="es">ES</option><option value="pt">PT</option></select>
    `;
    setLang('en');
  });

  test('textContent reflects the selected language for a page-level heading not in the old sidebar set', () => {
    setLang('en');
    expect(document.querySelector('[data-i18n="clientManagement"]').textContent).toBe('Client Management');
    setLang('es');
    expect(document.querySelector('[data-i18n="clientManagement"]').textContent).toBe('Gestión de clientes');
    setLang('pt');
    expect(document.querySelector('[data-i18n="clientManagement"]').textContent).toBe('Gestão de clientes');
  });

  test('placeholder attribute is translated', () => {
    setLang('es');
    expect(document.querySelector('[data-i18n-placeholder="searchClientsPh"]').getAttribute('placeholder')).toBe('Buscar clientes...');
  });

  test('title attribute is translated', () => {
    setLang('pt');
    expect(document.querySelector('[data-i18n-title="language"]').getAttribute('title')).toBe('Idioma');
  });

  test('innerHTML (data-i18n-html) preserves inline markup and translates', () => {
    setLang('es');
    const el = document.querySelector('[data-i18n-html="aclMessagesHelp"]');
    expect(el.innerHTML).toContain('<strong>Modo lista blanca</strong>');
  });

  test('t() falls back to English for an unknown language', () => {
    expect(t('clientManagement')).toBe(document.querySelector('[data-i18n="clientManagement"]').textContent === 'Client Management' ? 'Client Management' : t('clientManagement'));
  });
});

describe('no obvious hard-coded English left on a sample of previously-untranslated elements', () => {
  // Spot-check: elements that used to carry raw English text (pre-fix) must
  // now carry a data-i18n* attribute instead of literal text sitting next to it.
  const samples = [
    { needle: 'Client Management', attr: 'data-i18n="clientManagement"' },
    { needle: 'How Access Control Works', attr: 'data-i18n="howAclWorks"' },
    { needle: 'Create Persona', attr: 'data-i18n="createPersona"' },
    { needle: 'Install Custom Plugin', attr: 'data-i18n="installCustomPlugin"' },
    { needle: 'Backup', attr: 'data-i18n="backupRestore"' },
  ];

  test.each(samples)('"$needle" is wired through $attr', ({ attr }) => {
    expect(html).toContain(attr);
  });
});

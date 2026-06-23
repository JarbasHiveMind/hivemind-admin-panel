# Extending the panel

For developers adding features. Read [Architecture](architecture.md) first for the
injection seam and threading model; this page is the practical "how do I add X".

## Module map

```
hivemind_admin_panel/
├── api.py        the FastAPI app + every REST endpoint (one file, ~100 routes)
├── __main__.py   the launcher: builds the app, starts hivemind-core in-process,
│                 _tracked_protocol() (live connections + message tap)
├── _auth.py      tokens, roles, password hashing, audit log
├── _metrics.py   thread-safe counters + event/message ring buffers (METRICS)
├── version.py    VERSION_BLOCK (bumped by CI — don't hand-edit)
└── static/       the SPA: index.html, js/app.js, js/i18n.js, css/style.css
```

The app object is `api.app`; `__main__.app` wraps it (mounts it under `/api` and
serves the SPA). So a route declared `@app.get("/foo")` is served at `/api/foo`.

## Add a REST endpoint

Append to `api.py` (grouped under a `# ===== section =====` banner). Use the
shared dependencies for auth:

```python
@app.get("/widgets", dependencies=[Depends(verify_credentials)])   # any authed user
def list_widgets() -> List[Dict[str, Any]]:
    return [...]

@app.post("/widgets", dependencies=[Depends(require_admin)])        # admin role only
def make_widget(data: WidgetCreate) -> Dict[str, Any]:
    ...
```

- **Auth**: `verify_credentials` accepts HTTP Basic *or* `Authorization: Bearer`.
  Use `require_admin` for destructive actions. Get the caller with
  `_current_user(request)` (add `request: Request` to the signature).
- **Live core objects**: read the module globals `_db`, `_service`, `_protocol`
  (set by `init_injected_objects`). They may be `None` in `--no-core` mode —
  degrade gracefully, don't 500.
- **Read `ProcessStatus`** as `_service._status.state.name` (it has **no**
  `.value` — that mistake only crashes with a live service).
- **Metrics/audit**: call `METRICS.event(...)` / `METRICS.incr(...)` for
  observable actions; mutating requests are audit-logged automatically by the
  middleware.
- **Models**: define a `pydantic.BaseModel` for request bodies.

Then add an end-to-end test (see below) and a row in
[api-reference.md](api-reference.md).

## Add a UI page

The SPA is dependency-free vanilla JS. Three edits:

1. **Nav button** in `static/index.html` (in the `<nav>`):

   ```html
   <button class="nav-item" onclick="navigate('widgets')" data-page="widgets">
       <span class="nav-icon">🧩</span><span data-i18n="widgets">Widgets</span>
   </button>
   ```

2. **Page container** in `index.html` (a `<div id="widgetsPage" class="page">…</div>`).

3. **Wire `navigate()`** in `app.js`: add a title and a load call:

   ```js
   widgets: 'Widgets',                       // in the titles map
   if (page === 'widgets') loadWidgetsPage(); // in the dispatch
   ```

   Then write `loadWidgetsPage()` using `apiCall('/widgets')` (it prefixes `/api`
   and adds auth). **Always HTML-escape** user data with the existing `esc()`
   helper.

Browser `EventSource` (SSE) can't send headers — for live feeds, mint a token via
`/auth/login` and pass it as `?access_token=` (the API accepts it; see
`startMonitorLive`).

## Add a translation string

`static/js/i18n.js` holds `I18N = { en: {...}, es: {...}, pt: {...} }`. Add your
key to each language, tag the element `data-i18n="key"`, and `applyI18n()` swaps
it on load and on language change. Untranslated keys fall back to English.

## Tap hivemind-core internals (advanced)

The panel gets authoritative live state **without changing hivemind-core** by
subclassing its listener protocol in `__main__._tracked_protocol()` — overriding
`handle_message` / `handle_new_client` / etc. to feed `METRICS`, then injecting the
live instance. If you need a new live signal, add an override there. Keep
overrides thin (record, then `return super()...`).

## Testing

The suite (`tests/`) is genuinely end-to-end: a real FastAPI `TestClient` against a
real `ClientDatabase` in an isolated temp-XDG dir (see `tests/conftest.py`). Use
the fixtures `client`, `auth`, `make_client`. Only stub true external boundaries
(`subprocess`/pip, sockets, plugin discovery). Run:

```bash
pytest tests/ -v
```

Conventions: one test file per domain; Apache-2.0 SPDX header on new files; never
hand-edit `version.py`; work on a feature branch and let CI (the gh-automations
workflows) run build-tests/coverage/lint/license-check. See
[Development](development.md).

---

<!-- nav-footer -->
|  |  |  |
|:--|:-:|--:|
| ← [Architecture](architecture.md) | [📖 Docs home](index.md) | [API reference](api-reference.md) → |

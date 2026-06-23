# Glossary

Plain-language definitions of the terms a newcomer meets when running or operating the **HiveMind Admin Panel** — the web UI that manages a HiveMind voice-mesh hivemind-core built on OpenVoiceOS. Cross-references use `[[term]]` for entries in this page and ordinary links for the surrounding docs.

## A

**Access key (`api_key`)** — The per-client public identifier a [[satellite]] presents when connecting to the [[hivemind-core]]. It pairs with the client's [[password (client)]] and optional [[crypto key]] to authenticate the connection. Auto-generated (16 random bytes, hex) when a [[client]] is created if you don't supply one; set to the literal `REVOKED` to disable a client without deleting it. See [configuration](configuration.md) and the client model in [api-reference](api-reference.md).

**ACL (access control list)** — The full set of per-client permissions stored in the [[database backend]]: [[allowed_types]], the [[message blacklist]], [[skill blacklist]], [[intent blacklist]], the [[admin flag (client)]], and the [[escalate]]/[[propagate]]/[[broadcast]] flags. It governs what a given [[satellite]] is allowed to send into or receive from the [[mesh]]. Distinct from the panel's own [[role]] system, which controls who may use the admin UI.

**Admin flag (client)** — A boolean on a [[client]] (`is_admin`) that marks a [[satellite]] as a trusted admin node, letting it issue privileged HiveMind messages to the [[hivemind-core]]. Toggled via `make-admin` / `revoke-admin` (or in bulk). Not to be confused with the panel's `admin` [[role]], which is about the web UI.

**Admin panel (the)** — This project: a FastAPI web application plus a single-page UI that reads and writes the same on-disk state (`server.json`, the client DB, personas) as [[hivemind-core]]. By default it also launches hivemind-core [[in-process hivemind-core]], so it can show live connections and restart the service. See [architecture](architecture.md).

**Admission policy** — See [[policy chain]].

**Agent engine** — A modern OVOS plugin implementing `AbstractAgentEngine` (`ovos_plugin_manager.templates.agents`). Engines come in typed flavours — chat, memory, summarizer, reranker, retrieval, QA, yes/no, multimodal, coreference — and are the building blocks a [[persona]] composes via its [[handler]]s. They replace the deprecated [[solver plugin]] stack. Listed by `GET /plugins/agents`.

**Agent protocol** — The pluggable layer (selected by the `agent_protocol` block in `server.json`) that decides how hivemind-core turns an incoming utterance into a response — e.g. routing it to a local OVOS core or to a [[persona]]. Loaded through `AgentProtocolFactory`; the active [[persona]] is recorded here. Compare [[network protocol]] and [[binary protocol]].

**Allowed types (`allowed_types`)** — A per-client **whitelist** of [[message type]]s the [[client]] is permitted to emit. HiveMind is whitelist-only for message types: if a type is not in `allowed_types`, it is rejected. Edited with the `allow-msg` / `blacklist-msg` endpoints (blacklisting here simply removes the type from the whitelist).

**Audit log** — An append-only record of every mutating admin request (`POST`/`PUT`/`DELETE`) with the acting user, path and status, written to `~/.local/share/hivemind-admin/audit.log` and viewable at `GET /audit`. See [operations](operations.md).

## B

**Bearer token** — See [[session token]].

**Binary protocol** — The optional pluggable layer (the `binary_protocol` block, loaded via `BinaryDataHandlerProtocolFactory`) that handles raw binary payloads over the connection, such as streamed audio, separately from JSON control messages. Disabled by setting its `module` to `null`. Compare [[agent protocol]] and [[network protocol]].

**Broadcast** — A message-routing capability (the `can_broadcast` client flag) allowing a node's message to be delivered to all nodes at once. One of the three routing permissions alongside [[escalate]] and [[propagate]].

## C

**Cipher** — An allowed symmetric encryption algorithm for the encrypted transport, listed in `allowed_ciphers` (e.g. `CHACHA20-POLY1305`). Works together with the [[encoding]] and the client [[crypto key]] to secure traffic on the wire.

**Client** — A database record for one node that may connect to the [[hivemind-core]] — typically a [[satellite]] or [[relay]]. It bundles the node's [[access key]], [[password (client)]], optional [[crypto key]] and its full [[ACL]]. Managed under the `/clients/*` endpoints; deleting a client revokes it (its `api_key` becomes `REVOKED`).

**Crypto key** — A per-client symmetric key (must be 16, 24 or 32 characters) used to encrypt the connection's payloads with the negotiated [[cipher]]. Optional; held in the client's credentials alongside [[access key]] and [[password (client)]].

## D

**Database backend** — The pluggable client store hivemind-core uses, chosen by `database.module`: `hivemind-sqlite-database` (default, transactional), `hivemind-json-db-plugin` (simple file JSON), or `hivemind-redis-database` (networked, used by the Docker stack). The panel can switch backends and migrate clients between them. See [configuration](configuration.md#database-backend).

**Database profile** — A named, saved database configuration (`module` + constructor `config`) stored under `~/.config/hivemind-core/database_profiles/*.json`, letting you keep several [[database backend]] setups and activate one (optionally migrating clients into it). Managed via `/database/profiles/*`.

## E

**Encoding** — An allowed wire-format for messages, listed in `allowed_encodings` (e.g. `JSON-B64` — base64-encoded JSON). It describes how a message is serialised/wrapped before transport, separately from the [[cipher]] that encrypts it.

**Escalate** — A routing permission (`can_escalate`) letting a node send a message **upstream** toward a parent hivemind-core in the [[mesh]]. Granted/revoked with `allow-escalate` / `blacklist-escalate`. Compare [[propagate]] and [[broadcast]].

## H

**Handler** — In a modern [[persona]], one entry in the ordered `handlers` list — a response-engine plugin the persona tries in turn until one answers. Handlers are [[agent engine]]s (LLM, factual/tool, or scripted). This is the current OVOS schema; the panel always stores `handlers` even though the legacy `solvers` key is still accepted on input. See [configuration](configuration.md#personas).

**HiveMind** — The distributed voice-mesh framework this panel administers: a network of nodes (one or more hivemind-core instances and their satellites/relays) that exchange OVOS messages under per-client access control. Built on [[OVOS / OpenVoiceOS]].

**hivemind-core** — The backend package the panel manages: the central node that satellites connect to. It owns the client database, config, listener protocol and plugin factories; it authenticates clients, enforces the [[ACL]] and [[policy chain]], routes [[message type]]s, and hands utterances to an [[agent protocol]]/[[persona]]. The panel depends on it and, by default, launches it [[In-process mode|in-process]]. See the coupling seam in [architecture](architecture.md).

## I

**In-process mode** — The default deployment where the panel's launcher (`launch_core()`) constructs the [[hivemind-core]] service and runs it on the main thread inside the same process as the web UI (the panel's uvicorn server runs in a daemon thread). This gives the panel a live reference to hivemind-core, so the [[message inspector]], `/connections`, `/stats` and topology `online` flags are authoritative. The opposite is [[--no-core]]. See [architecture](architecture.md).

**Intent blacklist** — A per-client deny-list of OVOS intent IDs a node is forbidden to trigger. Edited with `allow-intent` / `blacklist-intent`. Compare [[skill blacklist]] and [[message blacklist]].

## M

**Memory plugin** — The conversational-memory [[agent engine]] a [[persona]] uses (its `memory_module`), default `ovos-agents-short-term-memory-plugin`. It retains context across turns. Installed options come from `GET /plugins/memory`.

**Mesh** — The overall graph of connected HiveMind nodes — hivemind-core instances, satellites and relays — across which messages [[escalate]], [[propagate]] and [[broadcast]]. Visualised on the [[topology]] page.

**Message blacklist** — A per-client deny-list of [[message type]]s (`message_blacklist`) that the node may never send or receive, applied on top of the [[allowed_types]] whitelist.

**Message inspector** — A panel feature (`GET /messages/recent`, filterable by `msg_type`/`peer`) that shows recent messages flowing through the live [[in-process hivemind-core]], for debugging mesh traffic. Authoritative only when hivemind-core runs in-process.

**Message type** — The `type` field of an OVOS [[OVOS message bus]] message that names what it is, e.g. `recognizer_loop:utterance` (a spoken request) or `speak` (a spoken response). HiveMind permissions ([[allowed_types]], blacklists) are keyed on these strings.

## N

**Network protocol** — The pluggable transport that carries HiveMind connections, configured under `network_protocol` and loaded via `NetworkProtocolFactory` — e.g. websocket, HTTP or MQTT. Multiple can be enabled at once. Compare [[agent protocol]] and [[binary protocol]].

**--no-core** — The mode where the panel runs *without* launching a hivemind-core instance: no live objects are injected, so live introspection (connections, inspector, restart) degrades gracefully while everything DB/config/filesystem-backed still works against the same on-disk state. The opposite of the [[in-process hivemind-core]]. See [architecture](architecture.md).

## O

**OVOS / OpenVoiceOS** — The open-source voice-assistant platform HiveMind is built on. It defines the message bus, skills, intents and the plugin ecosystem (STT/TTS/agents/personas) that hivemind-core and the admin panel speak in terms of.

**OVOS message bus** — OpenVoiceOS's internal publish/subscribe message bus. Every interaction is a typed JSON message (a [[message type]] plus data); HiveMind extends this bus across the network under access control.

**OVOS servers** — External OpenVoiceOS HTTP services the panel can register and health-check: **ovos-persona-server** (hosts a [[persona]] over an OpenAI/Ollama-style API), **ovos-stt-http-server** (speech-to-text), **ovos-tts-server** (text-to-speech) and **ovos-translate-server** (translation). The registry lives at `~/.config/hivemind-admin/servers.json`. See [ovos-servers](ovos-servers.md).

## P

**Pairing bundle** — The package of everything a [[satellite]] needs to join hivemind-core: its credentials ([[access key]], [[password (client)]], [[crypto key]]) plus hivemind-core's websocket endpoint, returned by `GET /clients/{id}/pairing`. Also rendered as a [[QR pairing]] code. See [operations](operations.md).

**Password (client)** — The per-client secret paired with the [[access key]] to authenticate a [[satellite]]'s connection to hivemind-core. Auto-generated if not supplied. Distinct from the *admin-panel* password (`admin_pass`) used to log into the web UI.

**Persona** — A small JSON document defining an assistant personality and response pipeline: an ordered list of [[handler]]s plus a [[memory plugin]]. Persona files live under `~/.config/ovos_persona/*.json`, are managed via `/personas/*`, and can be tested live in the UI. The active one is recorded in the [[agent protocol]] block. See [configuration](configuration.md#personas).

**Policy chain** — The ordered list of admission rules (the message admission policy) hivemind-core applies to decide whether to accept or drop a message before routing it. Edited via `GET/PUT /policy`. Also called the admission policy. See [operations](operations.md).

**Propagate** — A routing permission (`can_propagate`) letting a node forward a message **sideways** to its sibling nodes in the [[mesh]]. Granted/revoked with `allow-propagate` / `blacklist-propagate`. Compare [[escalate]] and [[broadcast]].

## Q

**QR pairing** — Onboarding a [[satellite]] by displaying the [[pairing bundle]] as a scannable QR code (`GET /clients/{id}/pairing/qr.svg`), so a device can join hivemind-core without typing credentials. Pass `?host=<LAN-IP>` when hivemind-core binds `0.0.0.0`. See [operations](operations.md).

## R

**Relay** — A HiveMind node that forwards messages between other nodes rather than originating them, extending the reach of the [[mesh]] (e.g. bridging a sub-network to the [[hivemind-core]]). Modelled like any other [[client]] with its own [[ACL]].

**Role** — The privilege level of an *admin-panel* user (distinct from the [[admin flag (client)]]): `admin` (full control, including destructive actions like plugin installs, DB migrate/clear, restore and policy/cert writes) or `operator` (read plus non-destructive writes). Extra accounts go in `server.json`'s `users` list. See [operations](operations.md) and [security](security.md).

## S

**Satellite** — A leaf HiveMind node (often a smart speaker or small device) that connects to the [[hivemind-core]] to send utterances and receive responses. Each satellite is backed by a [[client]] record and onboarded via a [[pairing bundle]] / [[QR pairing]].

**Session token** — An HMAC-signed bearer token issued by `POST /auth/login` and sent as `Authorization: Bearer <token>`; it can also ride as `?access_token=` for the SSE event stream (whose `EventSource` API can't set headers). HTTP Basic auth still works for scripts. See [operations](operations.md) and [security](security.md).

**Skill blacklist** — A per-client deny-list of OVOS skill IDs a node is forbidden to invoke. Edited with `allow-skill` / `blacklist-skill`. Compare [[intent blacklist]] and [[message blacklist]].

**Solver plugin** — The **deprecated** earlier response-engine plugin type (`ovos_plugin_manager.solvers` / `templates.solvers`), referenced by a persona's legacy `solvers` key. Superseded by [[agent engine]]s; the panel discovers handlers via the modern agent chat engines with a guarded fallback to legacy solvers for back-compat. See [configuration](configuration.md#personas).

## T

**Topology** — The map of the [[mesh]]: hivemind-core and client nodes with edges and live `online` flags, returned by `GET /topology` and drawn as an interactive SVG. The Topology page is also where you open the [[QR pairing]] modal. See [operations](operations.md).

## X

**XDG config** — The XDG Base Directory convention the panel follows for on-disk state. The shared hivemind-core config is `server.json` at `~/.config/hivemind-core/server.json` (honouring `XDG_CONFIG_HOME`); personas, database profiles and server registries live under sibling `~/.config/...` paths. See [configuration](configuration.md).

---

<!-- nav-footer -->
|  |  |  |
|:--|:-:|--:|
| ← [Tutorial](tutorial.md) | [📖 Docs home](index.md) | [Troubleshooting](troubleshooting.md) → |

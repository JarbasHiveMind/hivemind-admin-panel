# Glossary

Plain-language definitions of the terms a newcomer meets when running or operating the **HiveMind Admin Panel**, the web UI that manages a HiveMind voice-mesh hivemind-core built on OpenVoiceOS. Cross-references use `[[term]]` for entries on this page and ordinary links for the surrounding docs.

## A

**Access key (`api_key`)**: the per-client public identifier a [[satellite]] presents when connecting to the [[hivemind-core]]. It pairs with the client's [[password (client)]] and optional [[crypto key]] to authenticate the connection. It is auto-generated (16 random bytes, hex) when a [[client]] is created, if you do not supply one. Set it to the literal `REVOKED` to disable a client without deleting it. See [Configuration](configuration.md) and the client model in [API reference](api-reference.md).

**ACL (access control list)**: the full set of per-client permissions stored in the [[database backend]]. It covers [[allowed_types]], the [[message blacklist]], [[skill blacklist]], [[intent blacklist]], the [[admin flag (client)]], and the [[escalate]], [[propagate]], and [[broadcast]] flags. It governs what a given [[satellite]] is allowed to send into or receive from the [[mesh]]. It is distinct from the panel's own [[role]] system, which controls who may use the admin UI.

**Admin flag (client)**: a boolean on a [[client]] (`is_admin`) that marks a [[satellite]] as a trusted admin node, letting it issue privileged HiveMind messages to the [[hivemind-core]]. Toggle it with `make-admin` or `revoke-admin` (or in bulk). Do not confuse it with the panel's `admin` [[role]], which is about the web UI.

**Admin panel (the)**: this project. It is a FastAPI web application plus a single-page UI that reads and writes the same on-disk state (`server.json`, the client DB, personas) as [[hivemind-core]]. By default it also launches hivemind-core [[in-process hivemind-core]], so it can show live connections and restart the service. See [Architecture](architecture.md).

**Admission policy**: see [[policy chain]].

**Agent engine**: a modern OVOS plugin implementing `AbstractAgentEngine` (`ovos_plugin_manager.templates.agents`). Engines come in typed flavors: chat, memory, summarizer, reranker, retrieval, QA, yes/no, and coreference, among others. They are the building blocks a [[persona]] composes through its [[handler]]s. They replace the deprecated [[solver plugin]] stack. `GET /plugins/agents` lists them.

**Agent protocol**: the pluggable layer (selected by the `agent_protocol` block in `server.json`) that decides how hivemind-core turns an incoming utterance into a response, for example by routing it to a local OVOS core or to a [[persona]]. It loads through `AgentProtocolFactory`. The active [[persona]] is recorded here. Compare [[network protocol]] and [[binary protocol]].

**Allowed types (`allowed_types`)**: a per-client **whitelist** of [[message type]]s the [[client]] is permitted to emit. HiveMind is whitelist-only for message types. If a type is not in `allowed_types`, it is rejected. Edit it with the `allow-msg` and `deny-msg` endpoints (`blacklist-msg` is a deprecated alias of `deny-msg`).

**Audit log**: an append-only record of every mutating admin request (`POST`, `PUT`, `DELETE`) with the acting user, path, and status, written to `~/.local/share/hivemind-admin/audit.log` and viewable at `GET /audit`. See [Operations](operations.md).

## B

**Bearer token**: see [[session token]].

**Binary protocol**: the optional pluggable layer (the `binary_protocol` block, loaded through `BinaryDataHandlerProtocolFactory`) that handles raw binary payloads over the connection, such as streamed audio, separately from JSON control messages. Disable it by setting its `module` to `null`. Compare [[agent protocol]] and [[network protocol]].

**Broadcast**: a message-routing capability (the `can_broadcast` client flag) that lets a node's message reach all nodes at once. It is one of three routing permissions, alongside [[escalate]] and [[propagate]].

## C

**Cipher**: an allowed symmetric encryption algorithm for the encrypted transport, listed in `allowed_ciphers` (for example `CHACHA20-POLY1305`). It works together with the [[encoding]] and the client [[crypto key]] to secure traffic on the wire.

**Client**: a database record for one node that may connect to the [[hivemind-core]], typically a [[satellite]] or [[relay]]. It bundles the node's [[access key]], [[password (client)]], optional [[crypto key]], and its full [[ACL]]. It is managed under the `/clients/*` endpoints. Deleting a client revokes it (its `api_key` becomes `REVOKED`).

**Crypto key**: a per-client symmetric key (16, 24, or 32 characters) used to encrypt the connection's payloads with the negotiated [[cipher]]. It is optional, and held in the client's credentials alongside [[access key]] and [[password (client)]].

## D

**Database backend**: the pluggable client store hivemind-core uses, chosen by `database.module`. Options are `hivemind-sqlite-database` (default, transactional), `hivemind-json-db-plugin` (simple file JSON), or `hivemind-redis-database` (networked, used by the Docker stack). The panel can switch backends and migrate clients between them. See [Configuration](configuration.md#database-backend).

**Database profile**: a named, saved database configuration (`module` plus constructor `config`) stored under `~/.config/hivemind-core/database_profiles/*.json`. It lets you keep several [[database backend]] setups and activate one, optionally migrating clients into it. Manage it through `/database/profiles/*`.

## E

**Encoding**: an allowed wire format for messages, listed in `allowed_encodings` (for example `JSON-B64`, base64-encoded JSON). It describes how a message is serialized before transport, separately from the [[cipher]] that encrypts it.

**Escalate**: a routing permission (`can_escalate`) that lets a node send a message **upstream** toward a parent hivemind-core in the [[mesh]]. Grant or revoke it with `allow-escalate` or `blacklist-escalate`. Compare [[propagate]] and [[broadcast]].

## H

**Handler**: in a modern [[persona]], one entry in the ordered `handlers` list: a response-engine plugin the persona tries in turn until one answers. Handlers are [[agent engine]]s (LLM, factual/tool, or scripted). This is the current OVOS schema. The panel always stores `handlers`, even though the legacy `solvers` key is still accepted on input. See [Configuration](configuration.md#personas).

**HiveMind**: the distributed voice-mesh framework this panel administers. It is a network of nodes (one or more hivemind-core instances and their satellites or relays) that exchange OVOS messages under per-client access control. It is built on [[OVOS / OpenVoiceOS]].

**hivemind-core**: the backend package the panel manages, the central node that satellites connect to. It owns the client database, config, listener protocol, and plugin factories. It authenticates clients, enforces the [[ACL]] and [[policy chain]], routes [[message type]]s, and hands utterances to an [[agent protocol]] or [[persona]]. The panel depends on it and, by default, launches it [[In-process mode|in-process]]. See the coupling seam in [Architecture](architecture.md).

## I

**In-process mode**: the default deployment where the panel's launcher (`launch_core()`) constructs the [[hivemind-core]] service and runs it on the main thread inside the same process as the web UI (the panel's uvicorn server runs in a daemon thread). This gives the panel a live reference to hivemind-core, so the [[message inspector]], `/connections`, `/stats`, and topology `online` flags are authoritative. The opposite is [[--no-core]]. See [Architecture](architecture.md).

**Intent blacklist**: a per-client deny-list of OVOS intent IDs a node is forbidden to trigger. Edit it with `allow-intent` or `blacklist-intent`. Compare [[skill blacklist]] and [[message blacklist]].

## M

**Memory plugin**: the conversational-memory [[agent engine]] a [[persona]] uses (its `memory_module`), default `ovos-agents-short-term-memory-plugin`. It retains context across turns. Installed options come from `GET /plugins/memory`.

**Mesh**: the overall graph of connected HiveMind nodes, including hivemind-core instances, satellites, and relays, across which messages [[escalate]], [[propagate]], and [[broadcast]]. It is visualized on the [[topology]] page.

**Message blacklist**: removed. hivemind-core is whitelist-only, so there is no per-client message deny-list; a type the node may not send is simply absent from [[allowed_types]].

**Message inspector**: a panel feature (`GET /messages/recent`, filterable by `msg_type` or `peer`) that shows recent messages flowing through the live [[in-process hivemind-core]], for debugging mesh traffic. It is authoritative only when hivemind-core runs in-process.

**Message type**: the `type` field of an OVOS [[OVOS message bus]] message that names what it is, for example `recognizer_loop:utterance` (a spoken request) or `speak` (a spoken response). HiveMind permissions ([[allowed_types]], blacklists) are keyed on these strings.

## N

**Network protocol**: the pluggable transport that carries HiveMind connections, configured under `network_protocol` and loaded through `NetworkProtocolFactory`, for example websocket, HTTP, or MQTT. Multiple can be enabled at once. Compare [[agent protocol]] and [[binary protocol]].

**--no-core**: the mode where the panel runs *without* launching a hivemind-core instance. No live objects are injected, so live introspection (connections, inspector, restart) degrades gracefully, while everything backed by the database, config, or filesystem still works against the same on-disk state. It is the opposite of [[in-process hivemind-core]]. See [Architecture](architecture.md).

## O

**OVOS / OpenVoiceOS**: the open-source voice-assistant platform HiveMind is built on. It defines the message bus, skills, intents, and the plugin ecosystem (STT, TTS, agents, personas) that hivemind-core and the admin panel speak in terms of.

**OVOS message bus**: OpenVoiceOS's internal publish/subscribe message bus. Every interaction is a typed JSON message (a [[message type]] plus data). HiveMind extends this bus across the network under access control.

**OVOS servers**: external OpenVoiceOS HTTP services the panel can register and health-check. These are **ovos-persona-server** (hosts a [[persona]] over an OpenAI- or Ollama-style API), **ovos-stt-http-server** (speech-to-text), **ovos-tts-server** (text-to-speech), and **ovos-translate-server** (translation). The registry lives at `~/.config/hivemind-admin/servers.json`. See [OVOS servers](ovos-servers.md).

## P

**Pairing bundle**: the package of everything a [[satellite]] needs to join hivemind-core: its credentials ([[access key]], [[password (client)]], [[crypto key]]) plus hivemind-core's websocket endpoint, returned by `GET /clients/{id}/pairing`. It is also rendered as a [[QR pairing]] code. See [Operations](operations.md).

**Password (client)**: the per-client secret paired with the [[access key]] to authenticate a [[satellite]]'s connection to hivemind-core. It is auto-generated if not supplied. It is distinct from the *admin-panel* password (`admin_pass`) used to log into the web UI.

**Persona**: a small JSON document defining an assistant personality and response pipeline: an ordered list of [[handler]]s plus a [[memory plugin]]. Persona files live under `~/.config/ovos_persona/*.json`, are managed through `/personas/*`, and can be tested live in the UI. The active one is recorded in the [[agent protocol]] block. See [Configuration](configuration.md#personas).

**Policy chain**: the ordered list of admission rules (the message admission policy) hivemind-core applies to decide whether to accept or drop a message before routing it. Edit it through `GET`/`PUT /policy`. Also called the admission policy. See [Operations](operations.md).

**Propagate**: a routing permission (`can_propagate`) that lets a node forward a message **sideways** to its sibling nodes in the [[mesh]]. Grant or revoke it with `allow-propagate` or `blacklist-propagate`. Compare [[escalate]] and [[broadcast]].

## Q

**QR pairing**: onboarding a [[satellite]] by displaying the [[pairing bundle]] as a scannable QR code (`GET /clients/{id}/pairing/qr.svg`), so a device can join hivemind-core without typing credentials. Pass `?host=<LAN-IP>` when hivemind-core binds `0.0.0.0`. See [Operations](operations.md).

## R

**Relay**: a HiveMind node that forwards messages between other nodes rather than originating them, extending the reach of the [[mesh]] (for example, bridging a sub-network to the [[hivemind-core]]). It is modeled like any other [[client]], with its own [[ACL]].

**Role**: the privilege level of an *admin-panel* user, distinct from the [[admin flag (client)]]. It is either `admin` (full control, including destructive actions like plugin installs, DB migrate/clear, restore, and policy/cert writes) or `operator` (read plus non-destructive writes). Extra accounts go in `server.json`'s `users` list. See [Operations](operations.md) and [Security](security.md).

## S

**Satellite**: a leaf HiveMind node (often a smart speaker or small device) that connects to the [[hivemind-core]] to send utterances and receive responses. Each satellite is backed by a [[client]] record and onboarded through a [[pairing bundle]] or [[QR pairing]].

**Session token**: an HMAC-signed bearer token issued by `POST /auth/login` and sent as `Authorization: Bearer <token>`. It can also ride as `?access_token=` for the SSE event stream, whose `EventSource` API cannot set headers. HTTP Basic auth still works for scripts. See [Operations](operations.md) and [Security](security.md).

**Skill blacklist**: a per-client deny-list of OVOS skill IDs a node is forbidden to invoke. Edit it with `allow-skill` or `blacklist-skill`. Compare [[intent blacklist]] and [[message blacklist]].

**Solver plugin**: the **deprecated** earlier response-engine plugin type (`ovos_plugin_manager.solvers` / `templates.solvers`), referenced by a persona's legacy `solvers` key. It is superseded by [[agent engine]]s. The panel discovers handlers through the modern agent chat engines, with a guarded fallback to legacy solvers for back-compat. See [Configuration](configuration.md#personas).

## T

**Topology**: the map of the [[mesh]], showing hivemind-core and client nodes with edges and live `online` flags, returned by `GET /topology` and drawn as an interactive SVG. The Topology page is also where you open the [[QR pairing]] modal. See [Operations](operations.md).

## X

**XDG config**: the XDG Base Directory convention the panel follows for on-disk state. The shared hivemind-core config is `server.json` at `~/.config/hivemind-core/server.json` (honoring `XDG_CONFIG_HOME`). Personas, database profiles, and server registries live under sibling `~/.config/...` paths. See [Configuration](configuration.md).

---
[← Tutorial](tutorial.md) · [Home](index.md) · [Troubleshooting →](troubleshooting.md)

# OVOS servers & homelab synergy

A hivemind-core rarely runs alone. In a homelab it pairs naturally with the family
of **OVOS network servers** — small HTTP services that host one OVOS capability so
many devices (and hivemind-core) can share it instead of each satellite running heavy
models locally. This panel manages hivemind-core and its personas; the servers below
provide the speech and reasoning that hivemind-core brokers to satellites.

## The server family

| Server | Serves | Pairs with |
|--------|--------|------------|
| [ovos-persona-server](https://github.com/OpenVoiceOS/ovos-persona-server) | a persona (chat/agent handler chain) over an **OpenAI- and Ollama-compatible** HTTP API | the personas you manage here |
| [ovos-stt-http-server](https://github.com/OpenVoiceOS/ovos-stt-http-server) | any STT plugin over HTTP | remote/streaming speech-to-text |
| [ovos-tts-server](https://github.com/OpenVoiceOS/ovos-tts-server) | any TTS plugin over HTTP | shared text-to-speech |
| [ovos-translate-server](https://github.com/OpenVoiceOS/ovos-translate-server) | translation plugins over HTTP | multilingual pipelines |

Each is "bring your own plugin": you pick the STT/TTS/translation/solver plugin, the
server exposes it on the network, and every node points at one endpoint. One GPU box
can serve STT + TTS + an LLM persona to many low-power satellites.

## ovos-persona-server ↔ this panel

The single most useful pairing. A **persona** here is a JSON document declaring a
`memory_module` and an ordered list of `handlers` (chat/agent engines — see
[Configuration](configuration.md#personas)). `ovos-persona-server` loads that **same
persona JSON** and hosts it as an HTTP service speaking the OpenAI and Ollama
protocols:

```bash
# host a persona you authored in the panel
ovos-persona-server --persona ~/.config/ovos_persona/my-persona.json \
                    --host 0.0.0.0 --port 8337
```

Now any OpenAI/Ollama client can call it — including:

- the **`hivemind-persona-agent-plugin`** agent protocol, so HiveMind satellites get
  streaming `natural_language_query` answers from a shared persona;
- Home Assistant / Music Assistant and other homelab tooling that already speaks the
  OpenAI API;
- the `ovos-solver-openai-persona-plugin` on any OVOS device, pointing its `api_url`
  at the server.

Because a persona can be built from search/knowledge/scripted handlers (DuckDuckGo,
Wikipedia, Wolfram Alpha, RiveScript, a failure fallback) it needs **no GPU**; LLM
handlers are optional and can be mixed with factual/tool handlers.

## A homelab topology

```
          ┌─────────────────────────────────────────────┐
          │  GPU / always-on box                         │
          │   ovos-stt-http-server   :8080               │
          │   ovos-tts-server        :9666               │
          │   ovos-persona-server    :8337  (OpenAI/Ollama)
          └───────────────┬─────────────────────────────┘
                          │ HTTP
          ┌───────────────┴───────────────┐
          │  hivemind-core (this panel)     │  ← agent/STT/TTS plugins point at the servers
          │   hivemind-admin-panel  :8100  │
          └───────────────┬───────────────┘
                          │ encrypted mesh (websocket :5678)
        ┌─────────────────┼──────────────────┐
     satellite         satellite           relay → more satellites
```

hivemind-core's agent protocol (persona) and the satellites' STT/TTS can all be pointed at
the networked servers, so the satellites stay thin. The panel is where you provision
satellite clients + ACLs, author the persona the persona-server hosts, and pick which
agent/STT/TTS/database plugins hivemind-core uses.

## See also

- [Configuration → Personas](configuration.md#personas) — the persona schema this panel writes
- [Deployment](deployment.md) — running hivemind-core + panel (and the Compose stack)
- The broader OVOS server list also includes `ovos-bus-server`, `ovos-ww-server`,
  and `ovos-opendata-server`.

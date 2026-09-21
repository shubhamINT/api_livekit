# Guides

Guides are for building something *against* this platform, as opposed to using it or operating it.

- [Architecture](../architecture/index.md) explains how the running system behaves.
- [API Reference](../api/authentication.md) documents the endpoints you call.
- **Guides** — this section — walk through implementing a component the platform expects to exist
  but does not ship.

Dive in:

- [Build a Meeting Connector](meeting-connector.md) — the contract a meeting connector implements:
  the dispatch name, the job metadata, the mixed audio track, the `lk.publish_on_behalf` match, the
  four lifecycle events, the two rules that decide whether the meeting can hear the assistant, when
  `ready` may be emitted, and the teardown rules that decide whether the bot leaves. Ends with a
  walkthrough of building a connector for a platform other than Google Meet.

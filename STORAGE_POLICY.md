# Storage Policy

Git stores source, schemas, public-safe documentation, synthetic replay
fixtures, and sanitized capability profiles. Private or fast-growing data is
routed through portable roots.

| Variable | Role |
| --- | --- |
| `AOA_GOPRO_DATA_ROOT` | Device registry, operation/event journals and manifests |
| `AOA_GOPRO_CACHE_ROOT` | Preview buffers, proxies and resumable transfer state |
| `AOA_GOPRO_AUTH_ROOT` | Credentials, certificates, approvals and private device identity |
| `AOA_GOPRO_ARTIFACT_ROOT` | Receipts, telemetry and semantic derivatives, reports |
| `AOA_GOPRO_MEDIA_ROOT` | Retained original media |

`AOA_GOPRO_INSTANCE_ROOT` may expand to the five child roots. Without explicit
configuration, tiny network-free fixture runs use `.connector-state/`.

On this host a future private instance may be routed under
`/srv/abyss-machine/storage/connectors/aoa-gopro-connector`; regenerable decode
or model caches belong under `/srv/abyss-machine/cache`. These are host-specific
examples, not public defaults, and host creation remains an `abyss-machine`
change.

Ingest is retention-neutral by default. Inventory and immutable manifests come
before selective transfer. Original media is never modified by the connector;
deletion requires a separate exact plan and Operator approval.

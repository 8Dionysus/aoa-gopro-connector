# aoa-gopro-connector

`aoa-gopro-connector` turns an operator-authorized GoPro into a governed camera
capability: discoverable state, explicit operation plans, postcondition
receipts, preview and media integrity, and eventually optional Labs, semantic,
and multicamera extensions.

The repository is independently installable and headless. Its first supported
development profile is a stock GoPro HERO13 Black over USB/NCM HTTP. Current
proof and limitations live only in [`STATUS.md`](STATUS.md).

## Shape

- `src/aoa_gopro_connector/` owns domain and application code.
- `connector/schemas/` owns stable packet contracts.
- `connector/fixtures/` contains synthetic, public-safe replay input.
- `connector/profiles/` contains sanitized named capability profiles.
- `connector/SOURCE_POLICY.md` owns authorized camera/media/effect posture.
- `STORAGE_POLICY.md` owns portable roots and retention classes.
- `docs/ARCHITECTURE.md` owns component and state topology.
- `docs/RUNTIME_CONTRACT.md` owns CLI, daemon, and future agent boundaries.

The CLI currently provides a network-free doctor, a replayable read-only probe,
and an allowlisted live read-only HTTP probe. It has no effect command surface.
Consult `aoa-gopro --help` for exact syntax.

Runtime deployment belongs to `abyss-stack`. Host USB, Bluetooth, network,
permissions, storage, and thermal facts belong to `abyss-machine`.

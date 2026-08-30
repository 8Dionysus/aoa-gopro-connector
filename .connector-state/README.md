# Local connector state

The committed directories make a fresh clone usable for tiny offline tests:

- `data/`: registries, journals, and manifests;
- `cache/`: regenerable buffers and transfer state;
- `auth/`: private identity, credentials, certificates, and approvals;
- `artifacts/`: receipts and derived evidence;
- `media/`: retained originals.

Everything generated inside these directories is ignored.

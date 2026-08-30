# Runtime Contract

The package is independently runnable. `abyss-stack` owns long-running
deployment and authenticated agent exposure, not the connector's application
semantics.

## Current interfaces

- `doctor` inspects package, Python/SDK compatibility, schemas, and portable
  storage configuration without contacting a camera.
- `replay-probe` converts a public-safe fixture through the same probe contract
  used by live HTTP.
- `probe` performs only the three GET routes in the read allowlist, discards raw
  responses, and emits a sanitized capability profile.
- `schema validate` checks a document against a repository-owned packet schema.

The parser and `--help` own exact syntax.

## Exit and output posture

Commands emit one JSON document to stdout. Diagnostics go to stderr. Success is
exit code zero; validation, transport, redaction, or contract failure is
non-zero and does not emit a success profile.

A profile contains no base URL or real device/network identity. Writing a
profile is explicit; stdout is the default.

## Future boundaries

The loopback daemon will expose versioned read, candidate-plan, event, and
receipt lookup contracts. Local operator effects will require approval. An
agent effect surface can appear only through a separately admitted
`abyss-stack` bridge that consumes the exact plan and returns the exact receipt.

Health/readiness, runtime deployment, transport contact, effect admission,
semantic acceptance, and Goal acceptance remain distinct claims.

# Android patch capture package v2

`capture-package.schema.json` is the frozen 2.0 read/preflight contract.
`capture-package-v2.1.schema.json` is the additive materializer input contract. It
adds versioned evidence contracts, component-precise evidence membership,
conditional qualifiers, and N/A basis fields without redefining old 2.0 bytes.

The capture runtime writes 2.1 and validates cross-references, local-only
authority, status, and the full file inventory before an atomic local publish.
It records neutral, versioned evidence facts and exact component membership; it
does not bundle or interpret AKBS qualification groups or adapter contracts.
Neither version grants upload, server ID, server qualification, or
knowledge-materialization authority. The engineering writer and local validator
accept any supported layer in the seven-layer capture taxonomy. A downstream
consumer owns any narrower, independently versioned acceptance gate.

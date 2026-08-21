# phoenix-helix-c

Double Helix implementation in C for Lost Ark (Phoenix DevOps OS).

## Design Goals

- Horseshoe / daisy chain flow in core paths (minimize loops)
- Fail fast with rich diagnostics
- Automatic journaling: **What + Why + Recommended Action**
- Clean integration with existing Suit + Frank layer
- R2-primary clonepool + D1 Custody/Glossary split

## Current Status

This is the initial skeleton. Ingress and Egress are currently stubs.

Next steps:
- Implement real hex generation
- Implement R2 + D1 integration in Ingress
- Implement local cache + R2 fallback in Egress
- Add proper diagnostic context in hot paths

## Build

```bash
make
```

Produces `libhelix.a`

## Public API

See `include/helix.h`

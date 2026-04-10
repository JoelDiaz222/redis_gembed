# redis_gembed

A Redis module that brings ML-powered text embedding generation into Redis, by using the
[Gembed Rust core](https://github.com/JoelDiaz222/gembed).

The module is a thin adapter that marshals Redis command arguments into the C ABI of the portable Gembed Rust core
(`libgembed`), which handles model loading and inference.

## Commands

| Command | Description |
|---|---|
| `G.EMBED <backend> <model> <text>` | Embed a single string → binary float32 blob |
| `G.EMBEDS <backend> <model> <text> [<text> …]` | Embed multiple strings → array of blobs |

### Return Format

Both commands return raw **little-endian IEEE-754 float32** bytes:

- `G.EMBED` → bulk-string of `dim × 4` bytes
- `G.EMBEDS` → Redis array, each element a bulk-string of `dim × 4` bytes

### Examples

```bash
# Embed one document
G.EMBED embed_anything sentence-transformers/all-MiniLM-L6-v2 "First document"

# Get multiple embeddings
G.EMBEDS embed_anything sentence-transformers/all-MiniLM-L6-v2 \
    "First document" \
    "Second document" \
    "Third document"
```

## Architecture

```
┌───────────────────────────────────────────────┐
│           Redis Client Command                │
│   G.EMBED embed_anything <model> "Hello"      │
└──────────────────────┬────────────────────────┘
                       │  Redis Module API
                       ▼
┌───────────────────────────────────────────────┐
│       Redis Module (redis_gembed.so)          │
│  - Parses argv                                │
│  - Builds StringSlice / InputData structs     │
│  - Calls C FFI                                │
└──────────────────────┬────────────────────────┘
                       │  C FFI
                       ▼
┌───────────────────────────────────────────────┐
│       Rust Core Library (libgembed)           │
│  Backends: embed_anything / FastEmbed /       │
│            ORT / gRPC / HTTP                  │
└───────────────────────────────────────────────┘
                       │
                       ▼
          raw float32[] bytes → Redis reply
```

## Installation

### Prerequisites

- Redis 7+ (or Valkey; Redis Stack for vector search)
- Rust toolchain (`cargo`)
- `gcc` / `clang`

### Build

```bash
git clone --recurse-submodules https://github.com/JoelDiaz222/redis_gembed
cd redis_gembed

# Fetch the Redis module header
make deps

# Build Rust core + Redis module
make
```

### Load

```bash
# At server start
redis-server --loadmodule /path/to/redis_gembed.so

# Persistent (add to redis.conf)
loadmodule /path/to/redis_gembed.so
```

**Hot-loading (Redis 7+):** `MODULE LOAD` is disabled by default. To enable it, start your server with:

```bash
redis-server --enable-module-command local
```

Then load at runtime:

```bash
make load
# or
redis-cli MODULE LOAD /path/to/redis_gembed.so
```

## Demo

A self-contained Python demo is included in `demo/demo.py`. It demonstrates end-to-end semantic search using `redis_gembed` and Redis/Valkey's native vectorset module.

```bash
make demo
```

## License

Licensed under the [Apache License 2.0](./LICENSE).

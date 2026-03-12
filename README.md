# redis_gembed

## Generate Text Embeddings directly in Redis/Valkey

A Redis module that brings ML-powered text embedding generation into Redis,
using the same Gembed Rust core as [pg_gembed](https://github.com/JoelDiaz222/pg_gembed).

## Commands

| Command                                              | Description                                 |
|------------------------------------------------------|---------------------------------------------|
| `GEMBED.EMBED <embedder> <model> <text>`             | Embed a single string → binary float32 blob |
| `GEMBED.EMBEDS <embedder> <model> <text> [<text> …]` | Embed multiple strings → array of blobs     |

### Examples

```bash
# Embed one document
GEMBED.EMBED embed_anything sentence-transformers/all-MiniLM-L6-v2 "First document"

# Get multiple embeddings
GEMBED.EMBEDS embed_anything sentence-transformers/all-MiniLM-L6-v2 \
    "First document" \
    "Second document" \
    "Third document"
```

### Return Format

Both commands return **raw little-endian IEEE-754 float32** bytes:

- `GEMBED.EMBED` → bulk-string of `dim × 4` bytes
- `GEMBED.EMBEDS` → Redis array, each element a bulk-string of `dim × 4` bytes

## Supported Embedders & Models

`redis_gembed` uses the [portable Gembed Rust library](https://github.com/JoelDiaz222/gembed). Any embedder/model pair
registered there can be used with this module.

## Architecture

```
┌──────────────────────────────────────────┐
│          Redis Client Command            │
│   GEMBED.EMBED embed_anything <model>    │
│                  "Hello Redis"           │
└─────────────────────┬────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────┐
│        Redis Module (redis_gembed.so)    │
│  - Parses argv                           │
│  - Builds StringSlice / InputData        │
│  - Calls C FFI                           │
└─────────────────────┬────────────────────┘
                      │  C FFI  (same ABI as pg_gembed)
                      ▼
┌──────────────────────────────────────────┐
│      Rust Core Library (libgembed.a)     │
│  fastembed / embed_anything / gRPC / HTTP│
└──────────────────────────────────────────┘
                      │
                      ▼
        raw float32[] bytes → Redis reply
```

## Installation

### Prerequisites

- Redis 7+ (or Redis Stack for vector search)
- Rust toolchain (`cargo`)
- `gcc` / `clang`

### Build

```bash
git clone --recurse-submodules https://github.com/JoelDiaz222/redis_gembed
cd redis_gembed

# Fetch the Redis module header
make deps

# Build Rust library + Redis module
make
```

### Load

You can load the module by providing the `.so` path when starting the server:

```bash
# With the command line
redis-server --loadmodule /path/to/redis_gembed.so

# Persistent (add to redis.conf)
loadmodule /path/to/redis_gembed.so
```

**Loading at runtime (Redis 7+)**: Redis 7.0+ disabled the `MODULE LOAD` command by default for security reasons. If
you want to hot-load the module into an *already running* server via `redis-cli`, or use the `make load` / `make demo`
Makefile targets, you must start your server with local module commands enabled:

```bash
redis-server --enable-module-command local
```

Then you can hot-load it:
```bash
# Using the Makefile
make load

# With redis-cli
redis-cli MODULE LOAD /path/to/redis_gembed.so
```

### Semantic Search Python Demo

A self-contained Python demo is included in `demo/demo.py`. Demonstrates the full integration between redis_gembed and
Redis/Valkey's vectorset module.

```bash
make demo
```

## License

Apache License 2.0

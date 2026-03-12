"""
redis_gembed + vectorset demo: Semantic Article Search
========================================================

Demonstrates the full integration between redis_gembed and Redis/Valkey's
native vectorset module:

  1. Batch-embed 15 articles via GEMBED.EMBEDS
  2. Index them with VADD + SETATTR (category + year metadata)
  3. Run semantic searches via GEMBED.EMBED + VSIM
  4. Run hybrid searches combining vector similarity with attribute filters
  5. Inspect the index with VINFO / VCARD / VGETATTR

Requirements:
    pip install redis
    redis-server (or valkey-server) running with:
      - redis_gembed.so loaded
      - vectorset module loaded (built-in on Redis/Valkey 8+)

Usage:
    python3 demo.py
"""

import sys
import textwrap

import redis

# Configuration
HOST     = "127.0.0.1"
PORT     = 6379
EMBEDDER = "embed_anything"
MODEL    = "sentence-transformers/all-MiniLM-L6-v2"
VSET     = "articles"   # vectorset key name

# Dataset
ARTICLES = [
    {
        "name": "attention-is-all-you-need",
        "title": "Attention Is All You Need",
        "text": (
            "The Transformer architecture replaces recurrent and convolutional "
            "layers entirely with multi-head self-attention mechanisms. It "
            "achieves state-of-the-art results on translation tasks while "
            "being significantly more parallelisable."
        ),
        "category": "nlp",
        "year": 2017,
    },
    {
        "name": "graph-neural-networks",
        "title": "Graph Neural Networks: A Review",
        "text": (
            "GNNs generalise deep learning to graph-structured data by passing "
            "messages between nodes along edges. They excel at molecular property "
            "prediction, social network analysis, and knowledge graph reasoning."
        ),
        "category": "deep-learning",
        "year": 2019,
    },
    {
        "name": "diffusion-models",
        "title": "Diffusion Models for High-Resolution Image Synthesis",
        "text": (
            "Denoising diffusion probabilistic models iteratively reverse a "
            "Gaussian noising process to generate photorealistic images. Guided "
            "diffusion and latent diffusion variants have set new quality "
            "benchmarks on ImageNet and text-to-image generation."
        ),
        "category": "generative-ai",
        "year": 2022,
    },
    {
        "name": "rlhf",
        "title": "Reinforcement Learning from Human Feedback",
        "text": (
            "RLHF fine-tunes language models using a reward model trained on "
            "human preference comparisons. It is the key technique behind "
            "InstructGPT and ChatGPT, aligning model outputs with human intent."
        ),
        "category": "alignment",
        "year": 2022,
    },
    {
        "name": "onnx-runtime",
        "title": "The ONNX Runtime: Cross-Platform ML Inference",
        "text": (
            "ONNX Runtime is an open-source inference engine for ONNX models. "
            "It supports CPU, GPU, and specialised accelerators through a unified "
            "execution provider API, enabling models from PyTorch or TensorFlow "
            "to run efficiently in production without framework dependencies."
        ),
        "category": "inference",
        "year": 2020,
    },
    {
        "name": "vector-databases",
        "title": "Vector Databases: The Emerging Storage Layer for AI",
        "text": (
            "Vector databases store high-dimensional embeddings and support "
            "approximate nearest-neighbour search using indices such as HNSW "
            "and IVF. They power semantic search, recommendation systems, and "
            "retrieval-augmented generation pipelines."
        ),
        "category": "infrastructure",
        "year": 2023,
    },
    {
        "name": "rag",
        "title": "Retrieval-Augmented Generation",
        "text": (
            "RAG combines a dense retriever with a generative language model. "
            "At inference time, relevant documents are fetched from a knowledge "
            "base and concatenated with the user prompt, grounding the model's "
            "response in up-to-date factual information."
        ),
        "category": "nlp",
        "year": 2023,
    },
    {
        "name": "lora",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "text": (
            "LoRA freezes pretrained model weights and injects trainable "
            "low-rank decomposition matrices into each transformer layer. This "
            "reduces the number of trainable parameters by orders of magnitude "
            "while matching full fine-tuning performance."
        ),
        "category": "nlp",
        "year": 2022,
    },
    {
        "name": "flash-attention",
        "title": "FlashAttention: Fast and Memory-Efficient Attention",
        "text": (
            "FlashAttention rewrites the attention computation to be IO-aware, "
            "tiling the query/key/value matrices to avoid materialising the full "
            "N×N attention matrix. This yields 2–4× wall-clock speedups and "
            "linear memory usage in sequence length."
        ),
        "category": "efficiency",
        "year": 2022,
    },
    {
        "name": "quantisation",
        "title": "Quantisation of Neural Networks for Edge Deployment",
        "text": (
            "Post-training quantisation and quantisation-aware training reduce "
            "model weights from 32-bit floats to 8-bit or 4-bit integers. "
            "This dramatically shrinks model size and inference latency, enabling "
            "deployment on mobile and embedded devices."
        ),
        "category": "inference",
        "year": 2021,
    },
    {
        "name": "kubernetes-ml",
        "title": "Kubernetes for ML Workloads",
        "text": (
            "Kubernetes orchestrates containerised ML training and serving jobs "
            "using GPU node selectors, resource limits, and custom operators such "
            "as Kubeflow. Autoscaling and rolling deployments simplify going from "
            "experiment to production."
        ),
        "category": "mlops",
        "year": 2021,
    },
    {
        "name": "dvc",
        "title": "Data Versioning with DVC",
        "text": (
            "DVC adds version control for datasets and model artefacts on top of "
            "Git. Pipelines are defined as DAGs, enabling reproducible experiments "
            "and remote storage backends such as S3 or GCS."
        ),
        "category": "mlops",
        "year": 2020,
    },
    {
        "name": "prompt-engineering",
        "title": "LLM Prompt Engineering Best Practices",
        "text": (
            "Effective prompt engineering uses chain-of-thought reasoning, "
            "few-shot examples, and structured output instructions to steer large "
            "language model behaviour without updating weights. Systematic prompt "
            "evaluation frameworks help catch regressions."
        ),
        "category": "nlp",
        "year": 2023,
    },
    {
        "name": "rust-systems",
        "title": "Rust for Systems Programming",
        "text": (
            "Rust's ownership model guarantees memory safety without a garbage "
            "collector. Its zero-cost abstractions and fearless concurrency make "
            "it popular for high-performance networking, operating systems, and "
            "embedded firmware."
        ),
        "category": "systems",
        "year": 2021,
    },
    {
        "name": "postgres-extensions",
        "title": "PostgreSQL Extensions: Extending the Database Engine",
        "text": (
            "PostgreSQL extensions allow developers to add new data types, "
            "operators, index access methods, and functions directly inside the "
            "database process. Extensions like pgvector and PostGIS demonstrate "
            "how the engine can be specialised for entirely new domains."
        ),
        "category": "infrastructure",
        "year": 2022,
    },
]

# Helpers
def section(title: str) -> None:
    width = 72
    print()
    print("─" * width)
    print(f"  {title}")
    print("─" * width)


def print_results(results: list, articles_by_name: dict) -> None:
    """Pretty-print VSIM results (alternating name / score pairs)."""
    # VSIM WITHSCORES returns [name, score, name, score, ...]
    pairs = list(zip(results[0::2], results[1::2]))
    print(f"  {'Score':>6}  {'Category':<16}  Title")
    print(f"  {'─'*6}  {'─'*16}  {'─'*45}")
    for name_bytes, score_bytes in pairs:
        name  = name_bytes.decode()
        score = float(score_bytes)
        art   = articles_by_name.get(name, {})
        title = art.get("title", name)
        cat   = art.get("category", "?")
        snippet = textwrap.shorten(art.get("text", ""), width=72, placeholder="…")
        print(f"  {score:>6.4f}  {cat:<16}  {title}")
        print(f"           {snippet}")
        print()


# Main
def main() -> None:

    # Connect
    print(f"\n  Connecting to Redis/Valkey at {HOST}:{PORT} …")
    r = redis.Redis(host=HOST, port=PORT, decode_responses=False)
    try:
        r.ping()
    except redis.ConnectionError as e:
        print(f"\n  ERROR: Could not connect — {e}")
        sys.exit(1)

    articles_by_name = {a["name"]: a for a in ARTICLES}

    # Clean up any previous run
    r.delete(VSET)

    # Step 1: Batch embed
    section("Step 1 — Batch-embed all articles via GEMBED.EMBEDS")

    texts = [a["text"] for a in ARTICLES]
    print(f"  Calling GEMBED.EMBEDS with {len(texts)} texts…")

    blobs: list[bytes] = r.execute_command(
        "GEMBED.EMBEDS", EMBEDDER, MODEL, *texts
    )

    dim = len(blobs[0]) // 4
    print(f"  ✓  {len(blobs)} embeddings received, dim = {dim}")

    # Step 2: Index with VADD + SETATTR
    section("Step 2 — Index articles in vectorset via VADD")

    import json
    pipe = r.pipeline(transaction=False)
    for article, blob in zip(ARTICLES, blobs):
        attrs = json.dumps({
            "category": article["category"],
            "year":     article["year"],
            "title":    article["title"],
        })
        pipe.execute_command(
            "VADD", VSET, "FP32", blob, article["name"],
            "SETATTR", attrs
        )
    pipe.execute()
    print(f"  ✓  Indexed {len(ARTICLES)} articles into vectorset '{VSET}'")

    # Step 3: Inspect the index
    section("Step 3 — Inspect the vectorset")

    card = r.execute_command("VCARD", VSET)
    vdim = r.execute_command("VDIM",  VSET)
    print(f"  VCARD  → {card} elements")
    print(f"  VDIM   → {vdim} dimensions")

    # Show attributes for one element
    sample = ARTICLES[0]["name"]
    attrs_raw = r.execute_command("VGETATTR", VSET, sample)
    print(f"\n  VGETATTR {VSET} {sample}")
    print(f"    → {attrs_raw.decode()}")

    # Step 4: Semantic search
    section("Step 4 — Semantic search (GEMBED.EMBED + VSIM)")

    queries = [
        "how to make language models follow instructions",
        "running models efficiently on low-power hardware",
        "storing and searching vector embeddings at scale",
        "speeding up transformer training with less GPU memory",
        "versioning datasets and reproducing ML experiments",
    ]

    for query in queries:
        blob = r.execute_command("GEMBED.EMBED", EMBEDDER, MODEL, query)
        results = r.execute_command(
            "VSIM", VSET, "FP32", blob,
            "COUNT", 3,
            "WITHSCORES"
        )
        print(f"\n  Query: \"{query}\"")
        print_results(results, articles_by_name)

    # Step 5: Hybrid search
    section("Step 5 — Hybrid search (vector similarity + attribute filter)")

    hybrid_queries = [
        ("efficient inference and model deployment",  '.category == "inference"'),
        ("large language model fine-tuning",          '.category == "nlp"'),
        ("ML pipelines and experiment tracking",      '.category == "mlops"'),
        ("recent papers from 2023",                   '.year == 2023'),
    ]

    for query, filt in hybrid_queries:
        blob = r.execute_command("GEMBED.EMBED", EMBEDDER, MODEL, query)
        results = r.execute_command(
            "VSIM", VSET, "FP32", blob,
            "COUNT", 3,
            "WITHSCORES",
            "FILTER", filt
        )
        print(f"\n  Query:  \"{query}\"")
        print(f"  Filter: {filt}")
        print_results(results, articles_by_name)

    # Step 6: Find similar to an existing element
    section("Step 6 — Find articles similar to an existing element (VSIM ELE)")

    seed = "rag"
    results = r.execute_command(
        "VSIM", VSET, "ELE", seed,
        "COUNT", 4,
        "WITHSCORES"
    )
    print(f"\n  Articles most similar to '{seed}':")
    print_results(results, articles_by_name)

    print("\n  Demo complete.\n")


if __name__ == "__main__":
    main()

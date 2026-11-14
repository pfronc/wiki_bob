# Hybrid retrieval in bob-rag: BM25 + embeddinggemma + RRF

`bob-rag search` (`tools/rag.py:search_chunks`) is hybrid by default.
It runs lexical and semantic ranking in parallel, then merges them
with rank fusion. Neither method is assumed "more precise" — they are
complementary: exact words vs. meaning.

Pipeline:

```text
query ─┬─► BM25 (SQLite, always) ──────────────► rank list #1 ─┐
       └─► embeddinggemma (Ollama, if possible) ─► rank list #2 ─┴─► RRF ─► fused results
```

Degrades to BM25-only with a `note` when vectors are missing,
Ollama is down, or no vector score is positive.

## 1. BM25 — lexical / exact-word search

Best Matching 25. Classic sparse bag-of-words ranking, an improved TF-IDF.
Runs locally in SQLite, no Ollama needed.

Per query term `t` in passage `D`:

```text
score(D,Q) = Σ IDF(t) · TF(t,D)·(k1+1) / (TF(t,D) + k1·(1-b+b·|D|/avgdl))
```

- `TF` — term frequency in the passage. Saturates via `k1 = 1.2`
  (`tools/rag.py:65`): mentioning `qubit` 10× is not 10× better than 1×.
- `IDF` — rarity across the whole store. `no-cloning` counts far more
  than `what` / `is`.
- Length norm `b = 0.75`: short focused passages (e.g. `§Definition`)
  beat long dumps that mention the word once.
- `tokenize()` lowercases, splits, drops glue/pieces before scoring.

Strength: precise on formulas, names, symbols, stable IDs
(`CNOT`, `src_...:p042:c03`).
Weakness: no paraphrase — `copy unknown state` scores 0 against
a passage that only says `no-cloning theorem`.

## 2. embeddinggemma — semantic / meaning search

Google's open ~300M-parameter text embedding model, run locally via
Ollama. Default in `tools/rag.py`:

```python
DEFAULT_EMBED_MODEL = "embeddinggemma"
```

It maps text to a 768-dimensional vector of floats. Meaning ≈ direction;
similarity is cosine between vectors (`-1 … 1`).

How `bob-rag` uses it:

1. `index`: split `wiki/*.md` per section → ~1200 chars with 150 overlap
   (`CHUNK_TARGET_CHARS`, `CHUNK_OVERLAP_CHARS`) → `POST /api/embed
   {"model": "embeddinggemma"}` → store vector blob in
   `index/rag/rag.sqlite3`.
2. `search`: embed **only the query** the same way
   (`embed_texts([query], stored_model)`), cosine against all stored
   vectors, keep `score > 0`.

Strength: `why does measurement destroy superposition?` finds
`collapse / decoherence` passages with zero word overlap.
Weakness: fuzzy — weak on exact symbols, compresses 1200 chars into
768 floats so detail is lost, quality bounded by a small local model.

`bob-rag` never loads/unloads the model itself. Each call is a stateless
HTTP request to `ollama serve`; Ollama keeps the model resident per its
`keep_alive` (default ~5 min). First query after idle is slow (load),
subsequent ones reuse it. No `keep_alive` is sent by `rag.py`.

## 3. RRF — Reciprocal Rank Fusion

Rank-based merge of the two lists. `tools/rag.py:64,881`:

```python
RRF_K = 60
fused = reciprocal_rank_fusion([lexical, semantic])
```

Per passage `d`:

```text
RRF(d) = 1/(K + rank_bm25(d)) + 1/(K + rank_vector(d))
# absent from a list contributes 0
```

Example with `K = 60`: rank #1 → `1/61 ≈ 0.0164`,
rank #10 → `1/70 ≈ 0.0143`.

Why ranks, not scores? BM25 `4.3` and cosine `0.82` live on
incomparable scales. Ranks are comparable.

Effect:

- top in either list → high fused score;
- top in **both** → winner;
- large `K = 60` is flat/democratic: #1 only slightly beats #10,
  so consensus across lists matters more than one outlier.

That is why `--json` returns all three:

```json
{"bm25_rank": 2, "vector_rank": 1, "score": 0.032...}
```

If vectors are missing or Ollama is unreachable, fusion runs over
`[lexical]` only — pure BM25 plus a `note` such as
`store holds no vectors` or `vector search unavailable (...)`.

## Mental model

- BM25: precision on terms.
- Vectors: recall on intent.
- RRF: consensus without trusting either score scale.

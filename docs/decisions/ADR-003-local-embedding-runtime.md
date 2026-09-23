---
id: ADR-003
title: sentence-transformers now, ONNX/fastembed documented as the migration path
type: beyond-brief
---

# ADR-003: sentence-transformers now, ONNX/fastembed later

**The brief asked for** a Hugging Face model, with evidence of the
integration.

**We decided** to run the Hub checkpoint
(`paraphrase-multilingual-MiniLM-L12-v2`, pinned by commit SHA) locally
through `sentence-transformers`, rather than through the hosted Inference
API, with ONNX/fastembed documented as the migration path behind
`EmbeddingProvider`.

**Because** a reviewer must be able to run this offline with no token, and
the 0.80 threshold is calibrated against sentence-transformers' own scores.
This is **not** a departure from "a Hugging Face model" — the checkpoint
*is* one, pinned by Hub commit SHA (`EMBEDDING_MODEL_REVISION`); the choice
is about the runtime. Migration triggers and a mandatory score-equivalence
gate are written down so the choice stays revisable, not permanent.

## What it costs (measured)

- **API image size**: `docker images todo-ia-api` (Unit 16, reusing the
  image `todo-ia-api:latest` built and left cached by Unit 14) reports
  **10.4 GB disk usage / 4.4 GB content size**. Docker Desktop's newer
  `docker images` output splits these two columns; content size is the
  closer analogue to a traditional single "SIZE" value. This was not
  re-measured from a brand-new `--no-cache` build in this unit, so it may
  include reusable layer cache rather than only the final image's own
  layers — treat it as the current best measurement, not a from-clean
  baseline.
- **p95 embedding latency**: **UNMEASURED**. Neither Unit 8 nor Unit 14
  timed `embed()` p50/p95 against the running model; Unit 14 only measured
  cold-build wall time (torch install 71.6 s, `snapshot_download` 139.5 s,
  image export/unpack 157.7 s) and container-start-to-healthy (~10.6 s,
  see ADR-008), which are cold-start and boot numbers, not steady-state
  request latency. This stays an open item for whoever exercises
  `EMBEDDING_CACHE_SIZE` sizing or the p95 migration trigger below.
- **Casefold margins** (measured in Unit 9, `docs/evidence/calibration.md`,
  pair `case_and_spacing_variant`, "Comprar leche" vs "comprar LECHE"):
  cased cosine/score **0.3313**, cased margin **-0.4687**; casefolded score
  **1.0**, casefolded margin **+0.2000**. This corrects this design's own
  earlier estimate of "~0.98, unmeasured" for the cased score — the real
  number is far lower. The finding is the opposite of what was originally
  worried about: casefolding is not a risk to separation, it is what makes
  a case-variant pair recognizable as a duplicate at all. Without
  casefolding this pair scores 0.33, well below the 0.80 threshold, and
  would be reported as `distinct`; casefolded, it is an exact textual
  match (cosine 1.0).

## Migration triggers (any one is sufficient)

1. API image exceeds the agreed size ceiling for a target registry/deploy.
2. Cold start blocks a readiness-gated deployment (container start →
   `/health` ok).
3. RAM ceiling of a target host makes a torch process unviable.
4. p95 embedding latency becomes the dominant term in validate latency.

## The score-equivalence gate

ONNX export and (especially) int8 quantization shift cosine scores; near a
0.80 boundary a shift of ~1e-2 can flip a verdict. The migration PR MUST
re-run the ES/EN calibration fixture and diff per-pair scores against the
recorded sentence-transformers baseline, failing if any pair crosses the
threshold or drifts beyond an agreed tolerance.

## fastembed support (verified, task 16.3)

Ran `python -c "from fastembed import TextEmbedding; print([m['model'] for
m in TextEmbedding.list_supported_models()])"` in a throwaway virtualenv
(fastembed 0.8.1, Python 3.14.5). Result: **yes** —
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is in
fastembed's supported-model list. The documented migration path through
`fastembed` is viable directly; the manual `optimum` ONNX export is not
required as a fallback for this checkpoint. Score drift under fastembed's
own ONNX/quantization pipeline is still unverified (see the
score-equivalence gate above) — support in the library only means a
conversion path exists, not that scores are drift-free.

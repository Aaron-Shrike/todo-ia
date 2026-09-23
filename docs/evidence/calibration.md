# ES/EN calibration evidence (tasks.md 9.1/9.2)

Generated 2026-09-23 18:54 UTC by `make evidence`, scored against the real `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` model, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` -- the brief's Hugging Face integration evidence deliverable. `SIMILARITY_THRESHOLD` at run time: **0.8**.

## Duplicate pairs (hard-gated: score >= threshold)

| id | a | b | score | margin | note |
| --- | --- | --- | --- | --- | --- |
| `paraphrase_es_verb_added` | Comprar leche | Ir a comprar leche | 0.9417 | +0.1417 | Spanish paraphrase, verb added (spec example) |
| `case_and_spacing_variant` | Comprar leche | comprar LECHE | 1.0 | +0.2000 | Exact duplicate after casefold (spec example); also the pair used for the task 9.2 cased-vs-casefolded probe. |
| `cross_lingual_es_en` | Comprar leche | Buy milk | 0.975 | +0.1750 | Cross-lingual ES/EN paraphrase (spec example) |
| `paraphrase_en_minor_addition` | Call the dentist tomorrow | Call the dentist tomorrow morning | 0.9797 | +0.1797 | English paraphrase, minor addition |
| `paraphrase_es_reordered` | Necesito comprar pan y leche | Necesito comprar leche y pan | 0.9938 | +0.1938 | Spanish paraphrase, items reordered |
| `cross_lingual_en_es_reverse` | Schedule a dentist appointment | Programar una cita con el dentista | 0.923 | +0.1230 | Cross-lingual EN/ES paraphrase, reverse direction |

## Distinct pairs (hard-gated: score < threshold)

| id | a | b | score | margin | note |
| --- | --- | --- | --- | --- | --- |
| `different_grocery_item` | Comprar leche | Comprar pan | 0.317 | -0.4830 | Different grocery item (spec example) |
| `unrelated_tasks_es` | Llamar al dentista | Comprar leche | 0.2148 | -0.5852 | Unrelated tasks, both Spanish (spec example) |
| `unrelated_cross_lingual` | Buy milk | Schedule a dentist appointment | 0.1449 | -0.6551 | Unrelated tasks, cross-lingual |
| `unrelated_es_en` | Sacar la basura | Read a book | 0.242 | -0.5580 | Unrelated tasks, cross-lingual, reverse direction |
| `unrelated_same_domain_es` | Pagar la factura de luz | Renovar el pasaporte | 0.076 | -0.7240 | Unrelated errands, both bureaucratic but different tasks |

## Expected weakness pairs (reported, NEVER gated)

Negation pairs are a known, documented weakness of sentence embeddings on this checkpoint (design.md's "Accepted cost"): reported for visibility, never hard-gated.

| id | a | b | score | note |
| --- | --- | --- | --- | --- |
| `negation_es` | Me gusta el café | No me gusta el café | 0.6074 | Negation pair (Spanish, spec example) -- a documented, accepted weakness (design.md), not silently hidden. |
| `negation_en` | I like coffee | I don't like coffee | 0.6293 | Negation pair (English) |
| `negation_es_different_verb` | Necesito ir al banco | No necesito ir al banco | 0.6797 | Negation pair (Spanish, different verb from negation_es) |
| `accent_variant` | Llamar al dentista | Llamar al déntista | 0.4977 | Accent variant of the same Spanish word -- moved here from `duplicate` after the first real run (task 9.2): measured score 0.4977, far below the 0.8 threshold, contradicting the original assumption that this would score as a near-duplicate. Not a normalization bug (`comparison_ form`/`display_form` are NFC-based and never strip diacritics); the checkpoint itself treats an accent-shifted, non-dictionary word form as a substantial semantic change. A second, real, documented weakness alongside negation -- reported for visibility, never gated. |

## Cased vs. casefolded margin (task 9.2)

`paraphrase-multilingual-MiniLM-L12-v2` is a **cased** checkpoint; production always embeds the casefolded comparison form. This table measures how much separating margin casefolding costs versus the raw display form, same pair(s).

| id | cased cosine | cased score | cased margin | casefolded score | casefolded margin |
| --- | --- | --- | --- | --- | --- |
| `case_and_spacing_variant` | 0.3313 | 0.3313 | -0.4687 | 1.0 | +0.2000 |

Design.md's ADR-003 estimated the cased-variant cosine (`case_and_spacing_variant`, display forms) at **~0.98, unmeasured**; the row above is the first real measurement. If casefolding materially narrows the margin around the threshold, the decision rule applies: change `SIMILARITY_THRESHOLD`'s default (and `.env.example`, the spec, and an ADR-003 note) as a recorded spec change -- never silently, never by bending the fixture.


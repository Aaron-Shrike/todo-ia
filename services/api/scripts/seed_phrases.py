"""Seed the `phrases` table with generated Peruvian-themed phrases.

Standalone maintenance script — not part of the shipped application, not
subject to the `app/` import-linter boundaries (`design.md`'s hexagonal
contracts only govern the request-time modules). Run it inside the `api`
container, which already has the real embedding model baked in:

    docker compose exec api python scripts/seed_phrases.py --count 1000
    docker compose exec api python scripts/seed_phrases.py --count 20000 --batch-size 256

Or via the Makefile wrapper: `make seed N=1000`.

Why this bypasses SavePhrase entirely: the real save path (`application/
save_phrase.py`) recomputes an EXACT nearest-neighbour scan against the
whole table on every insert (`duplicate-confirmation` spec: "derived from
an EXACT nearest-neighbour scan ... inside the save transaction"). That is
O(n) per row, so seeding through the HTTP API or through `SavePhrase`
directly would cost O(n^2) total — at 20,000 rows that is hours, not
minutes. This script writes rows directly via SQL instead, with every
seeded row as `validation_status='unique'`, `similarity_score=NULL`,
`most_similar_phrase_id=NULL` (a paired-NULL row, satisfying the
`phrases_metadata_paired` CHECK — the same state as the very first phrase a
real user ever saves). This is a legitimate resting state, not a shortcut
that corrupts the data model: nothing about the API contract requires that
a `unique` row's neighbour was ever computed. Crucially, the app's own
write-path duplicate detection for any FUTURE save from the UI still runs
its normal exact scan against this seeded corpus — so seeding this way does
not weaken the feature it's meant to stress-test with realistic volume.

Text is deduplicated by comparison form (`normalized_text`, the same
casefolded/whitespace-collapsed key the app itself compares on) before any
row is built, and the partial unique index
(`phrases_unique_normalized_text_uidx`) is used as the `ON CONFLICT`
arbiter as a second line of defense (e.g. across repeated runs).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC
from typing import Any

from sqlalchemy import create_engine, text

from app.modules.phrases.domain.normalization import comparison_form, display_form
from app.platform.settings import Settings

try:
    from faker import Faker
except ImportError as exc:  # pragma: no cover — operator-facing, not test-covered
    raise SystemExit(
        "The 'faker' package is required. Install it with: pip install faker"
    ) from exc

# --- Peruvian vocabulary -------------------------------------------------
# Flavor content for generated seed data only — never user-facing app copy
# (which stays neutral Spanish per phrase-ui spec's copy table). Free to be
# vivid/colloquial here.

DISHES = [
    "ceviche", "tiradito", "causa limeña", "lomo saltado", "ají de gallina",
    "arroz con pollo", "papa a la huancaína", "rocoto relleno", "anticuchos",
    "chicharrón de pescado", "chicharrón de cerdo", "cuy chactado", "pachamanca",
    "seco de cordero", "carapulcra", "tacu tacu", "chupe de camarones",
    "sudado de pescado", "parihuela", "juane", "tacacho con cecina", "patasca",
    "olluquito con charqui", "escabeche de pollo", "adobo arequipeño", "chairo",
    "cau cau", "choros a la chalaca", "picante de mariscos", "arroz con mariscos",
    "tallarín saltado", "chifa de pollo", "butifarra", "salchipapa", "humita",
    "tamal verde", "mazamorra morada", "suspiro a la limeña", "picarones",
    "turrón de Doña Pepa", "alfajores", "king kong de Lambayeque",
]

PLACES = [
    "Machu Picchu", "Cusco", "el Valle Sagrado", "Ollantaytambo", "Miraflores",
    "Barranco", "San Isidro", "Surco", "La Molina", "el centro de Lima",
    "Arequipa", "el Cañón del Colca", "el Lago Titicaca", "Puno", "Chiclayo",
    "Trujillo", "Chan Chan", "Huaca Pucllana", "Kuélap", "Chachapoyas",
    "Huaraz", "la Cordillera Blanca", "Iquitos", "la selva de Tarapoto",
    "Huacachina", "Ica", "Paracas", "las Islas Ballestas", "Nazca", "Máncora",
    "Piura", "Ayacucho", "el Callao", "Pucallpa", "Tumbes", "el Mercado Central",
    "el malecón de Miraflores", "la Plaza de Armas del Cusco",
]

DRINKS = [
    "chicha morada", "pisco sour", "chilcano", "emoliente", "té piteado",
    "chicha de jora", "algarrobina", "agua de manzanilla con anís",
    "maracuyá sour", "Inca Kola",
]

# Split by grammatical fit so a template never pairs e.g. "Caminar por" with
# a dish, or "Cocinar" with a place — FOOD_ACTIONS take a dish/drink object,
# PLACE_ACTIONS take a place object.
FOOD_ACTIONS = [
    "Probar", "Comprar", "Preparar", "Cocinar", "Pedir", "Compartir",
    "Disfrutar de", "Comer", "Saborear", "Degustar", "Recomendar",
    "Buscar la receta de", "Aprender a preparar", "Llevar", "Reservar mesa para",
]
PLACE_ACTIONS = [
    "Visitar", "Recorrer", "Conocer", "Fotografiar", "Descubrir", "Explorar",
    "Caminar por", "Subir a", "Ver el amanecer en", "Ver el atardecer en",
    "Tomar fotos en",
]

TIME_HINTS = [
    "al amanecer", "antes del mediodía", "este fin de semana",
    "en la próxima feria gastronómica", "con la familia", "con amigos",
    "en el desayuno", "en el almuerzo", "para la cena",
    "en el próximo feriado largo", "durante las fiestas patrias", "en vacaciones",
]

# Standalone dichos/expresiones — inserted verbatim as their own phrases,
# not run through a template.
SAYINGS = [
    "Al toque nomás", "Habla causa, ¿todo bien?", "Estoy misio hasta fin de mes",
    "Qué tal palta la del vecino", "Ya pe, no seas serrano", "Esto está bacán",
    "Vamos a chapar el bus", "No seas cabro, invita otra chelita",
    "Qué buena esa jato", "Eso sí que es un cachito", "Estamos en la yapa",
    "Qué tal collera de amigos", "Me quedé plagado con la noticia",
    "Vamos a la chamba temprano", "Ese pata es un crack",
    "Qué rico está el caldo, causa", "Nos vemos al toque en la esquina",
    "Está soleado, vamos a la playa", "Ya estuvo, paremos aquí",
    "No hay levante como el peruano",
]

_TEMPLATE_WEIGHTS: list[tuple[str, int]] = [
    ("{food_action} {dish} en {place}", 5),
    ("{food_action} {dish}", 4),
    ("{place_action} {place}", 3),
    ("{place_action} {place} {time_hint}", 3),
    ("{food_action} {dish} {time_hint}", 3),
    ("{food_action} {dish} con {drink}", 2),
    ("{food_action} {drink} en {place}", 2),
    ("{name} recomienda el {dish} de {place}", 2),
    ("Llevar a {name} a comer {dish} en {place}", 2),
    ("SAYING", 2),  # standalone dicho, picked verbatim
]


def _render(template: str, rng: Faker, faker: Faker) -> str:
    if template == "SAYING":
        return rng.random_element(SAYINGS)
    return template.format(
        food_action=rng.random_element(FOOD_ACTIONS),
        place_action=rng.random_element(PLACE_ACTIONS),
        dish=rng.random_element(DISHES),
        place=rng.random_element(PLACES),
        drink=rng.random_element(DRINKS),
        time_hint=rng.random_element(TIME_HINTS),
        name=faker.first_name(),
    )


def generate_phrases(count: int, faker: Faker) -> list[str]:
    """Generates `count` DISTINCT display-form phrases (deduplicated by
    comparison form, the same key the app itself compares on)."""
    templates = [tpl for tpl, weight in _TEMPLATE_WEIGHTS for _ in range(weight)]
    seen: set[str] = set()
    phrases: list[str] = []
    max_attempts = count * 30
    attempts = 0
    while len(phrases) < count and attempts < max_attempts:
        attempts += 1
        template = faker.random_element(templates)
        candidate = _render(template, faker, faker)
        display = display_form(candidate)
        key = comparison_form(display)
        if not display or key in seen:
            continue
        seen.add(key)
        phrases.append(display)
    if len(phrases) < count:
        raise RuntimeError(
            f"Only generated {len(phrases)}/{count} unique phrases after "
            f"{attempts} attempts — widen the vocabulary in this script."
        )
    return phrases


def _serialize_vector(vector: Any) -> str:
    # `vector` is whatever `SentenceTransformer.encode` returns for one row of
    # a batch (an untyped numpy array — the library ships no stubs); iterating
    # it and coercing each component to `float` is the same pattern
    # `sentence_transformers.py`'s own adapter uses for a single embedding.
    return "[" + ",".join(repr(float(c)) for c in vector) + "]"


def seed(count: int, batch_size: int, faker_locale: str, rng_seed: int | None) -> None:
    faker = Faker(faker_locale)
    if rng_seed is not None:
        faker.seed_instance(rng_seed)

    # pydantic-settings reads DATABASE_URL (and everything else) from the
    # environment at runtime; same pattern/ignore as main.py's `Settings()`.
    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(settings.database_url)

    print(f"Generating {count} unique Peruvian phrases (locale={faker_locale})...")
    phrases = generate_phrases(count, faker)

    print("Loading embedding model (sentence-transformers)...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision
    )

    with engine.begin() as conn:
        before = conn.execute(text("SELECT count(*) FROM phrases")).scalar_one()

    start_time = time.monotonic()
    for start in range(0, len(phrases), batch_size):
        batch = phrases[start : start + batch_size]
        vectors = model.encode(
            batch, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        rows = []
        for display, vector in zip(batch, vectors, strict=True):
            normalized = comparison_form(display)
            moment = faker.date_time_between(
                start_date="-180d", end_date="now", tzinfo=UTC
            )
            rows.append(
                {
                    "t": display,
                    "n": normalized,
                    "e": _serialize_vector(vector),
                    "va": moment,
                    "ca": moment,
                }
            )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO phrases (text, normalized_text, embedding, similarity_score,"
                    " most_similar_phrase_id, validation_status, validated_at, created_at)"
                    " VALUES (:t, :n, CAST(:e AS vector), NULL, NULL, 'unique', :va, :ca)"
                    " ON CONFLICT (normalized_text) WHERE validation_status = 'unique' DO NOTHING"
                ),
                rows,
            )
        done = min(start + batch_size, len(phrases))
        elapsed = time.monotonic() - start_time
        rate = done / elapsed if elapsed > 0 else 0.0
        print(f"  {done}/{len(phrases)} embedded+inserted ({rate:.1f}/s)", end="\r")

    with engine.begin() as conn:
        after = conn.execute(text("SELECT count(*) FROM phrases")).scalar_one()

    skipped = len(phrases) - (after - before)
    print()
    print(
        f"Done in {time.monotonic() - start_time:.1f}s. phrases table: {before} -> {after} rows "
        f"(+{after - before}; {skipped} skipped as pre-existing duplicates)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--count", type=int, default=1000, help="Phrases to generate and insert.")
    parser.add_argument("--batch-size", type=int, default=256, help="Embed/insert batch size.")
    parser.add_argument("--locale", default="es_PE", help="Faker locale (falls back to es_MX).")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for a reproducible run.")
    args = parser.parse_args()

    if args.count <= 0:
        print("--count must be positive", file=sys.stderr)
        raise SystemExit(2)

    try:
        seed(args.count, args.batch_size, args.locale, args.seed)
    except AttributeError:
        # Faker has no 'es_PE' provider set in some versions — es_MX is the
        # closest maintained Latin American Spanish locale with full
        # first_name/date_time provider coverage.
        print(f"Locale '{args.locale}' unsupported by this Faker version, falling back to es_MX.")
        seed(args.count, args.batch_size, "es_MX", args.seed)


if __name__ == "__main__":
    main()

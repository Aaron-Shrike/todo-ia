"""Shared `PhraseRepository`/`UnitOfWork` contract suite (tasks.md 2.3/2d.3;
design.md: "so the fast fake cannot drift from the real one"). Not
`test_*.py` on purpose -- collected only through subclasses.

Split into mixins so a partial adapter registers only what it implements:
`NearestNeighbourContractSuite` (in-memory only, until Unit 5b gives pgvector
the write-path primitives), `MatchesContractSuite` (in-memory since Unit 2d,
pgvector since `tests/integration/test_find_matches.py`; also covers
`count_matches`, added retroactively -- see its docstring), and
`ListPageContractSuite` (`list_page`/`count_all`, added retroactively after
PR #42 introduced them with only a dedicated pgvector integration file and
an in-memory unit test, never proven to agree with each other the way every
other repository method is -- the same gap Unit 7b's own verify section
already flagged for `list_recent`, closed here for these three methods
instead). `RepositoryContractSuite` composes all three, unchanged for
in-memory (now 13 scenarios: 4 + 6 + 3).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.phrases.contracts import (
    Isolation,
    ListCursor,
    ListFilters,
    MatchCursor,
    NewPhrase,
    UnitOfWorkFactory,
    ValidationStatus,
)
from app.modules.similarity.contracts import Vector
from tests.contract_suite.vectors import PROBE
from tests.contract_suite.vectors import vector_at_distance as _vector_at_distance


def _new_phrase(
    text: str,
    embedding: Vector,
    *,
    status: ValidationStatus = ValidationStatus.UNIQUE,
    score: float | None = None,
    neighbour: int | None = None,
    normalized_text: str | None = None,
) -> NewPhrase:
    # `status`/`score`/`neighbour` (Unit 1, task 1.4): let filter tests seed
    # `duplicate_confirmed` rows (paired score+neighbour, migration 0001's
    # `phrases_metadata_paired`/`phrases_confirmed_has_neighbor` CHECKs) and
    # NULL-score rows without touching every other call site's 2-arg form.
    # `normalized_text` (optional, defaults to `text`): lets the text-filter
    # tests store a value that differs from the display `text` -- needed for
    # the case-folding regression case below, where `SavePhrase` would have
    # already folded the display text before writing `normalized_text`.
    return NewPhrase(
        text=text,
        normalized_text=text if normalized_text is None else normalized_text,
        embedding=embedding,
        similarity_score=score,
        most_similar_phrase_id=neighbour,
        validation_status=status,
        validated_at=datetime.now(UTC),
    )


def _seed(uow_factory: UnitOfWorkFactory, phrases: list[NewPhrase]) -> list[int]:
    ids: list[int] = []
    with uow_factory() as uow:
        for phrase in phrases:
            ids.append(uow.repo.add(phrase).id)
        uow.commit()
    return ids


class NearestNeighbourContractSuite:
    @pytest.fixture
    def uow_factory(self) -> UnitOfWorkFactory:
        raise NotImplementedError("subclasses must override the `uow_factory` fixture")

    def test_find_nearest_on_an_empty_store_returns_none(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        with uow_factory(isolation=Isolation.REPEATABLE_READ, read_only=True) as uow:
            assert uow.repo.find_nearest(PROBE) is None
            assert uow.repo.find_nearest_exact(PROBE) is None

    def test_find_nearest_returns_a_below_threshold_neighbour(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        _seed(uow_factory, [_new_phrase("far", _vector_at_distance(1.9))])
        with uow_factory(read_only=True) as uow:
            neighbor = uow.repo.find_nearest(PROBE)
            exact = uow.repo.find_nearest_exact(PROBE)
        assert neighbor is not None and exact is not None
        assert neighbor.text == exact.text == "far"
        # 1e-9 (in-memory float64-exact) was never exercised against a real
        # storage-backed adapter until pgvector registered here (Unit 5b);
        # design.md's own tolerance for pgvector's float32 column applies
        # ("Why 1e-5 and not 1e-6") -- still tight enough to catch a real bug.
        assert neighbor.distance == pytest.approx(1.9, abs=1e-5)

    def test_find_nearest_tie_breaks_on_lowest_id(self, uow_factory: UnitOfWorkFactory) -> None:
        ids = _seed(
            uow_factory,
            [
                _new_phrase("second", _vector_at_distance(0.4)),
                _new_phrase("first", _vector_at_distance(0.4)),
            ],
        )
        with uow_factory(read_only=True) as uow:
            neighbor = uow.repo.find_nearest(PROBE)
            exact = uow.repo.find_nearest_exact(PROBE)
        assert neighbor is not None and exact is not None
        assert neighbor.id == exact.id == min(ids)

    def test_add_inside_a_read_only_unit_of_work_raises_immediately(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # Fail-fast at the statement, matching a real Postgres `BEGIN READ
        # ONLY` transaction: the write must be rejected as soon as `add()`
        # is called, not only if the caller happens to call `commit()` with
        # pending writes -- the common read-only pattern never commits.
        with uow_factory(read_only=True) as uow:
            with pytest.raises(Exception):  # noqa: B017 -- adapter-specific error type
                uow.repo.add(_new_phrase("nope", PROBE))


class MatchesContractSuite:
    @pytest.fixture
    def uow_factory(self) -> UnitOfWorkFactory:
        raise NotImplementedError("subclasses must override the `uow_factory` fixture")

    def test_bit_identical_ties_split_cleanly_across_a_page_boundary(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Tie scores across a page boundary": 5 matches with
        # bit-identical embeddings (equal raw distance -> the SAME bucket),
        # ids 1..5, limit=2 -> pages [1,2], [3,4], [5]: none repeated, none
        # skipped, ordered purely by id inside the tied bucket.
        tied_vector = _vector_at_distance(0.10)
        ids = _seed(uow_factory, [_new_phrase(f"tied-{i}", tied_vector) for i in range(1, 6)])
        assert ids == sorted(ids)  # ids assigned in insertion order, as the assertion below assumes

        collected: list[int] = []
        cursor: MatchCursor | None = None
        with uow_factory(read_only=True) as uow:
            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=None)
            collected.extend(m.id for m in page.items)
            assert page.has_more is True
            cursor = page.next_cursor

            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=cursor)
            collected.extend(m.id for m in page.items)
            assert page.has_more is True
            cursor = page.next_cursor

            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=cursor)
            collected.extend(m.id for m in page.items)
            assert page.has_more is False
            assert page.next_cursor is None

        assert collected == ids  # [1,2],[3,4],[5] concatenated, none repeated or skipped

    def test_displayed_ties_are_ordered_by_raw_distance(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Displayed ties are ordered by raw distance": raw scores
        # 0.90001 (id "a") and 0.90004 (id "b") both round to the displayed
        # 0.9000, but "b" (the smaller raw distance, higher raw score) MUST
        # precede "a" -- the keyset orders on the UNROUNDED distance.
        ids = _seed(
            uow_factory,
            [
                _new_phrase("a", _vector_at_distance(1 - 0.90001)),
                _new_phrase("b", _vector_at_distance(1 - 0.90004)),
            ],
        )
        with uow_factory(read_only=True) as uow:
            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=10, cursor=None)
        assert [m.text for m in page.items] == ["b", "a"]
        assert [m.id for m in page.items] == sorted(ids, reverse=True)  # "b" inserted second

    def test_500_matches_page_through_completely_with_no_gaps_or_repeats(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Paging beyond the former approximate-index window":
        # 500 matches above threshold, page size 50 -> 10 pages, 500
        # distinct ids, none missing, none repeated.
        distances = [0.001 + i * 0.0013 for i in range(500)]  # spread, away from grid edges
        phrases = [_new_phrase(f"m{i}", _vector_at_distance(d)) for i, d in enumerate(distances)]
        ids = _seed(uow_factory, phrases)

        collected: list[int] = []
        cursor: MatchCursor | None = None
        pages = 0
        with uow_factory(read_only=True) as uow:
            while True:
                page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=50, cursor=cursor)
                pages += 1
                collected.extend(m.id for m in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert pages == 10
        assert len(collected) == 500
        assert len(set(collected)) == 500  # none repeated
        assert set(collected) == set(ids)  # none missing

    def test_perturbed_vector_paging_does_not_repeat_or_skip(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # design.md: "a perturbed-vector test pages a fixture to the end
        # with each page's query vector perturbed by one float32 ulp per
        # component"; fixture distances stay away from grid edges (D16) so
        # the test is deterministic. This models re-embedding the same
        # query text on a later page (cache eviction / another worker)
        # producing a vector that differs by a tiny numerical drift.
        distances = [0.011, 0.024, 0.037, 0.049, 0.062, 0.078, 0.091]
        phrases = [
            _new_phrase(f"p{i}", _vector_at_distance(d)) for i, d in enumerate(distances, start=1)
        ]
        ids = _seed(uow_factory, phrases)

        def _perturb(vector: Vector, eps: float = 1e-7) -> Vector:
            return [component + eps for component in vector]

        collected: list[int] = []
        cursor: MatchCursor | None = None
        first_page = True
        with uow_factory(read_only=True) as uow:
            while True:
                query_vector = PROBE if first_page else _perturb(PROBE)
                first_page = False
                page = uow.repo.find_matches(query_vector, max_distance=1.0, limit=3, cursor=cursor)
                collected.extend(m.id for m in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert collected == ids  # none repeated, none skipped, order preserved

    def test_count_matches_on_an_empty_store_is_zero(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory(read_only=True) as uow:
            assert uow.repo.count_matches(PROBE, max_distance=1.0) == 0

    def test_count_matches_equals_the_total_rows_find_matches_pages_through(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # `count_matches` and `find_matches` must agree on the SAME widened
        # bound (design.md) -- seed a mix of within-bound and out-of-bound
        # phrases, then prove the count equals the number of distinct ids a
        # full `find_matches` pagination actually yields, not a hardcoded
        # expectation either method could independently drift from.
        within_bound = [0.05, 0.2, 0.35, 0.5, 0.65]
        out_of_bound = [1.2, 1.5]
        phrases = [
            _new_phrase(f"in-{i}", _vector_at_distance(d)) for i, d in enumerate(within_bound)
        ]
        phrases += [
            _new_phrase(f"out-{i}", _vector_at_distance(d)) for i, d in enumerate(out_of_bound)
        ]
        _seed(uow_factory, phrases)

        with uow_factory(read_only=True) as uow:
            count = uow.repo.count_matches(PROBE, max_distance=0.7)

            collected: set[int] = set()
            cursor: MatchCursor | None = None
            while True:
                page = uow.repo.find_matches(PROBE, max_distance=0.7, limit=2, cursor=cursor)
                collected.update(m.id for m in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert count == len(within_bound)
        assert count == len(collected)


class ListPageContractSuite:
    """`list_page`/`count_all` (`GET /phrases`'s real pagination, added by
    PR #42) -- retroactively closes the same class of gap Unit 7b's verify
    section already flagged for `list_recent`: these methods previously had
    no shared, adapter-agnostic coverage proving the fake and the real
    adapter agree, only a dedicated pgvector integration file and an
    in-memory unit test that could silently diverge from each other."""

    @pytest.fixture
    def uow_factory(self) -> UnitOfWorkFactory:
        raise NotImplementedError("subclasses must override the `uow_factory` fixture")

    def test_list_page_on_an_empty_store_returns_no_items_and_zero_total(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        with uow_factory(read_only=True) as uow:
            page = uow.repo.list_page(limit=10, cursor=None)
            assert page.items == []
            assert page.total == 0
            assert page.has_more is False
            assert page.next_cursor is None
            assert uow.repo.count_all() == 0

    def test_count_all_matches_the_number_of_stored_phrases(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        ids = _seed(uow_factory, [_new_phrase(f"p{i}", PROBE) for i in range(7)])
        with uow_factory(read_only=True) as uow:
            assert uow.repo.count_all() == len(ids)
            assert uow.repo.list_page(limit=100, cursor=None).total == len(ids)

    def test_get_returns_the_matching_row(self, uow_factory: UnitOfWorkFactory) -> None:
        ids = _seed(uow_factory, [_new_phrase("p0", PROBE), _new_phrase("p1", PROBE)])
        with uow_factory(read_only=True) as uow:
            phrase = uow.repo.get(ids[1])
            assert phrase is not None
            assert phrase.id == ids[1]
            assert phrase.text == "p1"

    def test_get_with_an_unknown_id_returns_none(self, uow_factory: UnitOfWorkFactory) -> None:
        ids = _seed(uow_factory, [_new_phrase("p0", PROBE)])
        with uow_factory(read_only=True) as uow:
            assert uow.repo.get(max(ids) + 1) is None

    def test_list_page_pages_through_completely_with_no_gaps_or_repeats(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # Mirrors `test_500_matches_page_through_completely_with_no_gaps_or_repeats`'s
        # shape for the OTHER paginated read path (`list_page`, `(created_at,
        # id)` keyset instead of `(bucket, id)`): every seeded id reachable
        # exactly once, `has_more`/`next_cursor` internally consistent, and
        # `total` stable across every page regardless of pagination.
        #
        # Deliberately does NOT assert exact newest-first order: `NewPhrase`
        # has no `created_at` field for either adapter to accept, so a tight
        # seeding loop risks real timestamp collisions here -- asserting a
        # strict order would be flaky. That proof is owned by
        # `test_list_page_pgvector.py`'s own bespoke tests, which overwrite
        # `created_at` via a direct SQL `UPDATE` a second apart after
        # seeding, a DB-specific trick this adapter-agnostic suite can't
        # express.
        ids = _seed(uow_factory, [_new_phrase(f"m{i}", PROBE) for i in range(23)])

        collected: list[int] = []
        cursor: ListCursor | None = None
        pages = 0
        with uow_factory(read_only=True) as uow:
            while True:
                page = uow.repo.list_page(limit=5, cursor=cursor)
                pages += 1
                assert page.total == len(ids)
                collected.extend(p.id for p in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert pages == 5  # 23 rows, page size 5 -> 4 full pages + 1 of 3
        assert len(collected) == len(ids)
        assert len(set(collected)) == len(ids)  # none repeated
        assert set(collected) == set(ids)  # none missing

    # --- Filter cases (Unit 1, task 1.4; design.md's `ListFilters`) -------

    def test_list_page_filters_by_status_only(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow:
            unique_id = uow.repo.add(_new_phrase("agua", PROBE)).id
            confirmed_id = uow.repo.add(
                _new_phrase(
                    "agua otra vez",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.9,
                    neighbour=unique_id,
                )
            ).id
            uow.commit()

        confirmed_filters = ListFilters(status=ValidationStatus.DUPLICATE_CONFIRMED)
        with uow_factory(read_only=True) as uow:
            page = uow.repo.list_page(limit=10, cursor=None, filters=confirmed_filters)
            count = uow.repo.count_filtered(confirmed_filters)

        assert [p.id for p in page.items] == [confirmed_id]
        assert page.total == 1 == count
        assert unique_id not in [p.id for p in page.items]

    def test_list_page_filters_by_text_only(self, uow_factory: UnitOfWorkFactory) -> None:
        ids = _seed(
            uow_factory,
            [
                _new_phrase("comprar leche", PROBE),
                _new_phrase("comprar pan", PROBE),
            ],
        )
        with uow_factory(read_only=True) as uow:
            page = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="leche"))
        assert [p.id for p in page.items] == [ids[0]]

    def test_list_page_text_filter_case_folding_matches_the_already_folded_stored_value(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # Regression guard for design.md's "why LIKE, not ILIKE" rationale:
        # `SavePhrase` normalizes with Python `casefold()` BEFORE writing,
        # which folds "ß" to "ss" -- so `normalized_text` for an original
        # "Straße" is already "strasse" by the time any repository sees it.
        # `filters.text` arrives pre-folded the same way (D2). A plain,
        # case-sensitive `LIKE`/`in` on these ALREADY-folded values must
        # still find the row (first assertion); an un-folded raw "straße"
        # query must NOT re-fold and match it (second assertion) -- proving
        # neither adapter does its own casefolding, only the substring
        # comparison the design specifies.
        ids = _seed(
            uow_factory,
            [_new_phrase("Straße", PROBE, normalized_text="strasse")],
        )
        with uow_factory(read_only=True) as uow:
            folded = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="strasse"))
            unfolded = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="straße"))
        assert [p.id for p in folded.items] == ids
        assert unfolded.items == []

    def test_list_page_text_filter_matches_wildcard_characters_literally(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        ids = _seed(
            uow_factory,
            [
                _new_phrase("100% seguro", PROBE, normalized_text="100% seguro"),
                _new_phrase("100x seguro", PROBE, normalized_text="100x seguro"),
                _new_phrase("under_score", PROBE, normalized_text="under_score"),
                _new_phrase("underxscore", PROBE, normalized_text="underxscore"),
                _new_phrase(r"back\slash", PROBE, normalized_text=r"back\slash"),
                _new_phrase("backXslash", PROBE, normalized_text="backXslash"),
            ],
        )
        with uow_factory(read_only=True) as uow:
            percent = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="0%"))
            underscore = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="r_s"))
            backslash = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(text="\\s"))
        assert [p.id for p in percent.items] == [ids[0]]
        assert [p.id for p in underscore.items] == [ids[2]]
        assert [p.id for p in backslash.items] == [ids[4]]

    def test_list_page_filters_by_min_score_only(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow:
            null_score_id = uow.repo.add(_new_phrase("sin score", PROBE)).id
            below_id = uow.repo.add(
                _new_phrase(
                    "score bajo",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.4,
                    neighbour=null_score_id,
                )
            ).id
            boundary_id = uow.repo.add(
                _new_phrase(
                    "score limite",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.5,
                    neighbour=null_score_id,
                )
            ).id
            above_id = uow.repo.add(
                _new_phrase(
                    "score alto",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.9,
                    neighbour=null_score_id,
                )
            ).id
            uow.commit()

        with uow_factory(read_only=True) as uow:
            page = uow.repo.list_page(limit=10, cursor=None, filters=ListFilters(min_score=0.5))

        result_ids = {p.id for p in page.items}
        assert result_ids == {boundary_id, above_id}  # >= boundary; NULL and below excluded
        assert null_score_id not in result_ids
        assert below_id not in result_ids

    def test_list_page_filters_combine_with_and(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow:
            neighbour_id = uow.repo.add(_new_phrase("base", PROBE)).id
            match_id = uow.repo.add(
                _new_phrase(
                    "leche fresca",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.9,
                    neighbour=neighbour_id,
                    normalized_text="leche fresca",
                )
            ).id
            # Fails text only:
            uow.repo.add(
                _new_phrase(
                    "pan fresco",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.9,
                    neighbour=neighbour_id,
                    normalized_text="pan fresco",
                )
            )
            # Fails status only:
            uow.repo.add(_new_phrase("leche entera", PROBE, normalized_text="leche entera"))
            # Fails min_score only:
            uow.repo.add(
                _new_phrase(
                    "leche descremada",
                    PROBE,
                    status=ValidationStatus.DUPLICATE_CONFIRMED,
                    score=0.2,
                    neighbour=neighbour_id,
                    normalized_text="leche descremada",
                )
            )
            uow.commit()

        with uow_factory(read_only=True) as uow:
            filters = ListFilters(
                status=ValidationStatus.DUPLICATE_CONFIRMED, text="leche", min_score=0.5
            )
            page = uow.repo.list_page(limit=10, cursor=None, filters=filters)
            count = uow.repo.count_filtered(filters)

        assert [p.id for p in page.items] == [match_id]
        assert page.total == 1 == count

    def test_list_page_full_cursor_walk_under_a_filter(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # Mirrors `test_list_page_pages_through_completely_with_no_gaps_or_repeats`
        # for a FILTERED set: `total`/`count_filtered` stay pinned to the
        # filtered size on every page, not the whole store, while unrelated
        # rows outside the filter are never returned.
        with uow_factory() as uow:
            base_id = uow.repo.add(_new_phrase("base2", PROBE)).id
            matching_ids = [
                uow.repo.add(
                    _new_phrase(
                        f"n{i}",
                        PROBE,
                        status=ValidationStatus.DUPLICATE_CONFIRMED,
                        score=0.7,
                        neighbour=base_id,
                    )
                ).id
                for i in range(11)
            ]
            for i in range(4):  # noise the filter must exclude
                uow.repo.add(_new_phrase(f"unique-noise-{i}", PROBE))
            uow.commit()

        filters = ListFilters(status=ValidationStatus.DUPLICATE_CONFIRMED)
        collected: list[int] = []
        cursor: ListCursor | None = None
        pages = 0
        with uow_factory(read_only=True) as uow:
            while True:
                page = uow.repo.list_page(limit=4, cursor=cursor, filters=filters)
                pages += 1
                assert page.total == len(matching_ids) == uow.repo.count_filtered(filters)
                collected.extend(p.id for p in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert pages == 3  # 11 rows, page size 4 -> 4, 4, 3 -> 3 pages
        assert len(collected) == len(matching_ids)
        assert len(set(collected)) == len(matching_ids)
        assert set(collected) == set(matching_ids)
        assert base_id not in collected


class RepositoryContractSuite(
    NearestNeighbourContractSuite, MatchesContractSuite, ListPageContractSuite
):
    """Full suite: all three mixins' scenarios. In-memory registers here
    (Unit 2/2d, extended by the `ListPageContractSuite` retrofit); a partial
    adapter registers a single mixin directly instead (see this module's
    docstring)."""

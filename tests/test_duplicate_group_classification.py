from mcp4cm.api.services.duplicate_pipeline import build_duplicate_groups


def decision(left_id: str, right_id: str, techniques: list[str], *, is_duplicate: bool) -> dict:
    return {
        "leftId": left_id,
        "rightId": right_id,
        "isDuplicate": is_duplicate,
        "voteCount": len(techniques),
        "requiredVotes": 2,
        "techniques": techniques,
        "scores": {technique: 1.0 for technique in techniques},
    }


def group_confidence(decisions: list[dict]) -> str:
    groups, _lookup = build_duplicate_groups(decisions, {}, mandatory={"hash"}, min_votes=2)
    assert len(groups) == 1
    return str(groups[0]["confidence"])


def test_duplicate_group_confidence_is_strong_when_every_pair_satisfies_both_conditions() -> None:
    assert (
        group_confidence(
            [
                decision("a", "b", ["hash", "tfidf"], is_duplicate=True),
                decision("a", "c", ["hash", "tfidf"], is_duplicate=True),
                decision("b", "c", ["hash", "tfidf"], is_duplicate=True),
            ]
        )
        == "strong"
    )


def test_duplicate_group_confidence_is_high_when_all_pairs_have_enough_votes_but_one_misses_mandatory() -> None:
    assert (
        group_confidence(
            [
                decision("a", "b", ["hash", "tfidf"], is_duplicate=True),
                decision("b", "c", ["hash", "tfidf"], is_duplicate=True),
                decision("a", "c", ["tfidf", "graph_similarity"], is_duplicate=False),
            ]
        )
        == "high"
    )


def test_duplicate_group_confidence_is_moderate_when_all_pairs_have_mandatory_but_one_lacks_votes() -> None:
    assert (
        group_confidence(
            [
                decision("a", "b", ["hash", "tfidf"], is_duplicate=True),
                decision("b", "c", ["hash", "tfidf"], is_duplicate=True),
                decision("a", "c", ["hash"], is_duplicate=False),
            ]
        )
        == "moderate"
    )


def test_duplicate_group_confidence_is_low_when_an_internal_pair_satisfies_neither_condition() -> None:
    assert (
        group_confidence(
            [
                decision("a", "b", ["hash", "tfidf"], is_duplicate=True),
                decision("b", "c", ["hash", "tfidf"], is_duplicate=True),
            ]
        )
        == "low"
    )

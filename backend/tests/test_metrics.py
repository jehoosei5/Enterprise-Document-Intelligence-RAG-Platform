from app.evaluation.metrics import _mean_cosine_similarity, _precision_from_verdicts


def test_precision_from_verdicts_all_relevant():
    assert _precision_from_verdicts([True, True, True]) == 1.0


def test_precision_from_verdicts_none_relevant():
    assert _precision_from_verdicts([False, False, False]) == 0.0


def test_precision_from_verdicts_empty():
    assert _precision_from_verdicts([]) == 0.0


def test_precision_rewards_relevant_items_ranked_earlier():
    # Relevant item at position 1 -> precision@1 = 1.0, mean = 1.0
    early = _precision_from_verdicts([True, False, False])
    # Relevant item at position 3 -> precision@3 = 1/3, mean = 1/3
    late = _precision_from_verdicts([False, False, True])
    assert early > late
    assert early == 1.0
    assert late == 1 / 3


def test_precision_mixed_verdicts_known_value():
    # relevant at k=1 and k=3: precision@1=1/1=1.0, precision@3=2/3
    # mean over the 2 relevant positions = (1.0 + 2/3) / 2
    score = _precision_from_verdicts([True, False, True])
    assert abs(score - (1.0 + 2 / 3) / 2) < 1e-9


def test_mean_cosine_similarity_identical_vectors():
    assert abs(_mean_cosine_similarity([1.0, 0.0], [[1.0, 0.0]]) - 1.0) < 1e-9


def test_mean_cosine_similarity_orthogonal_vectors():
    assert abs(_mean_cosine_similarity([1.0, 0.0], [[0.0, 1.0]])) < 1e-9


def test_mean_cosine_similarity_opposite_vectors():
    assert abs(_mean_cosine_similarity([1.0, 0.0], [[-1.0, 0.0]]) - (-1.0)) < 1e-9


def test_mean_cosine_similarity_averages_multiple_vectors():
    score = _mean_cosine_similarity([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0]])
    assert abs(score - 0.5) < 1e-9


def test_mean_cosine_similarity_empty_vectors():
    assert _mean_cosine_similarity([1.0, 0.0], []) == 0.0

from src.fuzzy import generate_candidate_ids, levenshtein_distance, compute_similarity

def test_levenshtein_distance():
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("chokudai", "chokudai") == 0
    assert levenshtein_distance("chokudai", "chokudai1") == 1

def test_compute_similarity():
    assert compute_similarity("test", "test") == 1.0
    sim = compute_similarity("chokudai", "_chokudai")
    assert sim >= 0.85

def test_generate_candidate_ids():
    candidates = generate_candidate_ids("chokudai")
    names = {c.username for c in candidates}
    assert "chokudai" in names
    assert "_chokudai" in names or "chokudai_" in names
    assert "chokudai1" in names or "chokudai0" in names
    
    # Check exact match flag
    exacts = [c for c in candidates if c.username == "chokudai"]
    assert len(exacts) == 1
    assert exacts[0].is_exact is True
    assert exacts[0].similarity == 1.0

def test_strip_numbers():
    candidates = generate_candidate_ids("user123")
    names = {c.username for c in candidates}
    assert "user" in names


def test_generate_candidate_ids_exact_only():
    candidates = generate_candidate_ids("chokudai", exact_only=True)
    assert len(candidates) == 1
    assert candidates[0].username == "chokudai"
    assert candidates[0].original_id == "chokudai"
    assert candidates[0].is_exact is True
    assert candidates[0].match_type == "exact"
    assert candidates[0].similarity == 1.0


def test_generate_candidate_ids_max_candidates():
    candidates = generate_candidate_ids("chokudai", max_candidates=1)
    assert len(candidates) == 1
    assert candidates[0].is_exact is True

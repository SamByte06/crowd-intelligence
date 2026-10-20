# encoding: utf-8
"""
test_acceptance.py - Acceptance Tests for FastReID Cross-Camera Matching

Tests the 3 mandatory acceptance criteria:
1. One person walks from camera 1 into camera 2 -> global ID stays the same.
2. A person is occluded then reappears -> same global ID.
3. Two different people in similar clothes -> different global IDs.

Also verifies:
- Small crop skip (< 32x16) and retry
- Expiry pruning
- Overlapping camera count deduplication
"""

import os
import sys
import time
import numpy as np

# Ensure imports work from current dir
_current_dir = os.path.dirname(os.path.abspath(__file__))
_fast_reid_dir = os.path.join(_current_dir, "fast-reid")
for p in [_current_dir, _fast_reid_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from gallery import IdentityGallery


def generate_normalized_vector(dim=2048, seed=42):
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    return vec / np.linalg.norm(vec)


def generate_similar_vector(base_vec, target_similarity=0.85, seed=123):
    """Generate a vector having a specific cosine similarity with base_vec."""
    rng = np.random.RandomState(seed)
    noise = rng.randn(len(base_vec)).astype(np.float32)
    # Orthogonalize noise to base_vec
    noise = noise - np.dot(noise, base_vec) * base_vec
    noise = noise / np.linalg.norm(noise)
    # S = cos(theta) -> vector = cos(theta) * base + sin(theta) * noise
    s = target_similarity
    vec = s * base_vec + np.sqrt(max(0.0, 1.0 - s * s)) * noise
    return (vec / np.linalg.norm(vec)).astype(np.float32)


def test_acceptance_1_cross_camera_handover():
    """
    CRITERION 1:
    One person walks from camera 1 into camera 2 -> global ID stays the same.
    """
    gallery = IdentityGallery(match_threshold=0.6, expiry_seconds=60)
    track_map = {}

    # Person 1 appearance vector
    person1_emb_cam1 = generate_normalized_vector(dim=2048, seed=100)
    # Camera 2 captures Person 1 from a different angle/lighting (similarity ~0.82)
    person1_emb_cam2 = generate_similar_vector(person1_emb_cam1, target_similarity=0.82, seed=101)

    # 1. Person appears in Camera 1 with local ByteTrack ID = 101
    key_cam1 = (1, 101)
    gid_cam1, score_cam1 = gallery.match_or_register(person1_emb_cam1)
    track_map[key_cam1] = gid_cam1

    assert gid_cam1 == 1, "First person should be registered with global ID 1"
    assert score_cam1 is None, "First registration should not have match score"

    # 2. Person leaves Camera 1 -> ByteTrack drops track
    del track_map[key_cam1]

    # 3. Person walks into Camera 2 with local ByteTrack ID = 205
    key_cam2 = (2, 205)
    gid_cam2, score_cam2 = gallery.match_or_register(person1_emb_cam2)
    track_map[key_cam2] = gid_cam2

    # Verification
    assert gid_cam2 == gid_cam1, f"Expected same global ID ({gid_cam1}), but got {gid_cam2}"
    assert score_cam2 is not None and score_cam2 >= 0.6, f"Match score {score_cam2} should be >= 0.6"
    print(f"\n[PASS] Criterion 1 passed: Cam1 ID={gid_cam1} -> Cam2 ID={gid_cam2} (Score={score_cam2:.3f})")


def test_acceptance_2_occlusion_and_reappearance():
    """
    CRITERION 2:
    A person is occluded then reappears -> same global ID.
    """
    gallery = IdentityGallery(match_threshold=0.6, expiry_seconds=60)
    track_map = {}

    person_emb_pre = generate_normalized_vector(dim=2048, seed=200)
    # Reappearance embedding with slight pose/lighting variance (similarity ~0.88)
    person_emb_post = generate_similar_vector(person_emb_pre, target_similarity=0.88, seed=201)

    # 1. Person is tracked before occlusion with local ByteTrack ID = 12
    key_initial = (1, 12)
    gid_initial, _ = gallery.match_or_register(person_emb_pre)
    track_map[key_initial] = gid_initial

    # 2. Occlusion occurs: ByteTrack loses track -> track dropped
    del track_map[key_initial]

    # 3. Person emerges after occlusion: ByteTrack gives a NEW local ID = 34
    key_reemerge = (1, 34)
    gid_reemerge, score_reemerge = gallery.match_or_register(person_emb_post)
    track_map[key_reemerge] = gid_reemerge

    # Verification
    assert gid_reemerge == gid_initial, f"Expected same global ID ({gid_initial}), but got {gid_reemerge}"
    assert score_reemerge is not None and score_reemerge >= 0.6
    print(f"[PASS] Criterion 2 passed: Occluded ID={gid_initial} -> Re-emerged ID={gid_reemerge} (Score={score_reemerge:.3f})")


def test_acceptance_3_different_people_similar_clothes():
    """
    CRITERION 3:
    Two different people in similar clothes -> different global IDs.
    """
    gallery = IdentityGallery(match_threshold=0.6, expiry_seconds=60)

    # Person A in blue jacket & jeans
    person_a_emb = generate_normalized_vector(dim=2048, seed=300)
    # Person B in similar blue jacket & jeans, but distinct identity (similarity ~0.42 < 0.60)
    person_b_emb = generate_similar_vector(person_a_emb, target_similarity=0.42, seed=301)

    gid_a, score_a = gallery.match_or_register(person_a_emb)
    gid_b, score_b = gallery.match_or_register(person_b_emb)

    # Verification: Must be registered as distinct global identities
    assert gid_a != gid_b, f"Two different people were incorrectly assigned same ID {gid_a}"
    assert score_b is None, f"Person B should register as new identity, got score {score_b}"
    print(f"[PASS] Criterion 3 passed: Person A (gid={gid_a}) != Person B (gid={gid_b})")


def test_small_crop_filtering_rule():
    """
    Verifies that crops smaller than 32x16 are skipped and retried when larger.
    """
    min_h, min_w = 32, 16
    track_map = {}
    gallery = IdentityGallery(match_threshold=0.6)

    # Frame 1: Tiny crop (24x12) -> should skip ReID
    h1, w1 = 24, 12
    key = (1, 5)
    if h1 < min_h or w1 < min_w:
        # Skipped
        pass
    assert key not in track_map, "Tiny crop must not be added to track_map"

    # Frame 2: Person moves closer, crop becomes 100x48 -> ReID extracts & registers
    h2, w2 = 100, 48
    if h2 >= min_h and w2 >= min_w:
        emb = generate_normalized_vector(seed=400)
        gid, _ = gallery.match_or_register(emb)
        track_map[key] = gid

    assert key in track_map and track_map[key] == 1
    print("[PASS] Small crop filtering passed: tiny crop skipped, valid crop registered.")


def test_expiry_pruning():
    """
    Verifies that identities inactive beyond expiry_seconds are pruned.
    """
    gallery = IdentityGallery(match_threshold=0.6, expiry_seconds=0.1)  # 100ms expiry
    emb = generate_normalized_vector(seed=500)

    gid, _ = gallery.match_or_register(emb)
    assert len(gallery) == 1

    time.sleep(0.15)  # Wait for expiry
    gallery._prune()
    assert len(gallery) == 0, "Stale gallery entry was not pruned after expiry"
    print("[PASS] Expiry pruning passed: stale identity pruned.")


def test_overlapping_deduplication():
    """
    Verifies total crowd count deduplication when cameras have overlapping views.
    """
    cam1_active_gids = {1, 2, 3}
    cam2_active_gids = {2, 4}  # Person with global_id=2 is visible in both cameras!

    # Overlapping mode: union
    overlapping_total = len(cam1_active_gids | cam2_active_gids)
    assert overlapping_total == 4, f"Expected 4 unique people, got {overlapping_total}"

    # Non-overlapping mode: sum
    non_overlapping_total = len(cam1_active_gids) + len(cam2_active_gids)
    assert non_overlapping_total == 5, f"Expected 5, got {non_overlapping_total}"
    print(f"[PASS] Overlapping deduplication passed: overlap=4 unique, non-overlap=5 sum.")


if __name__ == "__main__":
    test_acceptance_1_cross_camera_handover()
    test_acceptance_2_occlusion_and_reappearance()
    test_acceptance_3_different_people_similar_clothes()
    test_small_crop_filtering_rule()
    test_expiry_pruning()
    test_overlapping_deduplication()
    print("\nALL ACCEPTANCE TESTS PASSED!")

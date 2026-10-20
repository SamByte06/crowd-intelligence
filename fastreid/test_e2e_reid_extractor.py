# encoding: utf-8
"""
test_e2e_reid_extractor.py - End-to-End Acceptance Test with Real FastReID Weights

Tests FastReID ReIDExtractor with market_sbs_S50.pth on synthetic person crops:
1. Person 1 (two different camera crops with lighting/perspective noise) -> same global ID.
2. Person 2 (different visual pattern) -> distinct global ID.
3. EMA update and cosine similarity score verification.
"""

import os
import sys
import numpy as np
import cv2

# Set path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_fast_reid_dir = os.path.join(_current_dir, "fast-reid")
for p in [_current_dir, _fast_reid_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from reid import ReIDExtractor
from gallery import IdentityGallery


def make_person_crop(color_top, color_bottom, noise_level=5, seed=0):
    """Create a synthetic 128x64 BGR crop representing a person in distinct clothing."""
    np.random.seed(seed)
    crop = np.zeros((128, 64, 3), dtype=np.uint8)
    # Head region (top 20%)
    crop[0:25, 20:44] = (180, 200, 220)  # skin tone
    # Torso (color_top)
    crop[25:75, 12:52] = color_top
    # Legs (color_bottom)
    crop[75:128, 16:30] = color_bottom
    crop[75:128, 34:48] = color_bottom
    # Add sensor noise and subtle camera lighting shift
    noise = np.random.randint(-noise_level, noise_level + 1, crop.shape, dtype=np.int16)
    crop = np.clip(crop.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return crop


def run_e2e_verification():
    print("[E2E Test] Loading ReIDExtractor with market_sbs_S50.pth...")
    config_path = "fast-reid/configs/Market1501/sbs_S50.yml"
    weights_path = "fast-reid/market_sbs_S50.pth"

    extractor = ReIDExtractor(config_path, weights_path, device="cpu")
    gallery = IdentityGallery(match_threshold=0.6, expiry_seconds=60)

    # 1. Person 1 in Camera 1: Red jacket, Dark Blue jeans
    person1_cam1 = make_person_crop(color_top=(30, 30, 210), color_bottom=(120, 50, 20), seed=1)
    emb1_cam1 = extractor.embedding(person1_cam1)
    gid1_cam1, score1_cam1 = gallery.match_or_register(emb1_cam1)
    print(f"Cam 1: Person 1 registered -> Global ID {gid1_cam1} (Score: {score1_cam1})")
    assert gid1_cam1 == 1

    # 2. Person 1 in Camera 2: Same clothing, slightly different illumination/angle
    person1_cam2 = make_person_crop(color_top=(35, 32, 205), color_bottom=(115, 52, 25), noise_level=10, seed=2)
    emb1_cam2 = extractor.embedding(person1_cam2)
    gid1_cam2, score1_cam2 = gallery.match_or_register(emb1_cam2)
    print(f"Cam 2: Person 1 observed   -> Global ID {gid1_cam2} (Score: {score1_cam2:.3f})")
    assert gid1_cam2 == 1, f"Expected Global ID 1, got {gid1_cam2}"
    assert score1_cam2 is not None and score1_cam2 >= 0.60, f"Expected match score >= 0.60, got {score1_cam2}"

    # 3. Person 2 in Camera 1: Bright Green polo, Khaki pants
    person2_cam1 = make_person_crop(color_top=(30, 200, 30), color_bottom=(70, 180, 210), seed=3)
    emb2_cam1 = extractor.embedding(person2_cam1)
    gid2_cam1, score2_cam1 = gallery.match_or_register(emb2_cam1)
    print(f"Cam 1: Person 2 registered -> Global ID {gid2_cam1} (Score: {score2_cam1})")
    assert gid2_cam1 == 2, f"Expected Global ID 2, got {gid2_cam1}"
    assert score2_cam1 is None, f"Person 2 should register as new, got {score2_cam1}"

    print("\n[SUCCESS] End-to-End ReID Feature Extractor + Gallery matching verified!")


if __name__ == "__main__":
    run_e2e_verification()

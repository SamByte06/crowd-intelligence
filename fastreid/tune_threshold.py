# encoding: utf-8
"""
tune_threshold.py - Threshold Calibration Utility for FastReID Cross-Camera Matching

Collects cosine similarity scores for:
1. Same person across camera 1 and camera 2.
2. Same person after occlusion / re-entry.
3. Two different people.

Calculates the optimal decision threshold in the observed gap and prints
a diagnostic report.
"""

import os
import sys
import argparse
from typing import List, Tuple
import numpy as np
import cv2

# Ensure fast-reid path is accessible
_current_dir = os.path.dirname(os.path.abspath(__file__))
_fast_reid_dir = os.path.join(_current_dir, "fast-reid")
for p in [_current_dir, _fast_reid_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from reid import ReIDExtractor


def compute_pair_similarity(extractor: ReIDExtractor, img1_path: str, img2_path: str) -> float:
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None:
        raise FileNotFoundError(f"Could not load image: {img1_path}")
    if img2 is None:
        raise FileNotFoundError(f"Could not load image: {img2_path}")

    emb1 = extractor.embedding(img1)
    emb2 = extractor.embedding(img2)
    return float(np.dot(emb1, emb2))


def analyze_thresholds(
    same_scores: List[float],
    diff_scores: List[float],
    default_threshold: float = 0.6
):
    """Analyze score distributions and suggest the optimal operating threshold."""
    print("=" * 65)
    print("       FASTREID THRESHOLD CALIBRATION REPORT")
    print("=" * 65)

    if same_scores:
        same_min = min(same_scores)
        same_mean = np.mean(same_scores)
        same_max = max(same_scores)
        print(f"Same-Person Pairs     (N={len(same_scores)}):")
        print(f"  Min: {same_min:.4f} | Mean: {same_mean:.4f} | Max: {same_max:.4f}")
    else:
        same_min = 0.70
        print("Same-Person Pairs: None provided (using reference ~0.70 - 0.95)")

    if diff_scores:
        diff_min = min(diff_scores)
        diff_mean = np.mean(diff_scores)
        diff_max = max(diff_scores)
        print(f"Different-Person Pairs (N={len(diff_scores)}):")
        print(f"  Min: {diff_min:.4f} | Mean: {diff_mean:.4f} | Max: {diff_max:.4f}")
    else:
        diff_max = 0.50
        print("Different-Person Pairs: None provided (using reference < 0.50)")

    print("-" * 65)

    if same_scores and diff_scores:
        gap = same_min - diff_max
        if gap > 0:
            recommended = round((same_min + diff_max) / 2.0, 3)
            print(f"Clean separation gap observed: [{diff_max:.4f}, {same_min:.4f}] (Width: {gap:.4f})")
            print(f"RECOMMENDED THRESHOLD: {recommended}")
        else:
            # Overlapping distributions
            recommended = round(np.mean([same_mean, diff_mean]), 3)
            print(f"[WARNING] Scores overlap by {abs(gap):.4f}. Consider collecting clearer footage or fine-tuning.")
            print(f"COMPROMISE THRESHOLD: {recommended}")
    else:
        print(f"RECOMMENDED STARTING THRESHOLD: {default_threshold}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate ReID similarity threshold on your footage.")
    parser.add_argument("--config", default="fast-reid/configs/Market1501/sbs_S50.yml", help="Path to config YAML")
    parser.add_argument("--weights", default="fast-reid/market_sbs_S50.pth", help="Path to weights file")
    parser.add_argument("--device", default="cpu", help="Device (cuda or cpu)")
    args = parser.parse_args()

    extractor = ReIDExtractor(args.config, args.weights, device=args.device)
    print("Extractor initialized. Ready for pairwise evaluation.")

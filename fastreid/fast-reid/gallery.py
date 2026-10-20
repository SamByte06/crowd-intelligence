# encoding: utf-8
"""
gallery.py - Shared Cross-Camera Identity Gallery for FastReID

Maintains persistent global identities across multiple camera streams.
Matches incoming ReID feature embeddings using cosine similarity against
multi-embedding centroids with spatial mutual exclusion and strict
cross-camera threshold enforcement.
"""

import time
from typing import Optional, Set, Tuple, List
import numpy as np


class IdentityGallery:
    """
    Cross-camera identity gallery for appearance-based person re-identification.

    Uses anchor-stabilized centroids with multi-sample confirmation for robust
    identity assignment. Supports camera-level mutual exclusion and enforces
    a higher similarity threshold for cross-camera matches.

    Key stability features:
    - Multi-sample confirmation: new identities only registered after N good samples
    - Anchor-weighted centroids: first clean embedding dominates to prevent drift
    - Anti-poisoning: only highly confident matches update the embedding bank
    - Ambiguity handling: ties resolved by deferring (not by creating duplicates)
    """

    def __init__(self, match_threshold: float = 0.75, expiry_seconds: float = 300.0,
                 max_embeddings: int = 10, cross_camera_boost: float = 0.02,
                 min_score_gap: float = 0.03, confirm_samples: int = 2, **kwargs):
        self.match_threshold = match_threshold
        self.cross_camera_boost = cross_camera_boost
        self.min_score_gap = min_score_gap
        self.expiry_seconds = expiry_seconds  # 5 minutes reservation (300s)
        self.max_embeddings = max_embeddings
        self.confirm_samples = confirm_samples
        self.entries = {}
        self.next_id = 1

        # Pending tracks collecting samples before gallery registration
        # key: pending_id -> {"samples": [emb, ...], "source_camera": int, "created": float}
        self._pending = {}
        self._next_pending_id = -1  # negative IDs for pending (never collide with real)

    def _centroid(self, entry: dict) -> np.ndarray:
        """Compute anchor-weighted centroid for stable matching."""
        anchor = entry.get("anchor")
        embeddings = entry.get("embeddings", [])
        if anchor is not None and len(embeddings) > 0:
            mean_emb = np.mean(embeddings, axis=0)
            combined = 0.6 * anchor + 0.4 * mean_emb
        elif anchor is not None:
            combined = np.array(anchor, dtype=np.float32).copy()
        elif len(embeddings) > 0:
            combined = np.mean(embeddings, axis=0)
        else:
            return np.zeros(2048, dtype=np.float32)

        norm = np.linalg.norm(combined)
        if norm > 1e-6:
            combined = combined / norm
        return combined

    def _normalize(self, embedding: np.ndarray) -> np.ndarray:
        """Ensure embedding is 1D float32 and L2-normalized."""
        embedding = np.asarray(embedding, dtype=np.float32).flatten()
        norm = np.linalg.norm(embedding)
        if norm > 1e-6:
            embedding = embedding / norm
        return embedding

    def match_only(self, embedding: np.ndarray, exclude_ids: Optional[Set[int]] = None,
                   source_camera: Optional[int] = None) -> Tuple[Optional[int], Optional[float]]:
        """
        Match against gallery WITHOUT registering or modifying anything.
        Used for re-verification of active tracks.
        """
        self._prune()
        embedding = self._normalize(embedding)
        exclude_set = exclude_ids or set()

        best_id, best_score = None, -1.0
        for gid, e in list(self.entries.items()):
            if gid in exclude_set:
                continue
            centroid = self._centroid(e)
            score = float(np.dot(embedding, centroid))
            if score > best_score:
                best_score = score
                best_id = gid

        threshold = self.match_threshold
        if best_id is not None and source_camera is not None:
            e = self.entries.get(best_id)
            if e and e.get("source_camera") is not None and source_camera != e["source_camera"]:
                threshold += self.cross_camera_boost

        if best_id is not None and best_score >= threshold:
            return best_id, best_score
        return None, None

    def match_or_register(
        self,
        embedding: np.ndarray,
        exclude_ids: Optional[Set[int]] = None,
        allow_register: bool = True,
        source_camera: Optional[int] = None
    ) -> Tuple[Optional[int], Optional[float]]:
        """
        Match embedding against gallery. If no match and allow_register,
        return a pending ID (negative) that will be confirmed after collecting
        enough samples via add_pending_sample().
        """
        self._prune()
        embedding = self._normalize(embedding)
        exclude_set = exclude_ids or set()

        matches = []
        for gid, e in list(self.entries.items()):
            if gid in exclude_set:
                continue

            centroid = self._centroid(e)
            score = float(np.dot(embedding, centroid))

            threshold = self.match_threshold
            if source_camera is not None and e.get("source_camera") is not None:
                if source_camera != e["source_camera"]:
                    threshold += self.cross_camera_boost

            if score >= threshold:
                matches.append((gid, score))

        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            best_id, best_score = matches[0]

            # Ambiguity: if two entries score nearly the same, pick best but don't
            # create a new identity (that was causing ID inflation)
            # Just return the best match — spatial continuity in app.py prevents swaps

            # Update embedding bank conservatively
            if best_score >= 0.88:
                self.entries[best_id]["embeddings"].append(embedding)
                if len(self.entries[best_id]["embeddings"]) > self.max_embeddings:
                    self.entries[best_id]["embeddings"] = self.entries[best_id]["embeddings"][-self.max_embeddings:]

            self.entries[best_id]["last_seen"] = time.time()
            return best_id, best_score

        if not allow_register:
            return None, None

        # Start pending confirmation instead of instant registration
        pending_id = self._next_pending_id
        self._next_pending_id -= 1
        self._pending[pending_id] = {
            "samples": [embedding.copy()],
            "source_camera": source_camera,
            "created": time.time()
        }
        return pending_id, None

    def add_pending_sample(self, pending_id: int, embedding: np.ndarray,
                           exclude_ids: Optional[Set[int]] = None,
                           source_camera: Optional[int] = None) -> Tuple[Optional[int], Optional[float]]:
        """
        Add another sample to a pending track. Once enough samples are collected,
        confirm registration using the averaged embedding.

        Returns:
          - (confirmed_global_id, None) if just confirmed as new identity
          - (matched_global_id, score) if confirmed samples actually match an existing identity
          - (pending_id, None) if still collecting samples
          - (None, None) if pending_id not found
        """
        if pending_id not in self._pending:
            return None, None

        embedding = self._normalize(embedding)
        self._pending[pending_id]["samples"].append(embedding.copy())

        # Check if this sample matches any existing reserved ID with high cosine similarity
        exclude_set = exclude_ids or set()
        instant_matches = []
        for gid, e in list(self.entries.items()):
            if gid in exclude_set:
                continue
            centroid = self._centroid(e)
            score = float(np.dot(embedding, centroid))
            threshold = self.match_threshold
            if source_camera is not None and e.get("source_camera") is not None:
                if source_camera != e["source_camera"]:
                    threshold += self.cross_camera_boost
            if score >= threshold:
                instant_matches.append((gid, score))

        if instant_matches:
            instant_matches.sort(key=lambda x: x[1], reverse=True)
            best_id, best_score = instant_matches[0]
            self._pending.pop(pending_id, None)
            if best_score >= 0.85:
                self.entries[best_id]["embeddings"].append(embedding)
                if len(self.entries[best_id]["embeddings"]) > self.max_embeddings:
                    self.entries[best_id]["embeddings"] = self.entries[best_id]["embeddings"][-self.max_embeddings:]
            self.entries[best_id]["last_seen"] = time.time()
            return best_id, best_score

        if len(self._pending[pending_id]["samples"]) < self.confirm_samples:
            return pending_id, None

        # Enough samples collected without matching existing — compute averaged embedding
        samples = self._pending.pop(pending_id)["samples"]
        avg_emb = np.mean(samples, axis=0)
        norm = np.linalg.norm(avg_emb)
        if norm > 1e-6:
            avg_emb = avg_emb / norm

        # Try matching the averaged embedding (much more reliable than single-frame)
        matches = []
        for gid, e in list(self.entries.items()):
            if gid in exclude_set:
                continue
            centroid = self._centroid(e)
            score = float(np.dot(avg_emb, centroid))
            threshold = self.match_threshold
            if source_camera is not None and e.get("source_camera") is not None:
                if source_camera != e["source_camera"]:
                    threshold += self.cross_camera_boost
            if score >= threshold:
                matches.append((gid, score))

        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            best_id, best_score = matches[0]
            if best_score >= 0.88:
                self.entries[best_id]["embeddings"].append(avg_emb)
                if len(self.entries[best_id]["embeddings"]) > self.max_embeddings:
                    self.entries[best_id]["embeddings"] = self.entries[best_id]["embeddings"][-self.max_embeddings:]
            self.entries[best_id]["last_seen"] = time.time()
            return best_id, best_score

        # Register as genuinely new identity
        gid = self.next_id
        self.next_id += 1
        self.entries[gid] = {
            "anchor": avg_emb.copy(),
            "embeddings": list(samples),
            "last_seen": time.time(),
            "source_camera": source_camera
        }
        return gid, None

    def is_pending(self, gid: int) -> bool:
        """Check if an ID is still in pending confirmation."""
        return gid < 0 and gid in self._pending

    def cancel_pending(self, pending_id: int):
        """Cancel a pending registration (e.g. track dropped before confirmation)."""
        self._pending.pop(pending_id, None)

    def update_last_seen(self, gid: int):
        """Update last_seen timestamp when an identity is actively tracked."""
        if gid in self.entries:
            self.entries[gid]["last_seen"] = time.time()

    def _prune(self):
        """Remove gallery entries that have exceeded expiry_seconds since last_seen."""
        if self.expiry_seconds is None or self.expiry_seconds <= 0:
            return
        now = time.time()
        stale = [g for g, e in self.entries.items() if (now - e["last_seen"]) > self.expiry_seconds]
        for g in stale:
            del self.entries[g]
        # Also clean stale pending entries (> 10 seconds old)
        stale_pending = [p for p, d in self._pending.items() if (now - d["created"]) > 10.0]
        for p in stale_pending:
            del self._pending[p]

    def get_active_ids(self):
        """Return list of active global identity IDs."""
        self._prune()
        return list(self.entries.keys())

    def __len__(self):
        self._prune()
        return len(self.entries)

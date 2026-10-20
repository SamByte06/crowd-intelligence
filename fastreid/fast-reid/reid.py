# encoding: utf-8
"""
reid.py - FastReID Embedding Extractor for Cross-Camera Re-Identification

Loads a FastReID model checkpoint once at startup and extracts L2-normalized
deep feature vectors from person bounding-box crops.
"""

import sys
import os
import torch
import cv2
import numpy as np
from PIL import Image

# Ensure the fast-reid package directory is on sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# Support both fastreid and fast_reid import conventions
try:
    import fastreid
    import fastreid.config
    import fastreid.modeling
    import fastreid.data.transforms
    import fastreid.utils.checkpoint
    sys.modules['fast_reid'] = fastreid
    sys.modules['fast_reid.config'] = fastreid.config
    sys.modules['fast_reid.modeling'] = fastreid.modeling
    sys.modules['fast_reid.data'] = fastreid.data
    sys.modules['fast_reid.data.transforms'] = fastreid.data.transforms
    sys.modules['fast_reid.utils'] = fastreid.utils
    sys.modules['fast_reid.utils.checkpoint'] = fastreid.utils.checkpoint
    from fastreid.config import get_cfg
    from fastreid.modeling import build_model
    from fastreid.data.transforms import build_transforms
    from fastreid.utils.checkpoint import Checkpointer
except ImportError:
    from fast_reid.config import get_cfg
    from fast_reid.modeling import build_model
    from fast_reid.data.transforms import build_transforms
    from fast_reid.utils.checkpoint import Checkpointer


class ReIDExtractor:
    """
    Appearance-based feature extractor wrapping a trained FastReID backbone & head.
    
    Attributes:
        model: Evaluated PyTorch ReID model.
        transforms: Preprocessing transform pipeline (resize, tensor conversion).
        device: Execution device (e.g., 'cuda' or 'cpu').
    """

    def __init__(self, config_path: str, weights_path: str, device: str = "cuda"):
        # Graceful fallback if CUDA is requested on a CPU-only environment
        if device == "cuda" and not torch.cuda.is_available():
            print("[INFO] CUDA not available on this system. Falling back to CPU for ReIDExtractor.")
            self.device = "cpu"
        else:
            self.device = device

        cfg = get_cfg()
        cfg.merge_from_file(config_path)
        cfg.MODEL.BACKBONE.PRETRAIN = False
        cfg.MODEL.DEVICE = self.device

        self.model = build_model(cfg)
        Checkpointer(self.model).load(weights_path)
        self.model.to(self.device).eval()
        self.transforms = build_transforms(cfg, is_train=False)

    @torch.no_grad()
    def embedding(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Extract an L2-normalized ReID embedding vector for a given image crop.

        Args:
            crop_bgr (np.ndarray): HxWxC BGR image crop of a detected person.

        Returns:
            np.ndarray: 1D L2-normalized float32 numpy array.
        """
        if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.shape[0] == 0 or crop_bgr.shape[1] == 0:
            raise ValueError("Invalid empty image crop provided to ReIDExtractor.")

        # Convert BGR (OpenCV) to RGB (PIL)
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img_tensor = self.transforms(img).unsqueeze(0).to(self.device)
        feat = self.model(img_tensor)
        feat = torch.nn.functional.normalize(feat, dim=1)
        return feat.cpu().numpy()[0]

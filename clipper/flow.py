"""Optical-flow tools: flow-based retiming (smooth slow motion) and vector motion blur.

Flow is computed with OpenCV's DIS optical flow at reduced resolution (fast on CPU) and
upsampled. Intermediate frames use the Super-SloMo linear flow approximation:

    F_t->0 = -(1-t) t F_0->1 + t^2 F_1->0
    F_t->1 = (1-t)^2 F_0->1 - t (1-t) F_1->0

then both neighbours are backward-warped to time t and blended, weighted by temporal
distance and by a forward/backward consistency check (cheap occlusion handling).
"""
import cv2
import numpy as np


class Flow:
    def __init__(self, scale=0.5, preset="medium"):
        self.scale = scale
        p = {"ultrafast": cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST, "fast": cv2.DISOPTICAL_FLOW_PRESET_FAST,
             "medium": cv2.DISOPTICAL_FLOW_PRESET_MEDIUM}[preset]
        self.dis = cv2.DISOpticalFlow_create(p)
        self.cache = {}
        self._grid = None

    def _small_gray(self, f):
        h, w = f.shape[:2]
        s = cv2.resize(f, (int(w * self.scale), int(h * self.scale)), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)

    def pair(self, a, b, key=None):
        """Forward and backward flow (full resolution, in pixels)."""
        if key is not None and key in self.cache:
            return self.cache[key]
        ga, gb = self._small_gray(a), self._small_gray(b)
        fab = cv2.GaussianBlur(self.dis.calc(ga, gb, None), (0, 0), 1.5)
        fba = cv2.GaussianBlur(self.dis.calc(gb, ga, None), (0, 0), 1.5)
        h, w = a.shape[:2]
        up = lambda f: cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR) / self.scale
        res = (up(fab), up(fba))
        if key is not None:
            if len(self.cache) > 6:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = res
        return res

    def grid(self, h, w):
        if self._grid is None or self._grid[0].shape != (h, w):
            xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            self._grid = (xs, ys)
        return self._grid

    def warp(self, img, flow):
        xs, ys = self.grid(*img.shape[:2])
        flow = flow.astype(np.float32, copy=False)
        return cv2.remap(img, xs + flow[..., 0], ys + flow[..., 1], cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REPLICATE)

    def interpolate(self, a, b, t, key=None):
        """In-between frame at fraction t in (0, 1)."""
        fab, fba = self.pair(a, b, key)
        ft0 = -(1 - t) * t * fab + t * t * fba
        ft1 = (1 - t) * (1 - t) * fab - t * (1 - t) * fba
        wa = self.warp(a, ft0).astype(np.float32)
        wb = self.warp(b, ft1).astype(np.float32)
        # occlusion: where the two warped frames disagree the flow is unreliable, so instead of
        # blending (ghosts) take the temporally nearer warped frame
        diff = np.abs(wa - wb).mean(axis=2)
        occ = np.clip((cv2.GaussianBlur(diff, (0, 0), 3) - 18) / 30, 0, 1)[..., None]
        near = wa if t < 0.5 else wb
        out = ((1 - t) * wa + t * wb) * (1 - occ) + near * occ
        return np.clip(out, 0, 255).astype(np.uint8)

    def vector_blur(self, img, flow, amount=0.5, samples=7):
        """Vector motion blur: average samples along each pixel's motion vector.
        amount = shutter fraction of the motion (0.5 = 180 degree shutter)."""
        mag = np.abs(flow).max()
        if mag * amount < 1.0:
            return img
        acc = np.zeros(img.shape, np.float32)
        for i in range(samples):
            k = (i / (samples - 1) - 0.5) * amount
            acc += self.warp(img, flow * k)
        return (acc / samples).astype(np.uint8)

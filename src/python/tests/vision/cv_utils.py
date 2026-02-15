"""Shared computer vision utility functions for vision tests."""

import cv2
import numpy as np


class FrameCapture:
    """Wrapper around cv2.VideoCapture that discards warmup frames.

    Parameters
    ----------
    device : str
        Path to the V4L2 video device (e.g. "/dev/video0").
    warmup : int
        Number of frames to read and discard before the capture is
        considered ready. This allows auto-exposure and auto-white-balance
        to settle.
    """

    def __init__(self, device: str, warmup: int = 10):
        self._cap = cv2.VideoCapture(device)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video device {device}")
        # Discard warmup frames
        for _ in range(warmup):
            self._cap.read()

    def read(self):
        """Read a single frame. Returns (ret, frame)."""
        return self._cap.read()

    def read_gray(self):
        """Read a single frame and convert to grayscale.

        Returns
        -------
        numpy.ndarray
            Grayscale image.

        Raises
        ------
        RuntimeError
            If the frame cannot be read.
        """
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Failed to read frame from camera")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def release(self):
        """Release the underlying VideoCapture."""
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def flush_buffer(cap, n=5):
    """Grab and discard *n* frames to flush OpenCV's internal buffer.

    V4L2 VideoCapture keeps a small queue of decoded frames.  After a
    camera movement we need to drain them so the next ``read()``
    returns a truly *current* frame.
    """
    for _ in range(n):
        cap.grab()


def compute_phase_shift(prev_gray, curr_gray):
    """Measure horizontal and vertical shift via phase correlation.

    Uses ``cv2.phaseCorrelate`` on the full frame which is robust to
    lighting changes and handles large sub-pixel displacements.

    Returns (dx, dy) where positive dx means the content moved RIGHT
    in *curr_gray* relative to *prev_gray* (camera panned LEFT).
    """
    prev_f = np.float64(prev_gray)
    curr_f = np.float64(curr_gray)
    (dx, dy), response = cv2.phaseCorrelate(prev_f, curr_f)
    return float(dx), float(dy), float(response)


def compute_sparse_flow(prev_gray, curr_gray):
    """Compute sparse optical flow using Lucas-Kanade on Shi-Tomasi corners.

    Parameters
    ----------
    prev_gray : numpy.ndarray
        Previous frame in grayscale.
    curr_gray : numpy.ndarray
        Current frame in grayscale.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        (dx_array, dy_array) -- arrays of horizontal and vertical
        displacement for each tracked feature point. Empty arrays if
        no features are found or tracked.
    """
    # Detect good features (Shi-Tomasi corners)
    feature_params = dict(
        maxCorners=200,
        qualityLevel=0.01,
        minDistance=10,
        blockSize=7,
    )
    prev_pts = cv2.goodFeaturesToTrack(prev_gray, **feature_params)

    if prev_pts is None or len(prev_pts) == 0:
        return np.array([]), np.array([])

    # Lucas-Kanade optical flow
    lk_params = dict(
        winSize=(21, 21),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray, curr_gray, prev_pts, None, **lk_params
    )

    # Filter to successfully tracked points
    good_mask = status.ravel() == 1
    if not np.any(good_mask):
        return np.array([]), np.array([])

    prev_good = prev_pts[good_mask]
    curr_good = curr_pts[good_mask]

    dx = curr_good[:, 0, 0] - prev_good[:, 0, 0]
    dy = curr_good[:, 0, 1] - prev_good[:, 0, 1]

    return dx, dy


def compute_frame_difference(frame1, frame2):
    """Compute mean absolute pixel difference between two frames.

    Parameters
    ----------
    frame1 : numpy.ndarray
        First frame (BGR or grayscale).
    frame2 : numpy.ndarray
        Second frame (BGR or grayscale).

    Returns
    -------
    float
        Mean of the absolute difference image.
    """
    diff = cv2.absdiff(frame1, frame2)
    return float(np.mean(diff))


def estimate_fov_change(prev_gray, curr_gray):
    """Estimate field-of-view change using multi-scale template matching.

    Crops a template from the centre of *prev_gray* and searches for it
    in *curr_gray* at multiple scales.  The scale with the best match
    indicates how much the FOV changed.  A ratio > 1.0 means the
    template appears larger in *curr_gray* (zoom in), < 1.0 means
    smaller (zoom out).

    Returns 1.0 if no reliable match is found.
    """
    h, w = prev_gray.shape[:2]
    # Use central 20% of frame as template
    th, tw = h // 5, w // 5
    y0, x0 = h // 2 - th // 2, w // 2 - tw // 2
    template = prev_gray[y0:y0 + th, x0:x0 + tw]

    best_val = -1.0
    best_scale = 1.0

    for scale_pct in range(30, 200, 3):
        scale = scale_pct / 100.0
        new_w = int(tw * scale)
        new_h = int(th * scale)
        if new_w >= w or new_h >= h or new_w < 10 or new_h < 10:
            continue
        resized = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(curr_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_scale = scale

    if best_val < 0.3:
        return 1.0

    return best_scale

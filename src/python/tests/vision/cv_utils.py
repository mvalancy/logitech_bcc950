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
    """Estimate field-of-view change using ORB feature matching.

    Computes the ratio of mean inter-feature distances between matched
    keypoints in the current frame vs the previous frame. A ratio > 1
    indicates features have spread apart (zoom in), < 1 indicates they
    have come closer (zoom out).

    Parameters
    ----------
    prev_gray : numpy.ndarray
        Previous frame in grayscale.
    curr_gray : numpy.ndarray
        Current frame in grayscale.

    Returns
    -------
    float
        Ratio of mean inter-feature distance (curr / prev).
        Returns 1.0 if insufficient matches are found.
    """
    orb = cv2.ORB_create(nfeatures=500)

    kp1, des1 = orb.detectAndCompute(prev_gray, None)
    kp2, des2 = orb.detectAndCompute(curr_gray, None)

    if des1 is None or des2 is None or len(des1) < 4 or len(des2) < 4:
        return 1.0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)

    if len(matches) < 4:
        return 1.0

    # Sort by distance (best matches first) and take top matches
    matches = sorted(matches, key=lambda m: m.distance)
    top_n = min(50, len(matches))
    matches = matches[:top_n]

    # Extract matched keypoint coordinates
    pts1 = np.array([kp1[m.queryIdx].pt for m in matches])
    pts2 = np.array([kp2[m.trainIdx].pt for m in matches])

    # Compute mean pairwise inter-feature distance for each set
    def mean_inter_distance(pts):
        if len(pts) < 2:
            return 1.0
        dists = []
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = np.linalg.norm(pts[i] - pts[j])
                dists.append(d)
        return float(np.mean(dists)) if dists else 1.0

    dist_prev = mean_inter_distance(pts1)
    dist_curr = mean_inter_distance(pts2)

    if dist_prev == 0:
        return 1.0

    return dist_curr / dist_prev

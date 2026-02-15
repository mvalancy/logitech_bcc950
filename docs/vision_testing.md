# Vision-Based Testing Methodology

## Overview

The BCC950 camera has no absolute pan/tilt position readback. To verify that motor commands actually produce the expected physical movement, we use computer vision techniques to analyze the camera's own video feed. The test suite captures frames before and after issuing a movement command, then applies CV algorithms to measure whether the scene shifted in the expected direction and magnitude.

## Test Infrastructure

Vision tests live in `src/python/tests/vision/` and require:

- `--run-vision` pytest flag
- `--device /dev/videoN` pointing to a connected BCC950
- OpenCV (`opencv-python >= 4.8`) and NumPy (`numpy >= 1.24`)

The `conftest.py` provides two fixtures:

- **`camera_capture`** -- Opens an OpenCV `VideoCapture`, discards 10 warmup frames (so auto-exposure and white balance settle), yields the capture, and releases on teardown.
- **`hardware_controller`** -- A `BCC950Controller` connected to real hardware via `SubprocessV4L2Backend`.

## CV Techniques

### 1. Lucas-Kanade Sparse Optical Flow (Pan/Tilt Verification)

**Purpose:** Detect and quantify the direction of scene motion caused by pan or tilt commands.

**How it works:**

1. Capture a "before" frame.
2. Detect good features to track using Shi-Tomasi corner detection (`cv2.goodFeaturesToTrack`).
3. Issue the pan or tilt command.
4. Capture an "after" frame.
5. Compute optical flow vectors between the two frames using `cv2.calcOpticalFlowPyrLK`.
6. Filter out points with poor tracking status.
7. Compute the median flow vector `(dx, dy)` across all tracked points.

**Interpretation:**

| Command | Expected Flow Direction |
|---------|----------------------|
| Pan left | Positive median `dx` (scene moves right in frame) |
| Pan right | Negative median `dx` (scene moves left in frame) |
| Tilt up | Positive median `dy` (scene moves down in frame) |
| Tilt down | Negative median `dy` (scene moves up in frame) |

The scene moves in the *opposite* direction to the camera because the camera is looking at a static environment.

**Parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `maxCorners` | 100 | Enough for statistical robustness without slowing detection |
| `qualityLevel` | 0.3 | Moderate corner quality threshold; too low picks up noise, too high may find too few points in low-texture scenes |
| `minDistance` | 7 | Minimum pixel spacing between corners to avoid clustering |
| `blockSize` | 7 | Neighborhood size for corner detection |
| `winSize` (LK) | (15, 15) | Optical flow search window; 15px handles typical BCC950 frame-to-frame displacement at 0.3s duration |
| `maxLevel` (LK) | 2 | Pyramid levels; 2 is sufficient for the small displacements we expect |

### 2. ORB Feature Matching (Zoom Verification)

**Purpose:** Verify that zoom-in magnifies the scene and zoom-out shrinks it by comparing the spatial distribution of matched features.

**How it works:**

1. Capture a "before" frame.
2. Detect ORB keypoints and descriptors in the before frame.
3. Issue the zoom command (e.g., `zoom_to(300)`).
4. Capture an "after" frame.
5. Detect ORB keypoints and descriptors in the after frame.
6. Match descriptors using brute-force Hamming distance with ratio test (Lowe's ratio = 0.75).
7. For each good match, compute the distance from the frame center to the keypoint in both frames.
8. Compare the median distance-from-center: after zooming in, matched features should be *farther* from the center (magnified outward); after zooming out, they should be *closer*.

**Parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `nfeatures` (ORB) | 500 | Enough features for reliable matching across zoom levels |
| Lowe's ratio | 0.75 | Standard ratio test threshold for filtering ambiguous matches |
| Minimum good matches | 10 | Below this, the result is inconclusive (too few features survived) |

### 3. Frame Differencing (General Movement Detection)

**Purpose:** Simple binary check that *something* changed in the frame, used as a sanity gate before applying more expensive techniques.

**How it works:**

1. Capture a "before" frame, convert to grayscale.
2. Issue the movement command.
3. Capture an "after" frame, convert to grayscale.
4. Compute `cv2.absdiff(before_gray, after_gray)`.
5. Threshold the difference image at a fixed pixel intensity value.
6. Count the fraction of pixels above threshold.

**Parameters:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Difference threshold | 25 | Pixel intensity units (0-255). Filters out sensor noise and minor auto-exposure changes. The BCC950 sensor noise floor is typically under 10-15 units. |
| Changed-pixel fraction threshold | 0.01 (1%) | If fewer than 1% of pixels changed, the scene is considered static. Pan/tilt at 0.3s duration typically changes 10-40% of pixels depending on scene texture. |

## Threshold Values and Rationale

| Threshold | Value | What It Measures | When to Adjust |
|-----------|-------|-----------------|----------------|
| Optical flow magnitude (pan/tilt) | >= 3.0 px | Minimum median displacement to confirm movement | Increase if testing with very short durations (< 0.1s); decrease for long durations (> 1.0s) or low-framerate captures |
| Optical flow direction tolerance | sign match | Median flow sign must match expected direction | N/A -- binary check |
| Feature match distance ratio (zoom) | > 1.1x or < 0.9x | Ratio of median distance-from-center (after/before) | Adjust for small zoom steps (delta < 50 may produce ratios close to 1.0) |
| Frame difference threshold | 25/255 | Pixel intensity change to count as "moved" | Increase in noisy/low-light environments; decrease in well-lit static scenes |
| Changed pixel fraction | >= 1% | Fraction of frame that changed | Increase if camera has a flickering light source in view |

## How to Interpret Results

**A test passes when:**

1. Frame differencing confirms something changed (sanity gate).
2. Optical flow median direction matches the expected direction for the command issued.
3. Optical flow median magnitude exceeds the minimum threshold.
4. For zoom tests: the feature distance ratio moves in the correct direction.

**Common failure modes:**

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Frame difference below threshold | Camera did not actually move, or scene has no texture (blank wall) | Check device path, verify motor is functional, add visual texture to the scene |
| Optical flow direction is wrong | Camera wiring or V4L2 control mapping is inverted | Check `pan_speed` sign convention for your firmware version |
| Optical flow magnitude is too low | Movement duration too short, or camera is at the mechanical limit | Increase `--duration`, reset camera position before test |
| Too few ORB matches for zoom test | Scene lacks texture or zoom step is too small | Add textured objects to the scene, increase zoom delta |
| Intermittent failures | Auto-exposure or white balance shifting between frames | Increase warmup frames, fix exposure manually with `v4l2-ctl -c exposure_auto=1` |

## Adjusting Thresholds

If you need to tune thresholds for your environment:

1. Run the vision tests with `pytest -s --run-vision --run-hardware` to see printed diagnostics.
2. Look at the reported median flow values and frame difference percentages.
3. If values are consistently near but below the threshold, lower the threshold by 20-30%.
4. If values are noisy and occasionally crossing in the wrong direction, increase movement duration to produce larger, more consistent displacements.
5. For zoom tests, use larger zoom deltas (e.g., zoom from 100 to 300 instead of 100 to 150) for more definitive results.

## Test Criteria Table

| Test | Command | CV Method | Pass Criteria | Typical Value |
|------|---------|-----------|---------------|---------------|
| Pan left detected | `pan_left(0.3)` | Lucas-Kanade optical flow | median `dx` > +3.0 px | 8-25 px |
| Pan right detected | `pan_right(0.3)` | Lucas-Kanade optical flow | median `dx` < -3.0 px | -8 to -25 px |
| Tilt up detected | `tilt_up(0.3)` | Lucas-Kanade optical flow | median `dy` > +3.0 px | 5-15 px |
| Tilt down detected | `tilt_down(0.3)` | Lucas-Kanade optical flow | median `dy` < -3.0 px | -5 to -15 px |
| Zoom in magnifies | `zoom_to(300)` from 100 | ORB feature matching | distance ratio > 1.1 | 1.3-2.0 |
| Zoom out shrinks | `zoom_to(100)` from 300 | ORB feature matching | distance ratio < 0.9 | 0.5-0.8 |
| Any movement detected | any PTZ command | Frame differencing | changed pixels > 1% | 10-40% |
| No false movement | no command (control) | Frame differencing | changed pixels < 1% | 0.1-0.5% |

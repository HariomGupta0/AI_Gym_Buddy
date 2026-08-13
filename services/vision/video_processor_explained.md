# `VideoProcessorClass` — Code Walkthrough

This document explains what `VideoProcessorClass` does, piece by piece, for future reference.

## What this file is for

This is a **real-time exercise-form checker**. It plugs into `streamlit-webrtc` as a `VideoProcessorBase`. For every webcam frame it:
1. Mirrors the frame so it feels natural to the user.
2. Runs Google MediaPipe's Pose Landmarker to find body joint positions.
3. Draws a skeleton overlay on the video.
4. Feeds the joint positions to an exercise-specific "detector" (Squats, Push-ups, Curls, Shoulder Press, Lunges) that scores form and counts reps.
5. Draws feedback text (like `DEPTH: Good`) onto the frame.
6. Returns the finished frame back to the browser.

---

## `__init__` — setup done once per session

- `self._lock` — a threading lock. `recv()` runs on a background thread per frame, while Streamlit's main thread reads `self._latest_metrics` to update the UI. The lock prevents both from touching that data at the same time.
- `self._latest_metrics` — most recent exercise results (reps, status, etc.), shared with the rest of the app.
- `self._exercise_type` — which exercise is currently selected (default `"Squats"`).
- **Loading the model**: builds the path to `pose_landmarker_full.task` and creates a `PoseLandmarker` in `VIDEO` mode (since this is a live stream, not single images), with confidence thresholds of 0.7 for detection, presence, and tracking — i.e., MediaPipe only reports a pose/joint if it's fairly confident.
- `self._detectors` — a dictionary mapping exercise name → the object that knows how to judge that exercise's form.
- `self._frame_timestamps_ms` — running counter MediaPipe needs to know frame order/timing in video mode.

## Getters/setters (`set_latest_metrics`, `get_latest_metrics`, `set_exercise`, `get_exercise`)

Thread-safe read/write helpers — every access goes through `self._lock` so the UI thread and the video-processing thread never read/write `_latest_metrics` or `_exercise_type` simultaneously.

## `_draw_skeleton(img, landmarks)`

Draws the visual skeleton:
- Loops through `POSE_CONNECTIONS` (pairs of joint indices that should be connected, e.g., shoulder→elbow).
- Only draws a line if **both** joints have `visibility > 0.7` (MediaPipe's confidence that the joint is actually visible/not occluded).
- Draws green lines (`(0,255,0)`) between connected joints, and blue dots (`(255,0,0)`) on each visible joint — note OpenCV uses BGR order, so `(255,0,0)` is actually blue, `(0,255,0)` is green.

## `_draw_no_pose_warnings(img)`

If no body was detected, overlays two lines of text: `NO POSE DETECTED` and `PLEASE FACE THE CAMERA`.

## `_draw_overlays(img, metrics, ex_type)` + exercise-specific overlay methods

Dispatches to one of five small helper methods based on `ex_type`, each of which prints exercise-specific status text near the bottom-left of the frame:
- Squats → `DEPTH: {status}`
- Push-ups → `BODY: {alignment} | HIP: {status}`
- Curls → `SWING: {status}`
- Shoulder Press → `EXT: {status} | BACK: {status}`
- Lunges → `BALANCE: {status}`

These just format and draw whatever the detector already computed — no exercise logic lives here.

## `recv(frame)` — runs on every incoming video frame

This is the main pipeline, called automatically by `streamlit-webrtc` for each frame:

1. **Mirror the frame**
   ```python
   image = np.asarray(cv2.flip(frame.to_ndarray(format="bgr24"), 1), dtype=np.uint8)
   ```
   Raw front-camera video feels backwards (you raise your right hand, it moves on the left of the screen). `cv2.flip(..., 1)` flips horizontally so it behaves like a mirror — natural for the user to follow while exercising. All pose detection and drawing happens **on this already-flipped image**, so what's analyzed matches what's displayed.

2. **Convert into MediaPipe's image format**
   ```python
   mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
   ```
   MediaPipe needs its own `mp.Image` wrapper. The `cvtColor` call swaps red/blue channels because OpenCV and MediaPipe expect different channel orders. (Note: the conversion constant name `RGB2BGR` looks like it's doing the "wrong" direction given the frame started as `bgr24`, but since it's just a channel swap, `RGB2BGR` and `BGR2RGB` perform the identical operation — so it still works, just with a slightly confusing name.)

3. **Timestamp and detect**
   ```python
   self._frame_timestamps_ms += 30
   result = self._landmarker.detect_for_video(mp_image, self._frame_timestamps_ms)
   ```
   MediaPipe's `VIDEO` mode needs increasing timestamps to track a person across frames. `+= 30` assumes roughly 30ms/frame (~33 fps) — an estimate, not measured from the actual camera framerate. `detect_for_video` runs the actual pose model and returns a `result`.

4. **If a body was found**
   ```python
   if result.pose_landmarks:
       landmarks = result.pose_landmarks[0]
   ```
   MediaPipe can detect multiple people; `[0]` takes only the first detected person's landmarks (nose, shoulders, elbows, wrists, hips, knees, ankles, etc., each with x/y/visibility).

   - `self._draw_skeleton(image, landmarks)` — draws the joints/lines on the frame.
   - `ex_type = self.get_exercise()` — reads which exercise the user has selected.
   - `detector = self._detectors.get(ex_type)` — picks the matching detector object (e.g. `SquatDetector`).
   - `if detector:` → `metrics = detector.process(landmarks)` — the actual form-checking/rep-counting logic lives inside the detector class, not here. It returns a dict like `{"reps": 5, "depth_status": "Good"}`.
   - `metrics["pose_detected"] = True` — tags the result as coming from a valid detection.
   - `self._draw_overlays(image, metrics, ex_type)` — writes the feedback text onto the frame.
   - `self.set_latest_metrics(metrics)` — thread-safely stores the result so the Streamlit UI (sidebar/cards) can display reps/status.

5. **If no body was found**
   ```python
   else:
       self._draw_no_pose_warnings(image)
       with self._lock:
           if self._latest_metrics is not None:
               self._latest_metrics["pose_detected"] = False
           else:
               self._latest_metrics = {"pose_detected": False}
   ```
   Draws the "no pose" warning text, and updates/creates `_latest_metrics` to reflect that no pose is currently detected — without wiping out previous rep counts if metrics already existed.

6. **Return the frame**
   ```python
   return av.VideoFrame.from_ndarray(image, format="bgr24")
   ```
   Hands the fully-processed frame (mirrored, skeleton drawn, feedback text drawn) back to `streamlit-webrtc`, which sends it to the browser.

---

## End-to-end flow per frame

```
Camera frame
   → flip horizontally (mirror effect)
   → convert to MediaPipe image format
   → timestamp + detect pose
   → pose found?
        yes → draw skeleton
              → pick detector for selected exercise
              → detector.process(landmarks) → metrics (reps, form status)
              → draw feedback text
              → save metrics (thread-safe)
        no  → draw "NO POSE DETECTED" warning
              → mark pose_detected = False (thread-safe)
   → return frame to browser
```

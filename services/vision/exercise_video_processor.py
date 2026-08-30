import os
import cv2
import av
import numpy as np
import mediapipe as mp
import threading
from streamlit_webrtc import VideoProcessorBase
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from detectors.squat import SquatDetector
from detectors.pushup import PushUpDetector
from detectors.biceps_curls import BicepsCurlDetector
from detectors.shoulder_press import ShoulderPressDetector
from detectors.lunges import LungesDetector
from detectors.plank import PlankDetector
from detectors.jumping_jacks import JumpingJacksDetector
from services.config.workout_config import POSE_CONNECTIONS


class VideoProcessorClass(VideoProcessorBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_metrics = None
        self._exercise_type = "Squats"

        model_path = os.path.join(os.getcwd(), "ml_models", "pose_landmarker_full.task")
        base_option = python.BaseOptions(model_asset_path=model_path)

        options = vision.PoseLandmarkerOptions(
            base_options=base_option,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.7,
            min_pose_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            output_segmentation_masks=False
        )

        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        self._detectors = {
            "Squats": SquatDetector(),
            "Push-ups": PushUpDetector(),
            "Biceps Curls (Dumbbell)": BicepsCurlDetector(),
            "Shoulder Press": ShoulderPressDetector(),
            "Lunges": LungesDetector(),
            "Planks": PlankDetector(),
            "Jumping Jacks": JumpingJacksDetector(),
        }

        self._frame_timestamps_ms = 0
    
    def set_latest_metrics(self, metrics):
        with self._lock:
            self._latest_metrics = metrics.copy()

    def get_latest_metrics(self):
        with self._lock:
            return None if self._latest_metrics is None else self._latest_metrics.copy()
        
    def set_exercise(self, exercise_type):
        with self._lock:
            self._exercise_type = exercise_type

    def get_exercise(self):
        with self._lock:
            return self._exercise_type
        
    def _draw_skeleton(self, img, landmarks, metrics, ex_type):
        h, w = img.shape[:2]

        default_color = (0, 255, 0)  # Green (BGR)
        error_color = (0, 0, 255)    # Red (BGR)

        torso_connections = {(11, 23), (12, 24), (23, 24)}
        leg_connections = {
            (23, 25), (24, 26), (25, 27), (26, 28),
            (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32)
        }
        arm_connections = {(11, 13), (12, 14), (13, 15), (14, 16)}

        torso_color = default_color
        leg_color = default_color
        arm_color = default_color

        if metrics:
            if ex_type == "Squats":
                depth = metrics.get("depth_status", "")
                back = metrics.get("back_angle", 180)
                if depth == "TOO HIGH":
                    leg_color = error_color
                if isinstance(back, (int, float)) and back < 130:
                    torso_color = error_color
                    
            elif ex_type == "Push-ups":
                alignment = metrics.get("body_alignment", "")
                hip = metrics.get("hip_status", "")
                if alignment == "Poor Form":
                    torso_color = error_color
                    leg_color = error_color
                if hip in ["SAGGING", "PIKED UP"]:
                    torso_color = error_color
                    
            elif ex_type == "Biceps Curls (Dumbbell)":
                shoulder = metrics.get("shoulder_status", "")
                swing = metrics.get("swing_status", "")
                if shoulder == "ELBOW DRIFTING" or swing == "SWING DETECTED":
                    arm_color = error_color
                    
            elif ex_type == "Shoulder Press":
                back_arch = metrics.get("back_arch_status", "")
                if back_arch == "Excessive Arch":
                    torso_color = error_color
                    
            elif ex_type == "Lunges":
                balance = metrics.get("balance_status", "")
                if balance == "OFF BALANCE":
                    leg_color = error_color
                    torso_color = error_color
                    
            elif ex_type == "Planks":
                alignment = metrics.get("body_alignment", "")
                hip = metrics.get("hip_status", "")
                if alignment == "Poor Form" or hip in ["SAGGING", "PIKED UP"]:
                    torso_color = error_color
                    leg_color = error_color
                    
            elif ex_type == "Jumping Jacks":
                jack = metrics.get("jack_status", "")
                arms = metrics.get("arm_extension", "")
                if jack == "LEGS TOO CLOSE":
                    leg_color = error_color
                if arms == "ARMS TOO LOW":
                    arm_color = error_color

        for start_idx, end_idx in POSE_CONNECTIONS:
            p1 = landmarks[start_idx]
            p2 = landmarks[end_idx]

            if p1.visibility > 0.7 and p2.visibility > 0.7:
                conn = (start_idx, end_idx)
                if conn in torso_connections:
                    color = torso_color
                elif conn in leg_connections:
                    color = leg_color
                elif conn in arm_connections:
                    color = arm_color
                else:
                    color = default_color

                cv2.line(
                    img,
                    (int(p1.x * w), int(p1.y * h)),
                    (int(p2.x * w), int(p2.y * h)),
                    color,
                    8
                )
        
        for lm in landmarks:
            if lm.visibility > 0.7:
                cv2.circle(
                    img, 
                    (int(lm.x * w), int(lm.y * h)),
                    8,
                    (255, 0, 0),
                    -1
                )
            
    def _draw_no_pose_warnings(self, img):
        cv2.putText(
            img,
            "NO POSE DETECTED",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            img,
            "PLEASE FACE THE CAMERA",
            (30, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    def _draw_overlays(self, img, metrics, ex_type):
        if ex_type == "Squats":
            self._draw_squats_overlays(img, metrics)
        elif ex_type == "Push-ups":
            self._draw_pushup_overlays(img, metrics)
        elif ex_type == "Biceps Curls (Dumbbell)":
            self._draw_curl_overlays(img, metrics)
        elif ex_type == "Shoulder Press":
            self._draw_press_overlays(img, metrics)
        elif ex_type == "Lunges":
            self._draw_lunge_overlays(img, metrics)
        elif ex_type == "Planks":
            self._draw_plank_overlays(img, metrics)
        elif ex_type == "Jumping Jacks":
            self._draw_jumping_jacks_overlays(img, metrics)


    def _draw_squats_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"DEPTH: {metrics['depth_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
    
    def _draw_pushup_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"BODY: {metrics['body_alignment']} | HIP: {metrics['hip_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_curl_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"SWING: {metrics['swing_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_press_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"EXT: {metrics['extension_status']} | BACK: {metrics['back_arch_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_lunge_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"BALANCE: {metrics['balance_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_plank_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"ALIGN: {metrics['body_alignment']} | HIP: {metrics['hip_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_jumping_jacks_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"STANCE: {metrics['jack_status']} | ARMS: {metrics['arm_extension']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def recv(self, frame):
        image = np.asarray(
            cv2.flip(frame.to_ndarray(format="bgr24"), 1),
            dtype=np.uint8
        )

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        )

        self._frame_timestamps_ms += 30
        result = self._landmarker.detect_for_video(mp_image, self._frame_timestamps_ms)

        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]
            ex_type = self.get_exercise()
            detector = self._detectors.get(ex_type)

            metrics = {}
            if detector:
                metrics = detector.process(landmarks)
                self.set_latest_metrics(metrics)

            self._draw_skeleton(image, landmarks, metrics, ex_type)

            if detector:
                self._draw_overlays(image, metrics, ex_type)
        else:
            self._draw_no_pose_warnings(image)

        return av.VideoFrame.from_ndarray(image, format="bgr24")
    
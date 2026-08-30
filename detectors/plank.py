import time
from core.base_exercise import BaseExercise

class PlankDetector(BaseExercise):
    MIN_VISIBILITY = 0.7
    HIP_SAG_TOLERANCE = 0.08

    LEFT_SHOULDER = 11
    LEFT_HIP = 23
    LEFT_ANKLE = 27
    RIGHT_SHOULDER = 12
    RIGHT_HIP = 24
    RIGHT_ANKLE = 28

    def __init__(self):
        super().__init__()
        self.accumulated_time = 0.0
        self.hold_start_time = None
        self.last_update_time = None

    def reset(self) -> None:
        self.reps = 0
        self.accumulated_time = 0.0
        self.hold_start_time = None
        self.last_update_time = None
        self.stage = "resting"

    def process(self, landmarks) -> dict:
        left_vis = landmarks[self.LEFT_HIP].visibility
        right_vis = landmarks[self.RIGHT_HIP].visibility

        if left_vis >= right_vis:
            shoulder_idx = self.LEFT_SHOULDER
            hip_idx = self.LEFT_HIP
            ankle_idx = self.LEFT_ANKLE
        else:
            shoulder_idx = self.RIGHT_SHOULDER
            hip_idx = self.RIGHT_HIP
            ankle_idx = self.RIGHT_ANKLE

        shoulder_y = landmarks[shoulder_idx].y
        ankle_y = landmarks[ankle_idx].y
        hip_y = landmarks[hip_idx].y

        expected_hip_y = (shoulder_y + ankle_y) / 2
        hip_deviation = hip_y - expected_hip_y

        body_angle = self.calculate_angle(
            self.get_point(landmarks, shoulder_idx),
            self.get_point(landmarks, hip_idx),
            self.get_point(landmarks, ankle_idx),
        )

        key_landmarks_visible = (
            landmarks[shoulder_idx].visibility > self.MIN_VISIBILITY
            and landmarks[hip_idx].visibility > self.MIN_VISIBILITY
            and landmarks[ankle_idx].visibility > self.MIN_VISIBILITY
        )

        if body_angle > 155:
            body_alignment = "Straight"
        elif body_angle > 140:
            body_alignment = "Slight Bend"
        else:
            body_alignment = "Poor Form"

        if abs(hip_deviation) <= self.HIP_SAG_TOLERANCE:
            hip_status = "LEVEL"
        elif hip_deviation > self.HIP_SAG_TOLERANCE:
            hip_status = "SAGGING"
        else:
            hip_status = "PIKED UP"

        # Valid plank is straight body and level hips
        is_plank_active = key_landmarks_visible and body_alignment == "Straight" and hip_status == "LEVEL"

        now = time.time()
        if is_plank_active:
            if self.hold_start_time is None:
                self.hold_start_time = now
                self.last_update_time = now
                self.stage = "planking"
            else:
                elapsed = now - self.last_update_time
                self.accumulated_time += elapsed
                self.last_update_time = now
                self.reps = int(self.accumulated_time)
                self.stage = "planking"
        else:
            self.hold_start_time = None
            self.last_update_time = None
            self.stage = "incorrect form / resting"

        return {
            "reps": self.reps,  # Reps count acts as total active hold seconds
            "body_alignment": body_alignment,
            "hip_status": hip_status,
            "stage": self.stage
        }

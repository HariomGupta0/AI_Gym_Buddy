from core.base_exercise import BaseExercise

class JumpingJacksDetector(BaseExercise):
    MIN_VISIBILITY = 0.7

    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28

    def __init__(self):
        super().__init__()
        self.stage = "closed"

    def reset(self) -> None:
        self.reps = 0
        self.stage = "closed"

    def process(self, landmarks) -> dict:
        left_shoulder = self.get_point(landmarks, self.LEFT_SHOULDER)
        right_shoulder = self.get_point(landmarks, self.RIGHT_SHOULDER)
        left_ankle = self.get_point(landmarks, self.LEFT_ANKLE)
        right_ankle = self.get_point(landmarks, self.RIGHT_ANKLE)

        # Stance is horizontal distance between ankles divided by shoulder width
        shoulder_width = abs(left_shoulder[0] - right_shoulder[0])
        ankle_dist = abs(left_ankle[0] - right_ankle[0])

        if shoulder_width == 0:
            stance_ratio = 1.0
        else:
            stance_ratio = ankle_dist / shoulder_width

        left_wrist_y = landmarks[self.LEFT_WRIST].y
        right_wrist_y = landmarks[self.RIGHT_WRIST].y
        left_shoulder_y = landmarks[self.LEFT_SHOULDER].y
        right_shoulder_y = landmarks[self.RIGHT_SHOULDER].y
        left_hip_y = landmarks[self.LEFT_HIP].y
        right_hip_y = landmarks[self.RIGHT_HIP].y

        # Arms are up if wrists are above shoulders
        arms_up = (left_wrist_y < left_shoulder_y) and (right_wrist_y < right_shoulder_y)
        
        # Arms are down if wrists are below hips
        arms_down = (left_wrist_y > left_hip_y) and (right_wrist_y > right_hip_y)

        legs_wide = stance_ratio > 1.2
        legs_closed = stance_ratio < 0.9

        key_landmarks_visible = (
            landmarks[self.LEFT_WRIST].visibility > self.MIN_VISIBILITY
            and landmarks[self.RIGHT_WRIST].visibility > self.MIN_VISIBILITY
            and landmarks[self.LEFT_ANKLE].visibility > self.MIN_VISIBILITY
            and landmarks[self.RIGHT_ANKLE].visibility > self.MIN_VISIBILITY
        )

        jack_status = "N/A"
        arm_extension = "N/A"

        if key_landmarks_visible:
            # Stage transition logic
            if legs_wide and arms_up:
                self.stage = "open"
                jack_status = "OPEN STANCE"
                arm_extension = "FULL EXTENSION"

            elif legs_closed and arms_down and self.stage == "open":
                self.stage = "closed"
                self.reps += 1
                jack_status = "CLOSED STANCE"
                arm_extension = "ARMS DOWN"

            # Form issue checking
            if legs_wide and not arms_up:
                jack_status = "WIDE LEGS"
                arm_extension = "ARMS TOO LOW"
            elif not legs_wide and arms_up:
                jack_status = "LEGS TOO CLOSE"
                arm_extension = "ARMS UP"
            elif self.stage == "closed":
                jack_status = "CLOSED"
                arm_extension = "ARMS DOWN"
        else:
            jack_status = "NOT VISIBLE"
            arm_extension = "NOT VISIBLE"

        return {
            "reps": self.reps,
            "jack_status": jack_status,
            "arm_extension": arm_extension,
            "stance_ratio": round(stance_ratio, 2),
            "stage": self.stage
        }

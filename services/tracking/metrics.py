import streamlit as st
import time 
from services.persistence.exercise_repository import add_exercise
from services.config.workout_config import METRICS_FIELDS


def sync_metrics_update(context):
    if not context or not hasattr(context, "state") or not context.state.playing:
        return
    
    processor = getattr(context, "video_processor", None)

    if not processor:
        return 
    
    exercise = st.session_state.get("exercise_type")

    if not exercise:
        return
    
    processor.set_exercise(exercise)
    latest_metrics = processor.get_latest_metrics()

    if not latest_metrics:
        return
    
    reps = latest_metrics.get("reps")
    st.session_state.reps = reps

    fields = METRICS_FIELDS.get(exercise)

    if not fields:
        return 

    for key, default in fields.items():
        st.session_state[key] = latest_metrics.get(key, default)

    reps_per_set = st.session_state.get("reps_per_set", 0)
    target_sets = st.session_state.get("target_sets", 0)

    if reps_per_set > 0 and target_sets > 0:
        sets_completed = reps // reps_per_set
        current_set_reps = reps % reps_per_set
        workout_completed = sets_completed >= target_sets 
    else:
        sets_completed = 0
        current_set_reps = 0
        workout_completed = False

    st.session_state.sets_completed = sets_completed
    st.session_state.current_set_reps = current_set_reps
    st.session_state.workout_completed = workout_completed

    last_saved_sets = st.session_state.get("last_saved_sets_completed", 0)

    if target_sets > 0 and reps_per_set > 0 and sets_completed > last_saved_sets:
        newly_completed = sets_completed - last_saved_sets
        now_ts = time.time()
        started_at = st.session_state.get("set_cycle_started_at", now_ts)
        time_taken = now_ts - started_at
        user_id = st.session_state.get("user_id", 0)

        add_exercise(user_id, exercise, newly_completed * reps_per_set, newly_completed, time_taken)

        if st.session_state.get("voice_pipeline"):
            result = st.session_state.voice_pipeline.process_event(
                event="set_completed",
                exercise=exercise,
                metrics=latest_metrics,
            )

            if result:
                st.session_state.audio_to_play, st.session_state.coach_feedback = result

        st.session_state.set_cycle_started_at = now_ts
        st.session_state.last_saved_sets_completed = sets_completed
        
    if workout_completed and st.session_state.get("workout_started"):
        if st.session_state.get("circuit_mode", False):
            idx = st.session_state.get("circuit_index", 0)
            exercises = st.session_state.get("circuit_queue", [])
            targets = st.session_state.get("circuit_targets", {})
            
            if idx + 1 < len(exercises):
                next_idx = idx + 1
                next_ex = exercises[next_idx]
                st.session_state.circuit_index = next_idx
                st.session_state.exercise_type = next_ex
                st.session_state.target_sets = int(targets[next_ex]["sets"])
                st.session_state.reps_per_set = int(targets[next_ex]["reps"])
                
                # Reset workout states for next exercise
                st.session_state.reps = 0
                st.session_state.sets_completed = 0
                st.session_state.current_set_reps = 0
                st.session_state.last_saved_sets_completed = 0
                st.session_state.set_cycle_started_at = time.time()
                
                # Reset the processor exercise type and local detector
                processor.set_exercise(next_ex)
                if hasattr(processor, "_detectors"):
                    detector = processor._detectors.get(next_ex)
                    if detector:
                        detector.reset()

                # Trigger transition voice prompt
                if st.session_state.get("voice_pipeline"):
                    result = st.session_state.voice_pipeline.process_event(
                        event="circuit_transition",
                        exercise=next_ex,
                        metrics={}
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result
            else:
                st.session_state.workout_started = False
                if st.session_state.get("voice_pipeline"):
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_completed",
                        exercise=exercise,
                        metrics=latest_metrics,
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result
        else:
            st.session_state.workout_started = False
            if st.session_state.get("voice_pipeline"):
                result = st.session_state.voice_pipeline.process_event(
                    event="workout_completed",
                    exercise=exercise,
                    metrics=latest_metrics,
                )
                if result:
                    st.session_state.audio_to_play, st.session_state.coach_feedback = result
                
    pose_detected = latest_metrics.get("pose_detected", True)
    
    if not pose_detected and st.session_state.get("voice_pipeline") and not workout_completed:
        result = st.session_state.voice_pipeline.process_event(
            event="no_pose_detected",
            exercise=exercise,
            metrics={"issue": "No pose detected! Please step into the camera frame."},
        )
    
        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result

    if st.session_state.get("voice_pipeline") and not workout_completed:
        result = st.session_state.voice_pipeline.process_event(
            event="ongoing_form_check",
            exercise=exercise,
            metrics=latest_metrics,
        )
        
        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result    
        
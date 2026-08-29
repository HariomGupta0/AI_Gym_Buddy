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
        
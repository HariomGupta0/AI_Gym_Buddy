import streamlit as st 
import os 
import time
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTION
from services.ui.style_loader import load_css,inject_local_font, inject_webrtc_styles
from services.persistence.exercise_repository import init_db
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.vision.exercise_video_processor import VideoProcessorClass
from services.tracking.metrics import sync_metrics_update
from groq import Groq
from services.persistence.exercise_repository import get_users_exercises
from services.coaching.llm import LLMCoach
from services.coaching.tts import TextToSpeech
from services.coaching.voice_pipeline import VoicePipeline, autoplay_audio

def main():
    st.set_page_config(
        page_icon= "🏋️",
        page_title= "AI Real-time GYM Coach",
        initial_sidebar_state= "expanded",
        layout= "centered"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd() , "static", "AdobeClean.otf"), "AdobeClean")

    init_db()
    
    if not render_login_wall():
        return

    initial_session_defaults()

    if "voice_pipeline" not in st.session_state:
        try:
            api_key = os.environ.get("GROQ_API_KEY", "")

            if not api_key and hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                api_key = st.secrets["GROQ_API_KEY"]
            
            if not api_key:
                st.sidebar.warning("⚠️ Voice Coach disabled: GROQ_API_KEY not set.")
                st.session_state.voice_pipeline = None
            else:
                groq_client = Groq(api_key=api_key)
                llm_coach = LLMCoach(groq_client)
                tts = TextToSpeech()
                st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
        except Exception as e:
            st.sidebar.error(f"⚠️ Voice Coach initialization failed: {e}")
            st.session_state.voice_pipeline = None

    workout_started = st.session_state.get("workout_started",False)

    with st.sidebar:
        st.title("GymGuru AI")

        if st.session_state.username:
            st.caption(f"🗽 Login as {st.session_state.username}") 

        st.toggle("🔇 Mute Voice Coach", value=False, key="mute_audio")

        st.divider()

        st.subheader("Workout Plan")

        if not workout_started:
            workout_mode = st.radio("Workout Mode", ["Single Exercise", "Circuit Mode"], index=0, key="workout_mode")

            if workout_mode == "Single Exercise":
                plan_exercise = st.selectbox("Exercise", options=EXERCISE_OPTION, key="plan_exercise")
                plan_sets = st.number_input("Sets", min_value=1, max_value=50, value=3, key="plan_sets", step=1)
                plan_reps = st.number_input("Reps per Set", min_value=1, max_value=50, value=10, key="plan_reps", step=1)
            else:
                circuit_exercises = st.multiselect("Select Exercises in Order", options=EXERCISE_OPTION, key="circuit_exercises")
                
                circuit_targets = {}
                for ex in circuit_exercises:
                    st.markdown(f"**Target for {ex}:**")
                    col1, col2 = st.columns(2)
                    with col1:
                        s = st.number_input(f"Sets ({ex})", min_value=1, max_value=10, value=1, key=f"sets_{ex}", step=1)
                    with col2:
                        r = st.number_input(f"Reps ({ex})", min_value=1, max_value=50, value=10, key=f"reps_{ex}", step=1)
                    circuit_targets[ex] = {"sets": s, "reps": r}

            st.markdown("")
            start_session_button = st.button("Start Session", width="stretch", key="start_session_button")

            if start_session_button:
                if workout_mode == "Single Exercise":
                    st.session_state.circuit_mode = False
                    st.session_state.exercise_type = plan_exercise
                    st.session_state.target_sets = int(plan_sets)
                    st.session_state.reps_per_set = int(plan_reps)
                else:
                    if not circuit_exercises:
                        st.sidebar.error("Please select at least one exercise for the circuit!")
                        st.stop()
                    st.session_state.circuit_mode = True
                    st.session_state.circuit_queue = circuit_exercises
                    st.session_state.circuit_targets = circuit_targets
                    st.session_state.circuit_index = 0
                    
                    first_ex = circuit_exercises[0]
                    st.session_state.exercise_type = first_ex
                    st.session_state.target_sets = int(circuit_targets[first_ex]["sets"])
                    st.session_state.reps_per_set = int(circuit_targets[first_ex]["reps"])

                st.session_state.reps = 0
                st.session_state.workout_started = True
                st.session_state.set_cycle_started_at = time.time()
                st.session_state.last_saved_sets_completed = 0

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_started",
                        exercise=st.session_state.exercise_type,
                        metrics={}
                    )
                    
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.session_state.last_notified_sets_completed = 0
                st.session_state.last_notified_workout_complete = False
                st.rerun()
            
        else:
            exercise = st.session_state.get("exercise_type")
            sets = st.session_state.get("target_sets")
            reps = st.session_state.get("reps_per_set")

            st.info(f"**{exercise}** -- {sets} Sets / {reps} Reps")

            if st.session_state.get("circuit_mode", False):
                st.markdown("**Circuit Queue:**")
                idx = st.session_state.get("circuit_index", 0)
                exercises = st.session_state.get("circuit_queue", [])
                targets = st.session_state.get("circuit_targets", {})
                
                for i, ex in enumerate(exercises):
                    ex_sets = targets[ex]["sets"]
                    ex_reps = targets[ex]["reps"]
                    if i < idx:
                        st.markdown(f"~~{i+1}. {ex} ({ex_sets}x{ex_reps})~~ ✅")
                    elif i == idx:
                        st.markdown(f"👉 **{i+1}. {ex} ({ex_sets}x{ex_reps})**")
                    else:
                        st.markdown(f"{i+1}. {ex} ({ex_sets}x{ex_reps})")

            st.markdown("")
            end_session_button = st.button("End Workout", key="end_session_button", width="stretch")

            if end_session_button:
                st.session_state["workout_started"] = False
                st.rerun()

        if  workout_started:
            st.divider()

            exercise = st.session_state.get("exercise_type")
            total_reps = st.session_state.get("reps")
            current_set_reps = st.session_state.get("current_set_reps")
            reps_per_set = st.session_state.get("reps_per_set")
            sets_completed = st.session_state.get("sets_completed")
            target_sets = st.session_state.get("target_sets")

            st.subheader("Progress")

            st.metric("Total Reps", f"{total_reps}")
            st.metric("Current Set Reps", f"{current_set_reps}/ {reps_per_set}")
            st.metric("Sets Completed", f"{sets_completed}/ {target_sets}")
            
            st.divider()

            if exercise == "Squats":
                st.subheader("Squat Metrics")
                st.metric("Knee Angle", f"{st.session_state.knee_angle}°")
                st.metric("Back Angle", f"{st.session_state.back_angle}°")
                st.metric("Depth Status", st.session_state.depth_status)

            elif exercise == "Push-ups":
                st.subheader("Push-up Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Body Alignment", st.session_state.body_alignment)
                st.metric("Hip Position", st.session_state.hip_status)

            elif exercise == "Biceps Curls (Dumbbell)":
                st.subheader("Curl Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Shoulder Stability", st.session_state.shoulder_status)
                st.metric("Swing Detection", st.session_state.swing_status)

            elif exercise == "Shoulder Press":
                st.subheader("Shoulder Press Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Arm Extension", st.session_state.extension_status)
                st.metric("Back Arch", st.session_state.back_arch_status)

            elif exercise == "Lunges":
                st.subheader("Lunge Metrics")
                st.metric("Front Knee Angle", f"{st.session_state.front_knee_angle}°")
                st.metric("Torso Angle", f"{st.session_state.torso_angle}°")
                st.metric("Balance Status", st.session_state.balance_status)

            elif exercise == "Planks":
                st.subheader("Plank Metrics")
                st.metric("Body Angle", f"{st.session_state.body_angle}°")
                st.metric("Body Alignment", st.session_state.body_alignment)
                st.metric("Hip Position", st.session_state.hip_status)

            elif exercise == "Jumping Jacks":
                st.subheader("Jumping Jacks Metrics")
                st.metric("Stance Ratio", f"{st.session_state.stance_ratio}")
                st.metric("Stance Status", st.session_state.jack_status)
                st.metric("Arm Extension", st.session_state.arm_extension)

    st.title("AI Real-time GYM Coach")
    st.markdown("#### Real-time pose detection with proactive AI voice coaching")

    if st.session_state.get("audio_to_play") and not st.session_state.get("mute_audio", False):
        autoplay_audio(st.session_state.audio_to_play)

    if st.session_state.get("coach_feedback"):
        st.markdown("")
        st.success(f"🤖 **Coach:** {st.session_state.coach_feedback}")


    if not workout_started:
         st.markdown(
            """
            <div style="
                border: 10px dashed #444;
                border-radius: 0px;
                padding: 48px 32px;
                text-align: center;
                color: #888;
                margin-top: 32px;
                margin-bottom: 32px;
            ">
                <h2 style="color:#ccc; margin-bottom:8px;">👈 Set your workout plan</h2>
                <p style="font-size:1.05rem;">
                    Choose your exercise, sets and reps in the sidebar,<br>
                    then click <strong>Start Workout</strong> to activate the camera and AI coach.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        context = webrtc_streamer(
            key="exercise-analysis",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory= VideoProcessorClass,
            rtc_configuration={
                "iceServers": [
                    {"urls": ["stun:stun.l.google.com:19302"]},
                    {"urls": ["stun:openrelay.metered.ca:80"]},
                    {
                        "urls": ["turn:openrelay.metered.ca:80", "turn:openrelay.metered.ca:443"],
                        "username": "openrelayproject",
                        "credential": "openrelayproject"
                    },
                    {
                        "urls": ["turn:openrelay.metered.ca:443?transport=tcp"],
                        "username": "openrelayproject",
                        "credential": "openrelayproject"
                    }
                ]
            },
            media_stream_constraints={
                "video": True,
                "audio": False
            },
            async_processing=True
        )

        inject_webrtc_styles()

        sync_metrics_update(context)

        if context.state.playing:
            time.sleep(0.25)
            st.rerun()
        inject_webrtc_styles()

    st.divider()

    st.markdown("#### Workout History")

    user_id = st.session_state.get("user_id",0)

    if isinstance(user_id,int):
        history_rows = get_users_exercises(user_id)

        df_arr = [
            {
                "Exercise": row["exercise_name"],
                "Reps": row["reps"],
                "Sets": row["sets"],
                "Time (sec)": row["time"],
                "Date": row["created_at"]
            }
            for row in history_rows
        ]

        df = pd.DataFrame(df_arr)

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            
            # 1. KPI Metric Cards
            total_reps = df["Reps"].sum()
            total_sets = df["Sets"].sum()
            total_seconds = df["Time (sec)"].sum()
            
            # Format time into HH:MM:SS
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Reps", f"{total_reps} 🏋️")
            with col2:
                st.metric("Total Sets", f"{total_sets} 🔢")
            with col3:
                st.metric("Active Time", f"{time_str} ⏱️")
                
            st.markdown("")
            
            # 2. Interactive Charts
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown("##### Exercise Volume (Reps)")
                volume_df = df.groupby("Exercise")["Reps"].sum().reset_index()
                st.bar_chart(data=volume_df, x="Exercise", y="Reps")
                
            with chart_col2:
                st.markdown("##### Daily Activity Trend")
                trend_df = df.groupby("Date")["Reps"].sum().reset_index()
                trend_df = trend_df.sort_values("Date")
                st.line_chart(data=trend_df, x="Date", y="Reps")
                
            st.markdown("")
            
            # 3. Collapsible Detailed Workout Logs
            with st.expander("📄 Show Detailed Workout Logs"):
                agg_df = df.groupby(["Exercise", "Date"]).agg(
                    {
                        'Reps': 'sum',
                        "Sets": 'sum',
                        "Time (sec)": 'sum'
                    }
                ).reset_index()
                agg_df.index += 1
                st.table(agg_df, border="horizontal")
        else:
            st.info("No workout history found.")


if __name__ == "__main__":
    main()
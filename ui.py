"""
ui.py

The Streamlit Frontend for the Incident RCA Agent.
Provides a minimalist, enterprise-grade interface for multi-file log ingestion, 
streaming human-in-the-loop RCA revision, and Jira ticket export.
"""

import streamlit as st
import pandas as pd
import logging
import rca_agent
print(f"LOADING RCA_AGENT FROM: {rca_agent.__file__}")
import jira_skill

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- PAGE CONFIGURATION & STYLING ---
st.set_page_config(page_title="Incident RCA Agent", layout="centered")

# Inject custom CSS for a stark, professional, single-color theme
st.markdown("""
<style>
    /* Base Typography */
    h1, h2, h3 { color: #0F172A; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.5rem; }
    p, span, label, .stMarkdown { color: #334155; font-size: 14px; }
    
    /* Single Accent Color: #2563EB (Corporate Blue) */
    .stButton>button[kind="primary"] {
        background-color: #2563EB; color: #FFFFFF; border: 1px solid #2563EB; font-weight: 500; border-radius: 4px;
    }
    .stButton>button[kind="primary"]:hover { background-color: #1D4ED8; border-color: #1D4ED8; }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] { background-color: #F8FAFC; border-right: 1px solid #E2E8F0; }
    [data-testid="stSidebar"] h2 { font-size: 16px; color: #0F172A; }
    
    /* Minimalist Status Box */
    .status-approved {
        padding: 12px 16px; background-color: #F8FAFC; border-left: 3px solid #2563EB; 
        color: #0F172A; font-size: 14px; margin-bottom: 24px; border-radius: 2px;
    }

    /* Layout Adjustments */
    .block-container { padding-top: 2rem; max-width: 900px; }
    [data-testid="stFileUploader"] { padding: 16px; border: 1px dashed #CBD5E1; border-radius: 4px; background: #FAFAFA; }
    hr { border-color: #E2E8F0; margin: 2rem 0; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE MANAGEMENT ---
def reset_session() -> None:
    """
    Resets all application state to default values.
    Clears the file uploader widget state to ensure a complete reset.
    """
    keys_to_clear = ['status', 'logs', 'rca_report', 'jira_df', 'log_uploader']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

# Initialize default state variables if they don't exist
if 'status' not in st.session_state: st.session_state.status = 'idle'
if 'logs' not in st.session_state: st.session_state.logs = ""
if 'rca_report' not in st.session_state: st.session_state.rca_report = ""
if 'jira_df' not in st.session_state: st.session_state.jira_df = None

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("Session Controls")
    st.caption("Manage your current analysis state.")
    if st.button("Clear Session :material/delete:", use_container_width=True):
        reset_session()
        st.rerun()

# --- HEADER ---
st.header("Incident RCA Agent")
st.caption("Automated root cause analysis and structured ticket generation.")
st.divider()

# --- STEP 1: MULTI-FILE LOG INGESTION ---
st.subheader("1. Ingest Logs")
uploaded_files = st.file_uploader(
    "Upload system log files (.txt)", 
    type=["txt"], 
    accept_multiple_files=True, 
    label_visibility="collapsed",
    key="log_uploader" # Explicit key allows us to clear it from session state
)

if uploaded_files:
    combined_logs = ""
    for file in uploaded_files:
        file_content = file.read().decode("utf-8")
        combined_logs += f"\n\n--- LOG FILE: {file.name} ---\n\n{file_content}"
        
    # Update state only if the combined logs have changed
    if combined_logs != st.session_state.logs:
        st.session_state.logs = combined_logs
        st.session_state.status = 'uploaded'
        st.session_state.rca_report = ""
        st.session_state.jira_df = None
        st.rerun()

# --- STEP 2: INITIAL ANALYSIS (STREAMING) ---
if st.session_state.status == 'uploaded':
    # Token Limit Warning
    if len(st.session_state.logs) > 100000:
        st.warning("Input logs exceed 100,000 characters. Some context might be truncated by the AI model's context window.")

    if st.button("Generate RCA Report", type="primary", use_container_width=True):
        try:
            response_generator = rca_agent.analyze_incident(st.session_state.logs)
            with st.spinner("Connecting to AI service..."):
                full_report = st.write_stream(response_generator)
            st.session_state.rca_report = full_report
            st.session_state.status = 'generated'
            st.rerun()
        except rca_agent.APICallFailedError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Analysis failed: {str(e)}")

# --- STEP 3: REVIEW & HUMAN-IN-THE-LOOP ---
if st.session_state.status in ['generated', 'revision', 'approved', 'jira']:
    st.subheader("2. Analysis Output")
    
    with st.container(border=True):
        st.markdown(st.session_state.rca_report)
    st.divider()

    # Check if Action Items were successfully generated in the report.
    # Since we forced compact JSON, we can just check for the opening bracket and brace.
    # This is much faster and prevents false positives from markdown wrappers.
    has_action_items = "[{" in st.session_state.rca_report

    # Action Buttons (Only show if not yet approved)
    if st.session_state.status in ['generated', 'revision']:

        # --- FALLBACK: Missing Action Items ---
        if not has_action_items:
            st.error("**Action Items Missing:** The AI failed to generate the structured JSON action items (likely due to output truncation). You can regenerate just the action items without re-running the full report.")
            if st.button("Regenerate Action Items Only", type="primary", use_container_width=True):
                with st.spinner("Generating action items..."):
                    try:
                        import time
                        time.sleep(2) # Throttle for free tier RPM limits
                        
                        # Isolate the narrative to prevent feeding old JSON back to the LLM
                        narrative_part = st.session_state.rca_report.split("## Action Items")[0].strip()
                        
                        action_items_text = rca_agent.regenerate_action_items(narrative_part)
                        
                        # Rebuild the report with the fresh Action Items (prevents duplication)
                        st.session_state.rca_report = f"{narrative_part}\n\n## Action Items\n{action_items_text}"
                        st.rerun()
                    except rca_agent.APICallFailedError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Failed to generate action items: {str(e)}")

        # --- NORMAL FLOW: Action Items Exist ---
        else:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Approve Report", use_container_width=True):
                    st.session_state.status = 'approved'
                    st.rerun()
            with col2:
                if st.button("Request Revision", use_container_width=True):
                    st.session_state.status = 'revision'
                    st.rerun()

    # Revision Flow (Streaming)
    if st.session_state.status == 'revision':
        st.markdown("#### Revision Cycle")
        with st.form("revision_form"):
            feedback = st.text_area("Provide specific feedback for the LLM to refine the report.")
            submitted = st.form_submit_button("Submit Revision", type="primary", use_container_width=True)
            
            if submitted:
                if not feedback.strip():
                    st.warning("Feedback cannot be empty.")
                else:
                    try:
                        response_generator = rca_agent.analyze_incident(st.session_state.logs, feedback)
                        with st.spinner("Applying revisions..."):
                            revised_report = st.write_stream(response_generator)
                        st.session_state.rca_report = revised_report
                        st.session_state.status = 'generated'
                        st.rerun()
                    except rca_agent.APICallFailedError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Revision failed: {str(e)}")

# --- STEP 4: APPROVAL & JIRA EXPORT ---
if st.session_state.status in ['approved', 'jira']:
    st.subheader("3. Export Action Items")
    
    st.markdown(
        '<div class="status-approved">Report approved. The action items are ready to be structured for Jira.</div>', 
        unsafe_allow_html=True
    )
    
    if st.session_state.status == 'approved':
        if st.button("Generate Jira Tickets", type="primary", use_container_width=True):
            with st.spinner("Parsing action items..."):
                try:
                    df = jira_skill.generate_jira_tickets(st.session_state.rca_report)
                    st.session_state.jira_df = df
                    st.session_state.status = 'jira'
                    st.rerun()
                except Exception as e:
                    st.error(f"Jira generation failed: {str(e)}")

# --- STEP 5: DATAFRAME & DOWNLOAD ---
if st.session_state.status == 'jira' and st.session_state.jira_df is not None:
    st.markdown("#### Generated Tickets")
    
    if st.session_state.jira_df.empty:
        st.warning("No valid JSON action items were found in the approved report.")
    else:
        st.dataframe(st.session_state.jira_df, use_container_width=True, hide_index=True)
        
        # Prepare CSV for download
        csv_data = st.session_state.jira_df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="Download jira_tickets.csv :material/download:",
            data=csv_data,
            file_name="jira_tickets.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )

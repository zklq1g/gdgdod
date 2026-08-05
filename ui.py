"""
ui.py

The Streamlit Frontend for the Incident RCA Agent.
Provides a minimalist, enterprise-grade interface for log ingestion, 
human-in-the-loop RCA revision, and Jira ticket export.
"""

import streamlit as st
import pandas as pd
import logging
import rca_agent
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
        background-color: #2563EB;
        color: #FFFFFF;
        border: 1px solid #2563EB;
        font-weight: 500;
        border-radius: 4px;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #1D4ED8;
        border-color: #1D4ED8;
    }
    
    /* Minimalist Status Box */
    .status-approved {
        padding: 12px 16px;
        background-color: #F8FAFC;
        border-left: 3px solid #2563EB;
        color: #0F172A;
        font-size: 14px;
        margin-bottom: 24px;
        border-radius: 2px;
    }

    /* Layout Adjustments */
    .block-container { padding-top: 2rem; max-width: 900px; }
    [data-testid="stFileUploader"] { 
        padding: 16px; 
        border: 1px dashed #CBD5E1; 
        border-radius: 4px; 
        background: #FAFAFA; 
    }
    hr { border-color: #E2E8F0; margin: 2rem 0; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
# State machine: 'idle' -> 'uploaded' -> 'generated' <-> 'revision' -> 'approved' -> 'jira'
if 'status' not in st.session_state:
    st.session_state.status = 'idle'
if 'logs' not in st.session_state:
    st.session_state.logs = ""
if 'rca_report' not in st.session_state:
    st.session_state.rca_report = ""
if 'jira_df' not in st.session_state:
    st.session_state.jira_df = None

# --- HEADER ---
st.header("Incident RCA Agent")
st.caption("Automated root cause analysis and structured ticket generation.")
st.divider()

# --- STEP 1: LOG INGESTION ---
st.subheader("1. Ingest Logs")
uploaded_file = st.file_uploader("Upload system log file (.txt)", type=["txt"], label_visibility="collapsed")

if uploaded_file is not None:
    file_contents = uploaded_file.read().decode("utf-8")
    # Update state only if a new file is uploaded
    if file_contents != st.session_state.logs:
        st.session_state.logs = file_contents
        st.session_state.status = 'uploaded'
        st.session_state.rca_report = ""
        st.session_state.jira_df = None
        st.rerun()

# --- STEP 2: INITIAL ANALYSIS ---
if st.session_state.status == 'uploaded':
    if st.button("Generate RCA Report", type="primary", use_container_width=True):
        with st.spinner("Analyzing logs and generating report..."):
            try:
                report = rca_agent.analyze_incident(st.session_state.logs)
                st.session_state.rca_report = report
                st.session_state.status = 'generated'
                st.rerun()
            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")

# --- STEP 3: REVIEW & HUMAN-IN-THE-LOOP ---
if st.session_state.status in ['generated', 'revision', 'approved', 'jira']:
    st.subheader("2. Analysis Output")
    
    # Display the report in a clean container
    with st.container(border=True):
        st.markdown(st.session_state.rca_report)
    
    st.divider()

    # Action Buttons (Only show if not yet approved)
    if st.session_state.status in ['generated', 'revision']:
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Approve Report", use_container_width=True):
                st.session_state.status = 'approved'
                st.rerun()
                
        with col2:
            if st.button("Request Revision", use_container_width=True):
                st.session_state.status = 'revision'
                st.rerun()

    # Revision Flow
    if st.session_state.status == 'revision':
        st.markdown("#### Revision Cycle")
        with st.form("revision_form"):
            feedback = st.text_area(
                "Provide specific feedback for the LLM to refine the report.",
                placeholder="e.g., The timeline is accurate, but please add an action item to increase the DB connection pool size."
            )
            submitted = st.form_submit_button("Submit Revision", type="primary", use_container_width=True)
            
            if submitted:
                if not feedback.strip():
                    st.warning("Feedback cannot be empty.")
                else:
                    with st.spinner("Regenerating report based on feedback..."):
                        try:
                            revised_report = rca_agent.analyze_incident(st.session_state.logs, feedback)
                            st.session_state.rca_report = revised_report
                            st.session_state.status = 'generated'
                            st.rerun()
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
            with st.spinner("Parsing action items and generating tickets..."):
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

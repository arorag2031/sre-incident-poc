import streamlit as st

from auth import authenticate
from display_flag import is_display_allowed
from event_listener import clear_incidents, list_incidents, start_listener
from llm import complete, groq_ready

st.set_page_config(
    page_title="SRE Incident Copilot",
    layout="wide",
    initial_sidebar_state="collapsed",
)
start_listener()

st.markdown(
    """
    <style>
      [data-testid="stSidebar"] { display: none; }
      [data-testid="collapsedControl"] { display: none; }
      .block-container { padding-top: 1.1rem; padding-bottom: 7.5rem; max-width: 100%; }
      .incident-card {
        border: 1px solid #243656; border-radius: 12px; padding: 10px 12px; margin-bottom: 8px;
        background: #111a2e;
      }
      .incident-card.active { border-color: #38bdf8; box-shadow: 0 0 0 1px #38bdf8 inset; }
      .muted { color: #9db0d0; font-size: 0.85rem; }
      .panel-title { font-size: 1.05rem; font-weight: 700; margin-bottom: 0.25rem; }
      [data-testid="stBottom"] {
        background: #0b1220;
        border-top: 1px solid #243656;
        z-index: 100;
      }
      @media (min-width: 768px) {
        [data-testid="stBottom"] { padding-left: min(22%, 280px); }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def login_screen() -> None:
    left, center, right = st.columns([1, 2, 1])
    with center:
        st.title("SRE Incident Copilot")
        st.caption("Local proof of concept — email/password gate, no external identity provider.")
        with st.form("login"):
            email = st.text_input("Email", value="sre@local.dev")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
            if submitted:
                user = authenticate(email, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
        st.info("Demo accounts: `sre@local.dev` / `ChangeMe123!`  ·  `demo@local.dev` / `demo123`")


def ensure_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("incident", None)
    st.session_state.setdefault("fresh", False)


def open_fresh_chat() -> None:
    st.session_state.incident = None
    st.session_state.fresh = True
    st.session_state.messages = []


def select_incident(incident: dict) -> None:
    st.session_state.incident = incident
    st.session_state.fresh = False
    prompt = (
        f"Analyze incident on service {incident['serviceName']} "
        f"(trace {incident['traceId']}, type {incident['errorType']}). "
        f"Short message: {incident['message']}"
    )
    st.session_state.messages = [{"role": "user", "content": prompt}]
    answer = complete(st.session_state.messages, incident)
    st.session_state.messages.append({"role": "assistant", "content": answer})


@st.dialog("Create Jira Ticket")
def jira_dialog(incident: dict) -> None:
    st.subheader("Simulation only")
    st.write(
        "This popup is a production stub. In a later phase it would call Jira "
        "(project, issue type, labels, and assignee) using the fields below."
    )
    st.text_input("Project", value="SRE", disabled=True)
    st.text_input(
        "Summary",
        value=f"[{incident['serviceName']}] {incident['errorType']} · {incident['shortTrace']}",
        disabled=True,
    )
    st.text_area(
        "Description",
        value=incident.get("message") or "",
        disabled=True,
        height=100,
    )
    st.info("No Jira API is connected in this POC.")
    if st.button("Close", use_container_width=True):
        st.rerun()


@st.dialog("Automate Hotfix Deployment")
def hotfix_dialog(incident: dict) -> None:
    st.subheader("Simulation only")
    st.write(
        "This popup is a production stub. Later it would open a gated pipeline "
        "(change ticket, canary, rollback plan) for the failing service."
    )
    st.text_input("Target service", value=incident["serviceName"], disabled=True)
    st.text_input("Trace", value=incident["traceId"], disabled=True)
    st.selectbox("Pipeline", ["hotfix-canary", "rollback", "feature-flag-off"], disabled=True)
    st.warning("No CI/CD backend is connected in this POC.")
    if st.button("Close", use_container_width=True):
        st.rerun()


def render_left_panel() -> None:
    st.markdown('<div class="panel-title">Live incidents</div>', unsafe_allow_html=True)
    st.caption("Newest first · Redis topic `system-failures`")
    if st.button("➕ Open Fresh Chat", use_container_width=True, type="primary", key="fresh_chat"):
        open_fresh_chat()
        st.rerun()
    if st.button("Clear all", use_container_width=True, key="clear_all"):
        clear_incidents()
        open_fresh_chat()
        st.rerun()

    incidents = list_incidents()
    if not incidents:
        st.markdown(
            '<p class="muted">No failures yet. Open a crash URL on port 8080, then click Refresh list.</p>',
            unsafe_allow_html=True,
        )
        return
    selected_id = (st.session_state.get("incident") or {}).get("id")
    for index, incident in enumerate(incidents):
        active = incident["id"] == selected_id
        st.markdown(
            f"""<div class="incident-card {'active' if active else ''}">
            <strong>{incident['serviceName']}</strong><br/>
            <span class="muted">{incident['errorType']} · {incident['shortTrace']}</span>
            </div>""",
            unsafe_allow_html=True,
        )
        if st.button("Open", key=f"open-{index}-{incident['shortTrace']}", use_container_width=True):
            select_incident(incident)
            st.rerun()


def render_main() -> None:
    incident = st.session_state.get("incident")
    if incident:
        st.title("Incident workspace")
        st.caption(
            f"{incident['serviceName']} · {incident['errorType']} · trace `{incident['traceId']}`"
        )
        action_a, action_b, _ = st.columns([1.2, 1.4, 1.4])
        with action_a:
            if st.button("Create Jira Ticket", use_container_width=True, key="jira_stub"):
                jira_dialog(incident)
        with action_b:
            if st.button("Automate Hotfix Deployment", use_container_width=True, key="hotfix_stub"):
                hotfix_dialog(incident)
        with st.expander("Matched JSON logs", expanded=False):
            logs = incident.get("logs") or []
            if not logs:
                st.write("No log lines matched this traceId yet. Wait a second and click Open again.")
            else:
                st.code("\n\n".join(logs), language="json")
    else:
        st.title("Fresh troubleshooting chat")
        st.caption("No incident context. Ask anything the way you would in ChatGPT.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_chat_input() -> None:
    if prompt := st.chat_input("Ask a follow-up, or describe a symptom…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        answer = complete(st.session_state.messages, st.session_state.get("incident"))
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()


def render_maintenance() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stSidebar"] { display: none; }
          [data-testid="collapsedControl"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([1, 2, 1])
    with center:
        st.title("Under Maintenance")
        st.markdown(
            "The SRE Incident Copilot is temporarily offline. "
            "Microservice log events are **not** being processed."
        )
        st.info("Set `ALLOW_Display=True` in `.env` to restore the site. This page refreshes every 2 seconds.")


@st.fragment(run_every=2)
def watch_display_flag() -> None:
    allowed = is_display_allowed()
    previous = st.session_state.get("_display_allowed")
    if previous is not None and previous != allowed:
        st.session_state._display_allowed = allowed
        st.rerun()
    st.session_state._display_allowed = allowed


def main() -> None:
    watch_display_flag()
    if not is_display_allowed():
        render_maintenance()
        return
    if "user" not in st.session_state:
        login_screen()
        return
    ensure_state()
    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.caption(
            f"Signed in as {st.session_state.user['name']} · "
            + ("LLM: Groq" if groq_ready() else "LLM: local mock — save `.env` (GROQ_API_KEY) then Refresh")
        )
    with top_right:
        if st.button("Refresh list", use_container_width=True, key="refresh_top"):
            st.rerun()
    left, right = st.columns([1, 4], gap="large")
    with left:
        render_left_panel()
        if st.button("Sign out", key="sign_out"):
            st.session_state.clear()
            st.rerun()
    with right:
        render_main()
    handle_chat_input()


main()

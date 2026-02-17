import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import streamlit as st
from agent import (
    agent_answer,
    open_work_handler,
    text_to_sql_handler,
    get_daily_suggestions,
    Tool,
    register_tool
)
from database import db_query

# ---------------------------------------------------------------------------
# Brand constants
# ---------------------------------------------------------------------------
AEL_NAVY = "#002B5C"
AEL_DARK = "#001F42"
AEL_LIGHT_BG = "#F0F4F8"
AEL_GOLD = "#C8A951"
AEL_WHITE = "#FFFFFF"
LOGO_PATH = "assets/logo.jpg"

AEL_CSS = f"""
<style>
/* ---------- global overrides ---------- */
html, body, [class*="css"] {{
    font-family: Georgia, 'Times New Roman', serif;
}}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {{
    background-color: {AEL_NAVY};
}}
section[data-testid="stSidebar"] * {{
    color: {AEL_WHITE} !important;
}}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSelectbox svg {{
    color: {AEL_WHITE} !important;
}}
section[data-testid="stSidebar"] .stSelectbox > div > div {{
    background-color: {AEL_DARK};
    border-color: {AEL_GOLD};
    color: {AEL_WHITE};
}}
section[data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,0.2);
}}

/* ---------- header bar ---------- */
header[data-testid="stHeader"] {{
    background-color: {AEL_NAVY};
}}

/* ---------- suggestion cards ---------- */
div[data-testid="stAlert"] {{
    background-color: {AEL_LIGHT_BG};
    border-left-color: {AEL_NAVY};
    color: #1A1A2E;
}}

/* ---------- buttons ---------- */
.stButton > button {{
    background-color: {AEL_NAVY};
    color: {AEL_WHITE};
    border: none;
    border-radius: 4px;
    padding: 0.4rem 1.2rem;
    font-family: Georgia, 'Times New Roman', serif;
}}
.stButton > button:hover {{
    background-color: {AEL_DARK};
    color: {AEL_GOLD};
}}

/* ---------- chat input ---------- */
div[data-testid="stChatInput"] textarea {{
    border-color: {AEL_NAVY} !important;
}}
div[data-testid="stChatInput"] button {{
    color: {AEL_NAVY} !important;
}}

/* ---------- gold accent on subheaders ---------- */
.ae-subheader {{
    color: {AEL_NAVY};
    border-bottom: 3px solid {AEL_GOLD};
    padding-bottom: 4px;
    margin-bottom: 12px;
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 1.25rem;
    font-weight: 700;
}}
</style>
"""


def get_sales_agents() -> list:
    """Fetch list of unique sales agents from the database"""
    try:
        df = db_query("SELECT DISTINCT sales_agent FROM sales_teams ORDER BY sales_agent")
        return df['sales_agent'].tolist()
    except:
        return ["Unknown"]


# Register the text_to_sql tool
register_tool(Tool(
    name="text_to_sql",
    description="Generate and execute SQL queries from natural language questions about the sales database. Use this for flexible, ad-hoc queries about accounts, deals, interactions, products, and sales teams.",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The natural language question to convert to SQL."
            }
        },
        "required": ["question"]
    },
    handler=text_to_sql_handler
))

# Register the open_work tool
register_tool(Tool(
    name="open_work",
    description="Get a list of outstanding work items and tasks that need attention. This shows deals in 'Engaging' stage from the last 30 days. Use this for questions about 'what to work on', 'outstanding items', 'tasks today', or 'open work'.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to return (default: 25)"
            },
            "sales_agent": {
                "type": "string",
                "description": "Optional: filter by sales agent name"
            }
        }
    },
    handler=open_work_handler
))


# ---------------------------------------------------------------------------
# Page config & branding
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="American Equity - Sales Assistant",
    page_icon=LOGO_PATH,
    layout="centered",
)
st.markdown(AEL_CSS, unsafe_allow_html=True)

# Logo + title
st.image(LOGO_PATH, width=280)
st.caption("Sales Data Assistant")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### Welcome")

    agents = get_sales_agents()

    if "current_user" not in st.session_state:
        st.session_state.current_user = agents[0] if agents else "Unknown"

    selected_agent = st.selectbox(
        "Acting as:",
        options=agents,
        index=agents.index(st.session_state.current_user)
        if st.session_state.current_user in agents
        else 0,
    )

    st.session_state.current_user = selected_agent
    st.markdown(f"Logged in as **{selected_agent}**")

    st.divider()

    st.markdown("#### How it works")
    st.markdown(
        "1. Ask a question in plain English\n"
        "2. AI chooses the right tool(s)\n"
        "3. Query executes with your context\n"
        "4. Results displayed in chat"
    )

    st.divider()
    st.markdown("**Tables available**")
    st.code("accounts, interactions, products,\nsales_pipeline, sales_teams")


# ---------------------------------------------------------------------------
# Daily Suggestions
# ---------------------------------------------------------------------------
def load_suggestions():
    """Fetch fresh suggestions for the current user."""
    user = st.session_state.get("current_user", "Unknown")
    st.session_state.daily_suggestions = get_daily_suggestions(user)
    st.session_state.suggestions_user = user


# Regenerate when user changes or first load
if (
    "daily_suggestions" not in st.session_state
    or st.session_state.get("suggestions_user") != st.session_state.current_user
):
    with st.spinner("Generating today's suggestions..."):
        load_suggestions()

st.markdown('<div class="ae-subheader">Today\'s Focus</div>', unsafe_allow_html=True)
st.caption("Proposed Feature — AI-generated suggestions based on your pipeline data")
suggestion_cols = st.columns(3)
for idx, col in enumerate(suggestion_cols):
    with col:
        s = st.session_state.daily_suggestions[idx]
        rationale = s.get("rationale", "")
        actions = s.get("actions", [])
        bullets = "\n".join(f"- {a}" for a in actions)
        st.info(f"**{s['title']}**\n\n{rationale}\n\n{bullets}")

if st.button("Refresh Suggestions"):
    with st.spinner("Generating new suggestions..."):
        load_suggestions()
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hi! Ask me anything about your sales data. "
            "I'll search the database to answer your questions.",
        }
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_question = st.chat_input("Ask a question about your sales data...")
if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = agent_answer(user_question)
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

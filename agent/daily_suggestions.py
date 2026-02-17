from openai import OpenAI
from database import db_query


def _get_user_snapshot(sales_agent: str) -> str:
    """Query the database for a summary of the user's accounts, pipeline, and interactions."""

    # 1. Pipeline overview: deals by stage
    pipeline_df = db_query(f"""
        SELECT deal_stage, product, account, close_value,
               TRY_CAST(close_date AS DATE) AS close_date,
               TRY_CAST(engage_date AS DATE) AS engage_date
        FROM sales_pipeline
        WHERE LOWER(sales_agent) = LOWER('{sales_agent}')
        ORDER BY deal_stage, close_date
    """)

    # 2. Accounts with last touch date
    accounts_df = db_query(f"""
        SELECT DISTINCT a.account, a.sector, a.revenue, a.employees,
               lt.last_touch
        FROM accounts a
        JOIN sales_pipeline sp ON a.account_id = sp.account_id
        LEFT JOIN v_last_touch lt ON a.account_id = lt.account_id
        WHERE LOWER(sp.sales_agent) = LOWER('{sales_agent}')
        ORDER BY lt.last_touch ASC NULLS FIRST
    """)

    # 3. Recent interactions (last 14 days)
    interactions_df = db_query(f"""
        SELECT a.account, i.activity_type, LOWER(i.status) AS status,
               CAST(TRY_CAST(i.timestamp AS TIMESTAMP) AS DATE) AS interaction_date,
               i.comment
        FROM interactions i
        JOIN accounts a ON i.account_id = a.account_id
        JOIN sales_pipeline sp ON a.account_id = sp.account_id
        WHERE LOWER(sp.sales_agent) = LOWER('{sales_agent}')
          AND TRY_CAST(i.timestamp AS TIMESTAMP) >= CURRENT_DATE - 14
        ORDER BY TRY_CAST(i.timestamp AS TIMESTAMP) DESC
        LIMIT 20
    """)

    # 4. Open work items
    open_work_df = db_query(f"""
        SELECT account_name_from_pipeline AS account, deal_stage, product,
               activity_type, status_lc, d_interaction AS last_activity
        FROM v_open_work
        WHERE LOWER(sales_agent) = LOWER('{sales_agent}')
        ORDER BY d_interaction DESC NULLS LAST
    """)

    sections = []
    sections.append(f"=== Pipeline ({len(pipeline_df)} deals) ===")
    if not pipeline_df.empty:
        sections.append(pipeline_df.to_string(index=False))

    sections.append(f"\n=== Accounts ({len(accounts_df)}) ===")
    if not accounts_df.empty:
        sections.append(accounts_df.to_string(index=False))

    sections.append(f"\n=== Recent Interactions (last 14 days, up to 20) ===")
    if not interactions_df.empty:
        sections.append(interactions_df.to_string(index=False))
    else:
        sections.append("No recent interactions found.")

    sections.append(f"\n=== Open Work Items ({len(open_work_df)}) ===")
    if not open_work_df.empty:
        sections.append(open_work_df.to_string(index=False))
    else:
        sections.append("No open work items.")

    return "\n".join(sections)


def get_daily_suggestions(sales_agent: str) -> list[dict]:
    """
    Analyze the user's accounts and pipeline data, then use OpenAI
    to generate 3 actionable suggestions for the day.

    Returns a list of 3 dicts, each with:
        - "title": high-level description
        - "rationale": why this matters (1 sentence)
        - "actions": list of 2 specific action strings
    """
    snapshot = _get_user_snapshot(sales_agent)

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a sales coach. Given a sales rep's current pipeline, "
                    "accounts, recent interactions, and open work items, suggest "
                    "exactly 3 things they should focus on today. "
                    "Each suggestion should reference a real account or deal from the data. "
                    "For each suggestion provide:\n"
                    "- A high-level title (1 short sentence)\n"
                    "- A rationale explaining why this matters (1 sentence)\n"
                    "- Exactly 2 specific actions they can take\n\n"
                    "Return ONLY a JSON array of 3 objects, no other text. "
                    'Each object must have "title" (string), "rationale" (string), '
                    'and "actions" (array of 2 strings).\n\n'
                    "Example format:\n"
                    '[{"title": "Follow up with Acme Corp", '
                    '"rationale": "They had a demo last week but no follow-up yet.", '
                    '"actions": ["Send a check-in email to the buyer", '
                    '"Schedule a demo for their new product interest"]}]'
                ),
            },
            {
                "role": "user",
                "content": f"Here is the data for {sales_agent}:\n\n{snapshot}",
            },
        ],
        temperature=0.7,
    )

    import json

    raw = response.choices[0].message.content.strip()
    # Handle markdown-wrapped JSON
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])
    raw = raw.strip()

    fallback = {
        "title": "Review your open pipeline deals",
        "rationale": "Keeping your pipeline fresh ensures no opportunities slip through.",
        "actions": ["Check for stale deals that need follow-up",
                     "Prioritize deals closest to closing"],
    }

    try:
        suggestions = json.loads(raw)
        if isinstance(suggestions, list) and len(suggestions) >= 3:
            result = []
            for s in suggestions[:3]:
                if isinstance(s, dict) and "title" in s and "actions" in s:
                    result.append({
                        "title": s["title"],
                        "rationale": s.get("rationale", ""),
                        "actions": list(s["actions"])[:2],
                    })
                else:
                    result.append(fallback)
            return result
    except json.JSONDecodeError:
        pass

    return [fallback] * 3

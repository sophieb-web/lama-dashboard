import json
import os

LAMA_THESIS = """
Lama Partners is a pre-seed and seed Israeli cybersecurity VC fund. GPs: Gil Zimmermann and Ron Zalkind
(previously built and sold CloudLock to Cisco). Investment thesis — "The Outcomes Playbook":
- Back high-agency founders building AI-native companies that replace enterprise labor
- The shift is from selling tools → delivering outcomes (work that gets done)
- Portfolio: Terra (agentic pentesting), Orion Security (AI-native DLP), Root (autonomous CVE patching),
  Capsule (runtime AI agent security), Jit (DevSecOps automation, acquired by Torq)
- Infrastructure plays that enable safe agentic adoption
- Target buyer: CISO + CIO + CTO + Chief AI Transformation Officer
"""

SYSTEM_PROMPT = """You are a VC research analyst at Lama Partners, an Israeli cybersecurity seed fund.
You have access to a database of 331 Israeli cyber companies and 485 funding deals.
Answer questions precisely using the data provided.
When relevant, flag companies that align with Lama's Outcomes Playbook thesis:
AI-native companies that replace enterprise security labor.
Format answers with markdown tables where appropriate.
If data is missing, say so. Always cite which companies or deals you're drawing from.

Lama Partners thesis context:
""" + LAMA_THESIS


def query(question, companies_json, context_text):
    try:
        import anthropic
    except ImportError:
        return "Anthropic SDK not installed. Run: pip install anthropic"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "ANTHROPIC_API_KEY environment variable not set."

    client = anthropic.Anthropic(api_key=api_key)

    companies_str = json.dumps(companies_json, indent=None)
    if len(companies_str) > 80000:
        companies_str = companies_str[:80000] + "\n... (truncated)"

    user_content = f"""DATABASE (331 Israeli cyber companies):
{companies_str}

CONTEXT FILES:
{context_text[:20000]}

QUESTION: {question}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text

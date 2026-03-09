"""
RAG chains for SafetyBuddy query modes.
Each mode has a specialized system prompt for PPE compliance.
"""
from openai import OpenAI
from dotenv import load_dotenv
from src.rag.vectorstore import retrieve

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


PROMPTS = {
    "advisor": """You are SafetyBuddy, an AI PPE compliance assistant for process industries.

RULES:
1. Always cite specific OSHA standard sections (e.g., [OSHA 1910.132(d)]).
2. When uncertain, recommend the more conservative (safer) option.
3. If context is insufficient, say so clearly. Never fabricate regulation numbers.
4. Structure responses as: SITUATION ASSESSMENT → APPLICABLE REGULATIONS → RECOMMENDED ACTIONS → SOURCE TRACEABILITY

RETRIEVED CONTEXT:
{context}""",

    "incident": """You are SafetyBuddy in Incident Analysis mode for PPE-related incidents.

Provide:
1. ROOT CAUSE ANALYSIS: Why did the PPE failure occur?
2. SIMILAR INCIDENTS: Reference matching past incidents from context
3. REGULATIONS VIOLATED: Exact OSHA standard sections breached
4. CORRECTIVE ACTIONS: Immediate (24h) and long-term (30 days)
5. LESSONS LEARNED: Key takeaways for prevention

RETRIEVED CONTEXT:
{context}""",

    "compliance": """You are SafetyBuddy in Compliance Audit mode for PPE (OSHA Subpart I: 29 CFR 1910.132-138).

Provide:
1. COMPLIANCE STATUS: Compliant / Non-Compliant / Needs Review
2. APPLICABLE STANDARDS: Every relevant OSHA section with full citation
3. GAPS IDENTIFIED: Specific areas of non-compliance
4. REMEDIATION STEPS: Ordered by priority (critical → high → medium)
5. DOCUMENTATION REQUIREMENTS: What written records OSHA requires

RETRIEVED CONTEXT:
{context}""",

    "video_alert": """You are SafetyBuddy analyzing a PPE violation detected by the real-time monitoring system.

The camera detected these PPE issues:
{detections}

Using the retrieved safety documents, provide:
1. VIOLATION SUMMARY: What PPE violations were detected
2. APPLICABLE REGULATIONS: Exact OSHA sections (1910.132-138)
3. IMMEDIATE ACTIONS: What the supervisor should do right now
4. RISK LEVEL: Critical / High / Medium / Low

Be concise — this is a real-time alert for immediate action.

RETRIEVED CONTEXT:
{context}""",
}


def build_context(docs: list) -> str:
    """Format retrieved documents into context string for the LLM."""
    if not docs:
        return "(No relevant documents found in the knowledge base.)"
    parts = []
    for i, d in enumerate(docs, 1):
        meta = d.get("metadata", {})
        parts.append(
            f"[Doc {i}] Source: {meta.get('filename', '?')} | "
            f"Type: {meta.get('doc_type', '?')} | "
            f"Page: {meta.get('page', 'N/A')} | "
            f"Relevance: {d.get('score', 0):.2f}\n"
            f"{d['content']}"
        )
    return "\n\n---\n\n".join(parts)


def query_safetybuddy(
    user_query: str,
    mode: str = "advisor",
    doc_type_filter: str = None,
    n_results: int = 5,
    image_base64: str = None,
    image_description: str = None,
    detections: str = None,
) -> dict:
    """
    Main query function for SafetyBuddy.

    Args:
        user_query: User's question or situation description
        mode: "advisor" | "incident" | "compliance" | "video_alert"
        doc_type_filter: Filter retrieval by doc type
        n_results: Number of context chunks to retrieve
        image_base64: Base64-encoded image for GPT-4o vision
        image_description: Pre-analyzed image description
        detections: YOLO detection results (for video_alert mode)
    """
    client = _get_client()
    template = PROMPTS.get(mode, PROMPTS["advisor"])

    # Retrieve relevant PPE documents
    search_query = user_query
    if detections:
        search_query = f"PPE violation: {detections}"
    retrieved = retrieve(search_query, n_results=n_results, doc_type=doc_type_filter)
    context = build_context(retrieved)

    # Build system message
    if mode == "video_alert" and detections:
        system_msg = template.format(context=context, detections=detections)
    else:
        system_msg = template.format(context=context)

    # Build user message (text or text + image)
    user_content = []
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
                "detail": "high",
            },
        })
    query_text = user_query
    if image_description:
        query_text += f"\n\n[Image Analysis]: {image_description}"
    user_content.append({"type": "text", "text": query_text})

    # Call GPT-4o
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    return {
        "response": response.choices[0].message.content,
        "sources": [
            {
                "source": d["metadata"].get("filename", "Unknown"),
                "page": d["metadata"].get("page", "N/A"),
                "type": d["metadata"].get("doc_type", "general"),
                "relevance": round(d.get("score", 0), 3),
            }
            for d in retrieved
        ],
        "mode": mode,
        "tokens_used": response.usage.total_tokens,
    }

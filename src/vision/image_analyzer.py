"""
GPT-4o vision analysis for PPE compliance on still images.
Used for uploaded inspection photos and violation frame snapshots.
"""
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None

VISION_PROMPT = """You are SafetyBuddy's PPE visual inspector for industrial environments.

Systematically check for ALL of the following:

1. HEAD PROTECTION — Hard hat present? Properly worn? Visible damage?
2. EYE/FACE PROTECTION — Safety glasses/goggles? Side shields? Face shield if needed?
3. HAND PROTECTION — Gloves present? Correct type for task?
4. FOOT PROTECTION — Safety-toe boots? No sneakers/sandals?
5. BODY PROTECTION — High-vis vest if vehicle area? FR clothing if heat/flame?
6. HEARING PROTECTION — Earplugs/earmuffs if noisy area?
7. RESPIRATORY — Respirator/mask if dust, fumes, or vapors visible?
8. ENVIRONMENTAL HAZARDS — Visible hazards requiring PPE? Safety signage?

For each finding:
- State observation clearly
- Rate severity: CRITICAL / HIGH / MEDIUM / LOW
- Cite applicable OSHA standard (1910.132-138)
- Reference location in image (e.g., "worker on the left")

End with OVERALL RISK LEVEL: CRITICAL / HIGH / MODERATE / LOW"""


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def encode_image_file(path: str) -> str:
    """Read and base64-encode an image file."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_image(image_source: str, additional_context: str = "",
                  is_base64: bool = False) -> dict:
    """
    Analyze an image for PPE compliance using GPT-4o vision.

    Args:
        image_source: File path or base64-encoded string
        additional_context: Extra info about the scene
        is_base64: True if image_source is already base64
    """
    client = _get_client()
    b64 = image_source if is_base64 else encode_image_file(image_source)

    user_text = "Analyze this image for PPE compliance. Identify all workers and check their PPE status."
    if additional_context:
        user_text += f"\nContext: {additional_context}"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=1500,
    )

    return {
        "analysis": response.choices[0].message.content,
        "tokens_used": response.usage.total_tokens,
    }

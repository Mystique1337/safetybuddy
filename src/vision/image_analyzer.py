"""
Gemma 4 vision analysis for PPE compliance on still images.
Used for uploaded inspection photos and violation frame snapshots.

Gemma 4 (google/gemma-4-*-it) is natively multimodal and is served by vLLM on
Modal through an OpenAI-compatible API, so the request shape is the familiar
chat-completions call with an ``image_url`` part. See src/llm.py and modal_app.py.
"""
import base64

from src.config import settings
from src.llm import get_llm_client

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


def encode_image_file(path: str) -> str:
    """Read and base64-encode an image file."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_image(image_source: str, additional_context: str = "",
                  is_base64: bool = False) -> dict:
    """
    Analyze an image for PPE compliance using Gemma 4 vision.

    Args:
        image_source: File path or base64-encoded string
        additional_context: Extra info about the scene
        is_base64: True if image_source is already base64
    """
    client = get_llm_client()
    b64 = image_source if is_base64 else encode_image_file(image_source)

    user_text = "Analyze this image for PPE compliance. Identify all workers and check their PPE status."
    if additional_context:
        user_text += f"\nContext: {additional_context}"

    response = client.chat.completions.create(
        model=settings.vision_model,
        messages=[
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=max(settings.max_tokens, 1500),
    )

    usage = getattr(response, "usage", None)
    return {
        "analysis": response.choices[0].message.content,
        "tokens_used": getattr(usage, "total_tokens", 0) if usage else 0,
    }

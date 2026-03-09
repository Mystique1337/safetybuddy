"""
Enriches SafetyBuddy responses with regulatory traceability.
"""
from src.compliance.regulations import identify_applicable_regulations


def enrich_with_compliance(query: str, llm_response: str,
                           image_analysis: str = None) -> dict:
    """Add explicit regulatory traceability to a response."""
    combined = f"{query} {llm_response}"
    if image_analysis:
        combined += f" {image_analysis}"

    regs = identify_applicable_regulations(combined)
    return {
        "applicable_regulations": regs,
        "compliance_summary": _format_summary(regs),
        "traceability_note": (
            "All recommendations are linked to the regulations above. "
            "Verify applicability with your facility's compliance officer."
        ),
    }


def _format_summary(regulations: list) -> str:
    """Format regulation matches into readable markdown."""
    if not regulations:
        return "No specific PPE regulations auto-detected. Manual review recommended."
    lines = ["**Applicable PPE Regulations:**\n"]
    for reg in regulations:
        lines.append(f"**{reg['standard']}** — {reg['title']}")
        for section in reg.get("key_sections", {}).values():
            lines.append(f"  - {section}")
        lines.append(f"  _(Triggered by: {', '.join(reg['matched_keywords'])})_\n")
    return "\n".join(lines)

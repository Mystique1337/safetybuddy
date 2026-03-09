"""
Structured registry of PPE regulations.
Maps hazard keywords to applicable OSHA standards for auto-tagging.
"""

PPE_REGULATION_REGISTRY = {
    "general_ppe": {
        "standard": "OSHA 29 CFR 1910.132",
        "title": "General Requirements for PPE",
        "key_sections": {
            "hazard_assessment": "1910.132(d) - Hazard assessment and PPE selection",
            "certification": "1910.132(d)(2) - Written certification of hazard assessment",
            "defective_ppe": "1910.132(e) - Defective/damaged PPE shall not be used",
            "training": "1910.132(f) - Training requirements",
            "retraining": "1910.132(f)(3) - When retraining is required",
            "documentation": "1910.132(f)(4) - Written training certification",
            "employer_payment": "1910.132(h) - Employer payment for PPE",
        },
    },
    "eye_face": {
        "standard": "OSHA 29 CFR 1910.133",
        "title": "Eye and Face Protection",
        "key_sections": {
            "general": "1910.133(a)(1) - Protection from particles, chemicals, vapors, light",
            "side_protection": "1910.133(a)(2) - Side protection required",
            "filter_lenses": "1910.133(a)(5) - Filter lenses for radiant energy",
        },
    },
    "respiratory": {
        "standard": "OSHA 29 CFR 1910.134",
        "title": "Respiratory Protection",
        "key_sections": {
            "program": "1910.134(c) - Written respiratory protection program",
            "selection": "1910.134(d) - Selection of respirators",
            "medical": "1910.134(e) - Medical evaluation required",
            "fit_testing": "1910.134(f) - Fit testing required",
            "maintenance": "1910.134(h) - Maintenance and care",
            "cartridge_changeout": "1910.134(h)(2)(i) - Cartridge change-out schedules",
        },
    },
    "head": {
        "standard": "OSHA 29 CFR 1910.135",
        "title": "Head Protection",
        "key_sections": {
            "general": "1910.135(a)(1) - Protection from falling/flying objects",
            "ansi": "1910.135(b) - ANSI Z89.1 compliance required",
        },
    },
    "foot": {
        "standard": "OSHA 29 CFR 1910.136",
        "title": "Foot Protection",
        "key_sections": {
            "general": "1910.136(a) - Protection from falling/rolling objects, piercing",
        },
    },
    "hand": {
        "standard": "OSHA 29 CFR 1910.138",
        "title": "Hand Protection",
        "key_sections": {
            "general": "1910.138(a) - Appropriate hand protection selection",
        },
    },
    "hearing": {
        "standard": "OSHA 29 CFR 1910.95",
        "title": "Occupational Noise Exposure",
        "key_sections": {
            "conservation": "1910.95(c) - Hearing conservation program",
            "protectors": "1910.95(i) - Hearing protector requirements",
            "fit_training": "1910.95(i)(4) - Proper fitting and training",
        },
    },
}

PPE_KEYWORDS = {
    "general_ppe": ["PPE", "personal protective", "hazard assessment", "protective equipment"],
    "eye_face": ["safety glasses", "goggles", "face shield", "eye protection",
                 "eye injury", "splash", "welding helmet", "flying particles"],
    "head": ["hard hat", "helmet", "NO-Hardhat", "no hardhat", "head protection",
             "bump cap", "falling object", "head injury"],
    "hand": ["gloves", "hand protection", "cut-resistant", "nitrile",
             "chemical gloves", "leather gloves", "hand injury", "laceration"],
    "foot": ["safety shoes", "safety boots", "safety-toe", "steel toe",
             "foot protection", "metatarsal", "foot injury"],
    "respiratory": ["respirator", "mask", "N95", "SCBA", "cartridge",
                    "NO-Mask", "no mask", "respiratory", "vapor", "fume", "dust"],
    "hearing": ["ear plugs", "earplugs", "ear muffs", "hearing protection",
                "noise", "decibel", "dBA", "hearing loss"],
}


def identify_applicable_regulations(text: str) -> list:
    """Given any text, identify which PPE regulations apply."""
    text_lower = text.lower()
    matches = []
    for category, keywords in PPE_KEYWORDS.items():
        matched = [kw for kw in keywords if kw.lower() in text_lower]
        if matched:
            reg = PPE_REGULATION_REGISTRY[category]
            matches.append({
                "category": category,
                "standard": reg["standard"],
                "title": reg["title"],
                "matched_keywords": matched,
                "key_sections": reg.get("key_sections", {}),
            })
    return matches

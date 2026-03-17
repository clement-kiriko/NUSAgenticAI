INJECTION_PATTERNS = [
    "ignore previous instructions",
    "reveal system prompt",
    "show hidden prompt",
    "call tool",
    "execute tool",
    "system override",
]

def detect_prompt_injection(text: str) -> bool:
    if not text:
        return False

    text_lower = text.lower()
    return any(pattern in text_lower for pattern in INJECTION_PATTERNS)

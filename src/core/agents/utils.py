import chevron
import logging

logger = logging.getLogger(__name__)


def render_prompt(text: str, data: dict) -> str:
    """
    Renders mustache-style {{key}} placeholders in text using chevron.
    Supports nested access like {{user.name}} and {{items.0}}.
    Missing keys are rendered as empty strings (Mustache standard).
    """
    if not text:
        return text

    if not data:
        return text

    try:
        # Standard mustache behavior: missing keys -> empty string
        return chevron.render(text, data)
    except Exception as e:
        logger.error(f"Error rendering prompt template: {e}")
        return text

import re

def render_prompt(text: str, data: dict) -> str:
    """
    Replaces placeholders like {{key}} or {{ key }} in the text with values from data.
    If a key is missing from data, the placeholder is left as is.
    """
    if not text:
        return text
    
    # Matches {{key}} or {{ key }}
    # \w+ matches alphanumeric characters and underscore
    return re.sub(
        r'\{\{\s*(\w+)\s*\}\}', 
        lambda m: str(data.get(m.group(1), m.group(0))), 
        text
    )

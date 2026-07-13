import re
from typing import AsyncGenerator

# Phrases to remove entirely
PHRASES_TO_REMOVE = [
    r"(?i)as an ai(?: language model)?\b,?\s*",
    r"(?i)i am an ai(?: language model)?\b,?\s*",
    r"(?i)i hope this helps!?\s*"
]

# Words to replace to reduce "AI feel" without destroying meaning
WORD_REPLACEMENTS = {
    r"(?i)\bdelve\b": "explore",
    r"(?i)\bleverage\b": "use",
    r"(?i)\brobust\b": "strong",
    r"(?i)\btapestry\b": "collection",
    r"(?i)\btestament\b": "proof",
}

def clean_ai_text(text: str) -> str:
    """
    Applies regex to find and replace known AI tells in a string.
    """
    # Remove complete phrases
    for phrase in PHRASES_TO_REMOVE:
        text = re.sub(phrase, "", text)
    
    # Replace overused words, preserving case
    for pattern, replacement in WORD_REPLACEMENTS.items():
        def match_case(match):
            word = match.group(0)
            if word.istitle():
                return replacement.title()
            elif word.isupper():
                return replacement.upper()
            return replacement
        
        text = re.sub(pattern, match_case, text)
        
    # Reduce excessive em-dashes (e.g., --- or -- becomes a single —)
    text = re.sub(r'[-—]{2,}', '—', text)
    
    return text

def scrub_dict(data: dict) -> dict:
    """
    Recursively applies clean_ai_text to all string values in a dictionary.
    Safe for JSON payloads where we don't want to modify keys.
    """
    if isinstance(data, dict):
        return {k: scrub_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [scrub_dict(item) for item in data]
    elif isinstance(data, str):
        return clean_ai_text(data)
    else:
        return data

class AIScrubberBuffer:
    """
    A stateful buffer that accumulates text chunks and flushes cleaned sentences.
    Useful for integrating into complex stream loops.
    """
    def __init__(self):
        self.buffer = ""
        self.boundary_pattern = re.compile(r'([.!?]\s+|\n+)')

    def process_chunk(self, chunk: str) -> str:
        self.buffer += chunk
        output = ""
        
        match = self.boundary_pattern.search(self.buffer)
        while match:
            split_idx = match.end()
            sentence = self.buffer[:split_idx]
            self.buffer = self.buffer[split_idx:]
            
            cleaned = clean_ai_text(sentence)
            if cleaned:
                output += cleaned
                
            match = self.boundary_pattern.search(self.buffer)
            
        return output
        
    def flush(self) -> str:
        output = ""
        if self.buffer:
            cleaned = clean_ai_text(self.buffer)
            if cleaned:
                output += cleaned
            self.buffer = ""
        return output

async def stream_clean_ai_text(async_gen: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """
    Wraps an async generator (like SSE chunk streams), buffering text until 
    a sentence boundary is reached, scrubbing the buffer, and yielding it.
    This prevents AI phrases split across network chunks from escaping.
    """
    scrubber = AIScrubberBuffer()
    
    async for chunk in async_gen:
        cleaned = scrubber.process_chunk(chunk)
        if cleaned:
            yield cleaned
            
    final_cleaned = scrubber.flush()
    if final_cleaned:
        yield final_cleaned

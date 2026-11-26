from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChunkingConfig:
    """Whitespace chunking configuration matching Gemini File Search settings."""

    max_tokens: int = 512
    overlap_tokens: int = 64

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0.")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be >= 0 and < max_tokens.")

    def to_gemini_payload(self) -> dict[str, Any]:
        """Serialize into Gemini File Search ``chunkingConfig`` JSON."""
        return {
            "whiteSpaceConfig": {
                "maxTokensPerChunk": self.max_tokens,
                "maxOverlapTokens": self.overlap_tokens,
            }
        }


def split_into_chunks(text: str, config: ChunkingConfig) -> list[str]:
    """Split text into overlapping whitespace-delimited chunks."""
    tokens = (text or "").split()
    if not tokens:
        return []

    step = config.max_tokens - config.overlap_tokens
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = start + config.max_tokens
        chunks.append(" ".join(tokens[start:end]))
        if end >= len(tokens):
            break
        start += step
    return chunks


def estimate_chunk_count(text: str, config: ChunkingConfig) -> int:
    """Return the expected number of chunks for a Markdown document."""
    return len(split_into_chunks(text, config))

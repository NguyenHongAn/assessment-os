from __future__ import annotations

import pytest

from src.chunking import ChunkingConfig, estimate_chunk_count, split_into_chunks


def test_tc_c09_chunking_empty_short_and_overlapping() -> None:
    cfg = ChunkingConfig(max_tokens=5, overlap_tokens=2)

    assert split_into_chunks("", cfg) == []
    assert estimate_chunk_count("   \n\t ", cfg) == 0

    assert split_into_chunks("one two three", cfg) == ["one two three"]
    assert estimate_chunk_count("one two three", cfg) == 1

    # 10 tokens with max=5, overlap=2 -> step=3 -> [0:5], [3:8], [6:11]
    text = " ".join(f"w{i}" for i in range(10))
    chunks = split_into_chunks(text, cfg)
    assert chunks == [
        "w0 w1 w2 w3 w4",
        "w3 w4 w5 w6 w7",
        "w6 w7 w8 w9",
    ]
    assert estimate_chunk_count(text, cfg) == 3


def test_tc_c09_chunking_gemini_payload_and_validation() -> None:
    cfg = ChunkingConfig(max_tokens=512, overlap_tokens=64)
    assert cfg.to_gemini_payload() == {
        "whiteSpaceConfig": {
            "maxTokensPerChunk": 512,
            "maxOverlapTokens": 64,
        }
    }

    with pytest.raises(ValueError, match="max_tokens"):
        ChunkingConfig(max_tokens=0, overlap_tokens=0)

    with pytest.raises(ValueError, match="overlap_tokens"):
        ChunkingConfig(max_tokens=100, overlap_tokens=100)

    with pytest.raises(ValueError, match="overlap_tokens"):
        ChunkingConfig(max_tokens=100, overlap_tokens=-1)

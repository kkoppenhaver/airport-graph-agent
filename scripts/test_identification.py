#!/usr/bin/env python3
"""Test script to check runway/taxiway identification without running the full agent."""

import base64
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

IDENTIFICATION_PROMPT = """Analyze this FAA airport diagram and identify the following elements.

## Visual Identification Guide

### Runways
- **Appearance**: Solid BLACK elongated shapes (the darkest elements on the diagram)
- **Labels**: Runway numbers appear as TEXT at each END of the black shape
- **IMPORTANT**: Look for the RUNWAY LEGEND box (usually on the right side) which lists all runways

### Taxiways
- **Appearance**: GREY outlined paths (lighter than runways, not solid black)
- **Labels**: Single letters or letter+number combinations (A, B, C, W, W1, etc.)

### What to IGNORE
- Frequency boxes, elevation numbers, coordinates, dimension text, CLOSED markings

## Your Task

1. First, find and read the RUNWAY LEGEND box. List exactly what it says.
2. Count the solid black runway shapes you can see. Does this match the legend?
3. List each runway with both end numbers (e.g., "02L/20R")
4. List all taxiway letters you can identify
5. List any FBOs or named facilities you can see

Be precise and only report what you can clearly see. Do not guess or hallucinate runways."""


def test_identification(image_path: str, model: str = "claude-sonnet-4-20250514"):
    """Test identification on an airport diagram."""
    path = Path(image_path)
    if not path.exists():
        print(f"Error: File not found: {image_path}")
        sys.exit(1)

    # Read and encode image
    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Determine media type
    suffix = path.suffix.lower()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix.lstrip("."), "image/png"
    )

    print(f"Testing identification on: {image_path}")
    print(f"Using model: {model}")
    print("-" * 60)

    client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": IDENTIFICATION_PROMPT,
                    },
                ],
            }
        ],
    )

    print(response.content[0].text)
    print("-" * 60)
    print(f"Tokens used: {response.usage.input_tokens} input, {response.usage.output_tokens} output")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_identification.py <image_path> [model]")
        print("  model: claude-sonnet-4-20250514 (default) or claude-opus-4-20250514")
        sys.exit(1)

    image_path = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-sonnet-4-20250514"

    test_identification(image_path, model)

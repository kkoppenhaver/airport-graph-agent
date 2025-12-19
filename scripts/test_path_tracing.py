#!/usr/bin/env python3
"""Test path tracing identification without the full agent."""

import base64
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


def test_path_tracing(
    image_path: str,
    starting_point: str,
    known_taxiways: list[str],
    model: str = "claude-sonnet-4-20250514"
):
    """Test path tracing from a specific point."""
    path = Path(image_path)
    if not path.exists():
        print(f"Error: File not found: {image_path}")
        sys.exit(1)

    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    suffix = path.suffix.lower()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        suffix.lstrip("."), "image/png"
    )

    known_list = ", ".join(known_taxiways) if known_taxiways else "none yet"

    prompt = f"""## Path Tracing Task

Starting from: **{starting_point}**
Already known taxiways: {known_list}

### Instructions:
1. Locate {starting_point} on the diagram
2. Find ALL grey taxiway paths that connect to or lead away from this point
3. For EACH grey path, trace it and note:
   - The taxiway letter/name (look for labels on or near the grey path)
   - Where it leads (another taxiway intersection, runway, ramp, etc.)
   - Any OTHER taxiways it intersects along the way

4. Pay special attention to:
   - Small connector taxiways that might be easy to miss
   - Taxiways at the edges/corners of the diagram
   - Any taxiway letters NOT in the known list above

### Report Format:
For each path traced, report:
```
PATH: [Taxiway Letter]
  From: {starting_point}
  Direction: [N/S/E/W/etc]
  Passes through: [intersections]
  Ends at: [destination]
  NEW taxiway? [Yes/No]
```

After tracing all paths, provide:
1. Complete list of taxiways found from this point
2. Any NEW taxiways not in the known list: {known_list}
3. Suggested next starting point for more tracing"""

    print(f"Testing path tracing on: {image_path}")
    print(f"Starting point: {starting_point}")
    print(f"Known taxiways: {known_list}")
    print(f"Model: {model}")
    print("-" * 60)

    client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=3000,
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
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    print(response.content[0].text)
    print("-" * 60)
    print(f"Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/test_path_tracing.py <image_path> <starting_point> [known_taxiways] [model]")
        print("")
        print("Examples:")
        print('  python scripts/test_path_tracing.py diagrams/KDPA.png "Runway 10" "A,B,C,E,F,G,H,W,X,Y"')
        print('  python scripts/test_path_tracing.py diagrams/KDPA.png "Runway 2L" "A,B,C" claude-opus-4-20250514')
        sys.exit(1)

    image_path = sys.argv[1]
    starting_point = sys.argv[2]

    # Parse known taxiways (comma-separated)
    known_taxiways = []
    if len(sys.argv) > 3 and not sys.argv[3].startswith("claude-"):
        known_taxiways = [t.strip() for t in sys.argv[3].split(",") if t.strip()]

    # Model is last arg if it starts with "claude-"
    model = "claude-sonnet-4-20250514"
    for arg in sys.argv[3:]:
        if arg.startswith("claude-"):
            model = arg
            break

    test_path_tracing(image_path, starting_point, known_taxiways, model)

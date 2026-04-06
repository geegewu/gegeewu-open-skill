#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "google-genai>=1.0.0",
#     "pillow>=10.0.0",
#     "httpx[socks]>=0.27.0",
# ]
# ///
"""
Generate images using Google's Nano Banana Pro (Gemini 3 Pro Image) API.

Usage:
    uv run generate_image.py --prompt "your image description" --filename "output.png" [--resolution 1K|2K|4K] [--api-key KEY]
"""

import argparse
import os
import sys
from pathlib import Path


def get_api_keys(provided_key: str | None) -> list[str]:
    """Get API keys: from argument, or all 6 from environment."""
    if provided_key:
        return [provided_key]

    # Try to load all 6 API keys from environment
    keys = []
    for i in range(1, 7):
        key = os.environ.get(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key)

    # Fallback to single GEMINI_API_KEY if no numbered keys found
    if not keys:
        fallback_key = os.environ.get("GEMINI_API_KEY")
        if fallback_key:
            keys.append(fallback_key)

    return keys


def main():
    parser = argparse.ArgumentParser(
        description="Generate images using Nano Banana Pro (Gemini 3 Pro Image)"
    )
    parser.add_argument(
        "--prompt", "-p",
        required=True,
        help="Image description/prompt"
    )
    parser.add_argument(
        "--filename", "-f",
        required=True,
        help="Output filename (e.g., sunset-mountains.png)"
    )
    parser.add_argument(
        "--input-image", "-i",
        help="Optional input image path for editing/modification"
    )
    parser.add_argument(
        "--resolution", "-r",
        choices=["1K", "2K", "4K"],
        default="1K",
        help="Output resolution: 1K (default), 2K, or 4K"
    )
    parser.add_argument(
        "--api-key", "-k",
        help="Gemini API key (overrides GEMINI_API_KEY env var)"
    )

    args = parser.parse_args()

    # Get API keys (all 6 if available)
    api_keys = get_api_keys(args.api_key)
    if not api_keys:
        print("Error: No API key provided.", file=sys.stderr)
        print("Please either:", file=sys.stderr)
        print("  1. Provide --api-key argument", file=sys.stderr)
        print("  2. Set GEMINI_API_KEY_1 to GEMINI_API_KEY_6 environment variables", file=sys.stderr)
        print("  3. Set GEMINI_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(api_keys)} API key(s) for rotation")

    # Import here after checking API key to avoid slow import on error
    from google import genai
    from google.genai import types
    from PIL import Image as PILImage
    import httpx

    # Ensure httpx picks up proxy via standard env vars
    proxy_url = os.environ.get("GEMINI_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_url:
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["https_proxy"] = proxy_url
        print(f"Using proxy: {proxy_url}")

    # Set up output path
    output_path = Path(args.filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load input image if provided
    input_image = None
    output_resolution = args.resolution
    if args.input_image:
        try:
            input_image = PILImage.open(args.input_image)
            print(f"Loaded input image: {args.input_image}")

            # Auto-detect resolution if not explicitly set by user
            if args.resolution == "1K":  # Default value
                width, height = input_image.size
                max_dim = max(width, height)
                if max_dim >= 3000:
                    output_resolution = "4K"
                elif max_dim >= 1500:
                    output_resolution = "2K"
                else:
                    output_resolution = "1K"
                print(f"Auto-detected resolution: {output_resolution} (from input {width}x{height})")
        except Exception as e:
            print(f"Error loading input image: {e}", file=sys.stderr)
            sys.exit(1)

    # Build contents (image first if editing, prompt only if generating)
    if input_image:
        contents = [input_image, args.prompt]
        print(f"Editing image with resolution {output_resolution}...")
    else:
        contents = args.prompt
        print(f"Generating image with resolution {output_resolution}...")

    # API Key rotation: each key can retry up to 2 times
    MAX_RETRIES_PER_KEY = 2
    all_errors = []
    image_saved = False

    for key_idx, api_key in enumerate(api_keys, 1):
        for attempt in range(1, MAX_RETRIES_PER_KEY + 1):
            try:
                print(f"[Key {key_idx}/{len(api_keys)}, Attempt {attempt}/{MAX_RETRIES_PER_KEY}] Generating...")

                client = genai.Client(api_key=api_key)

                response = client.models.generate_content(
                    model="gemini-3-pro-image-preview",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                        image_config=types.ImageConfig(
                            image_size=output_resolution
                        )
                    )
                )

                # Process response and convert to PNG
                for part in response.parts:
                    if part.text is not None:
                        print(f"Model response: {part.text}")
                    elif part.inline_data is not None:
                        from io import BytesIO

                        image_data = part.inline_data.data
                        if isinstance(image_data, str):
                            import base64
                            image_data = base64.b64decode(image_data)

                        image = PILImage.open(BytesIO(image_data))

                        # Ensure RGB mode for PNG
                        if image.mode == 'RGBA':
                            rgb_image = PILImage.new('RGB', image.size, (255, 255, 255))
                            rgb_image.paste(image, mask=image.split()[3])
                            rgb_image.save(str(output_path), 'PNG')
                        elif image.mode == 'RGB':
                            image.save(str(output_path), 'PNG')
                        else:
                            image.convert('RGB').save(str(output_path), 'PNG')
                        image_saved = True

                if image_saved:
                    full_path = output_path.resolve()
                    print(f"\nImage saved: {full_path}")
                    sys.exit(0)
                else:
                    error_msg = f"Key {key_idx} Attempt {attempt}: No image in response"
                    print(f"Failed: {error_msg}", file=sys.stderr)
                    all_errors.append(error_msg)

            except Exception as e:
                error_msg = f"Key {key_idx} Attempt {attempt}: {str(e)}"
                print(f"Failed: {error_msg}", file=sys.stderr)
                all_errors.append(error_msg)

        print(f"Key {key_idx} exhausted ({MAX_RETRIES_PER_KEY} attempts). Switching to next key...\n")

    # All keys exhausted
    print("\n" + "="*60, file=sys.stderr)
    print("ERROR: All API keys exhausted", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"Total attempts: {len(all_errors)}", file=sys.stderr)
    print("\nErrors:", file=sys.stderr)
    for error in all_errors:
        print(f"  - {error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

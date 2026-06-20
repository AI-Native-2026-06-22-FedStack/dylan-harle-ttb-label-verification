import argparse
import mimetypes
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vision import OpenAIVisionService, VisionServiceError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract label fields from one sample image.")
    parser.add_argument("image", type=Path, help="Path to a label image.")
    args = parser.parse_args()

    load_dotenv(BACKEND_ROOT / ".env")

    try:
        image_bytes = args.image.read_bytes()
    except OSError as exc:
        print(f"Could not read image: {exc}", file=sys.stderr)
        return 1

    content_type = mimetypes.guess_type(args.image.name)[0]

    try:
        label = OpenAIVisionService.from_env().extract(image_bytes, content_type)
    except VisionServiceError as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 2

    print(label.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import os
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_VISION_MODEL", "").strip()

    if not api_key:
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    if not model:
        print("OPENAI_VISION_MODEL is not set.", file=sys.stderr)
        return 1

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        client.models.retrieve(model)
    except Exception as exc:
        print(f"Vision model check failed for {model}: {exc}", file=sys.stderr)
        return 1

    checked_date = datetime.now(UTC).date().isoformat()
    print(f"Vision model verified: {model}")
    print(f"Verified against OpenAI Models API on {checked_date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

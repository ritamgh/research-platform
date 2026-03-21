import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("QDRANT_URL"):
    print("ERROR: QDRANT_URL environment variable is not set", file=sys.stderr)
    sys.exit(1)

if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
    sys.exit(1)

from mcp_tools.vector_db.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9002)

"""Development entry point for the local HPT analysis API."""

import os

import uvicorn

from hpt_tracking.api import create_app


if __name__ == "__main__":
    uvicorn.run(
        create_app(),
        host=os.getenv("HPT_API_HOST", "127.0.0.1"),
        port=int(os.getenv("HPT_API_PORT", "8000")),
        reload=False,
    )

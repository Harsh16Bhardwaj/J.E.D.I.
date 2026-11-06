"""One-shot bounded resume worker with document bytes in and evidence JSON out."""

import json
import sys


def main():
    # Unix workers receive CPU limits. Linux also supports a practical address
    # space bound; macOS does not implement that limit consistently.
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    from backend.services.resume import (
        MAX_RESUME_BYTES,
        ResumeError,
        extract_docx_resume,
        extract_resume,
    )

    try:
        data = sys.stdin.buffer.read(MAX_RESUME_BYTES + 1)
        parser = (
            extract_docx_resume if data.startswith(b"PK\x03\x04") else extract_resume
        )
        evidence = parser(data)
        print(json.dumps(evidence.model_dump(mode="json", by_alias=True)))
    except ResumeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}))


if __name__ == "__main__":
    main()

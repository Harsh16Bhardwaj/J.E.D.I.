"""One-shot bounded PDF worker; stdin is PDF bytes, stdout is structured JSON."""

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
    from backend.services.resume import MAX_PDF_BYTES, ResumeError, extract_resume

    try:
        evidence = extract_resume(sys.stdin.buffer.read(MAX_PDF_BYTES + 1))
        print(evidence.model_dump_json(by_alias=True))
    except ResumeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}))


if __name__ == "__main__":
    main()

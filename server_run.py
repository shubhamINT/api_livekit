# server_run.py
import os

def main():

    port = os.getenv("PORT", "8000")

    cmd = [
        "gunicorn",
        "src.api.server:app",                     # your ASGI/FastAPI app
        "-k",
        "uvicorn.workers.UvicornWorker",    
        "--workers", "2",
        "--bind", f"0.0.0.0:{port}",
        "--keep-alive", "20",
        "--timeout", "120",  # TTS can be slow
        "--max-requests", "1000",  # Restart workers to prevent memory leaks
        "--max-requests-jitter", "100",
    ]

    # Replace current process with Gunicorn
    os.execvp(cmd[0], cmd)

if __name__ == "__main__":
    main()

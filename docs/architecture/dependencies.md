# Container Dependencies

The production deployment uses two role-specific images and three services. The images are
separate so the LiveKit worker does not need to carry the FastAPI and documentation stack, and the
control plane does not need the agent provider plugins.

## Services and images

| Service | Container image | Process | Role |
|---|---|---|---|
| `api` | `Dockerfile.control` | `python server_run.py` | FastAPI HTTP API and, in single-container mode, background services |
| `sip_dispatcher` | `Dockerfile.control` | `python sip_dispatcher_run.py` | Singleton inbound SIP listener and outbound queue dispatcher |
| `agent` | `Dockerfile.agent` | `python -m livekit.agents start agent_run.py` | LiveKit agent worker and provider integrations |

The `api` and `sip_dispatcher` containers intentionally share the control image. They need
different processes, not different package sets, because the control image is also the deployment
unit used by the Compose profile. Only one `sip_dispatcher` may run across the deployment.

## Agent image

`docker/requirements-agent.txt` contains packages imported by the worker path:

- `livekit-agents` and the Cartesia, Deepgram, ElevenLabs, Google, OpenAI, and Sarvam extras,
  because provider factories import those integrations.
- `beanie` and `motor` for assistant, call, audio-asset, and usage records.
- `httpx` for tools, inbound context, and provider validation.
- `chevron` for prompt rendering.
- `numpy` and `onnxruntime` for local audio denoising and VAD support.
- `boto3` for downloading prerecorded greetings from S3.
- `mistralai` for the supported Mistral TTS path.

`scipy` is not used by the normal agent entrypoint. It is used by the SIP/RTP bridge in the
dispatcher path, so it can be removed from the agent requirements only if the agent image will
never run SIP bridge code. `audioop-lts` is conditional on Python 3.13 or newer; the production
Dockerfile uses Python 3.12, so that line currently installs nothing.

## Control image

`docker/requirements-control.txt` contains packages used by the API, dispatcher, or image build:

- `fastapi[standard]` and `gunicorn` for the HTTP service.
- `beanie`, `motor`, `python-dotenv`, and `httpx` for shared persistence and service integration.
- `livekit` and `livekit-api` for LiveKit API, RTC, SIP, token, and bridge operations.
- `numpy`, `scipy`, and `av` for audio upload transcoding and SIP/RTP processing.
- `boto3` for audio-asset storage.
- `mcp` for the read-only `/mcp` documentation server.
- `mkdocs` and `mkdocs-material` to build the documentation site during the image build.

`chevron` is an agent prompt-rendering dependency and is not required by the normal API or
dispatcher entrypoints. It is not needed in the control requirements unless control-side code
starts importing agent prompt utilities.

## Build-time versus runtime

The control Dockerfile installs one virtual environment, builds the site with MkDocs, and copies
that environment into the final image. Therefore MkDocs remains installed in the final image even
though the API does not import it for ordinary requests. Removing it from the requirements without
moving the build to a separate stage breaks the image build.

Build-only documentation dependencies affect image size and build time, not API request RAM. The
main runtime memory costs are the agent worker's provider plugins and local audio runtime, plus the
number of worker processes and concurrent calls.

## Two-server deployment

Recommended layout:

| Server | Services | Main pressure |
|---|---|---|
| Control plane | `api` and one `sip_dispatcher` | API workers, MongoDB traffic, SIP/RTP bridge processes |
| Capacity node | one or more `agent` containers | Agent process memory, provider connections, local audio models |

Use the Compose profiles rather than installing both requirement files into every environment:

```bash
# Control plane
docker compose --profile control up -d --build

# Agent capacity node
docker compose --profile agent up -d --build
```

Installed packages do not each consume a full copy of RAM. RAM is consumed when a process imports
and uses them. Docker image layers are shared on disk, while each running container has its own
process memory. Measure steady-state RSS and concurrency with `docker stats` before changing
`MAX_CONCURRENT_*`, `GUNICORN_WORKERS`, or the agent's idle-process count.

## Safe dependency cleanup

The following are the current low-risk candidates, subject to the deployment checks above:

| Change | Effect | Caveat |
|---|---|---|
| Remove `scipy` from the agent requirements | Smaller agent image and less unused import weight | Do not run the SIP bridge from that image |
| Remove `chevron` from the control requirements | Smaller control image | Do not import agent prompt rendering from control code |
| Keep `audioop-lts` conditional | No change on Python 3.12 | Needed only if the base image moves to Python 3.13 and a dependency requires it |
| Move MkDocs to a documentation builder stage | Smaller final control image | Requires Dockerfile changes; it does not materially reduce live API RAM |

Do not remove `numpy`, `onnxruntime`, `av`, `boto3`, MongoDB packages, or LiveKit packages based
only on image size. Each has a concrete runtime path in the current deployment.

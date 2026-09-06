"""Launch the LiveKit agent worker.

Production runs `python -m livekit.agents start agent_run.py`. That command imports this
module and looks for a module-level `AgentServer`, which is why the worker options live here
and are converted rather than passed to the CLI directly.

Developers run `uv run agent_run.py dev`, which goes through the SDK's deprecated Python CLI.
That path prints a DeprecationWarning and will stop working when the SDK removes it; it is
kept because the supported replacement (`lk agent dev`) needs a separate binary installed.

The worker configuration lives in this file rather than in src/core/agents/session.py so that
importing the job handler — which several test modules do — does not build a worker. The
entrypoint is a root-level file rather than the session module itself because src/ is a
namespace package with no __init__.py, and the CLI's module discovery would import
src/core/agents/session.py a second time under the bare name `session`.
"""

from livekit.agents import AgentServer, WorkerOptions, cli

from src.core.agents.session import entrypoint
from src.core.config import settings


def _worker_load(worker) -> float:
    """Report this worker's load as a fraction of the jobs it is willing to run.

    The SDK default measures CPU across the whole machine. That made job intake depend on
    whatever else the host was doing: when the SIP dispatcher spiked CPU launching bridge
    processes, this worker quietly stopped accepting jobs, so calls connected with no agent
    behind them and the caller heard nothing. Counting our own jobs keeps the decision local
    and predictable.
    """
    # Measured against the global ceiling, not the telephony cap: this worker runs the agent
    # job for *every* call type — phone, web and passthrough — so the telephony cap alone would
    # make it refuse web jobs it has ample room for.
    max_jobs = max(1, settings.MAX_CONCURRENT_SESSIONS)
    return min(1.0, len(worker.active_jobs) / max_jobs)


# Named `server` because that is the first name the CLI's discovery looks for
# (livekit/agents/cli/discover.py::get_app_name).
server = AgentServer.from_server_options(
    WorkerOptions(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        ws_url=settings.LIVEKIT_URL,
        job_memory_warn_mb=1024,
        # A hard ceiling, not just a warning. Only job_memory_warn_mb was set before, which
        # logs and does nothing, so a leaking session grew until the container OOMed and
        # took every call running alongside it down with it.
        job_memory_limit_mb=2048,
        entrypoint_fnc=entrypoint,
        agent_name="api-agent",
        # Raised from 2: at a dozen simultaneous calls, jobs past the second one queued
        # behind a cold process start each.
        num_idle_processes=4,
        load_fnc=_worker_load,
        # The SDK refuses a job when load >= threshold, so 1.0 means "refuse once we are
        # already running MAX_CONCURRENT_JOBS". Anything lower would make the worker refuse
        # jobs the dispatcher is still willing to send, and a dispatched call with no agent
        # behind it is a call that connects to silence.
        load_threshold=1.0,
    )
)


if __name__ == "__main__":
    cli.run_app(server)

import unittest
from types import SimpleNamespace

from livekit.agents import AgentServer

import agent_run
from src.core.config import settings


class TestAgentServerDiscovery(unittest.TestCase):
    """`python -m livekit.agents start agent_run.py` finds the worker by these two facts.

    The CLI imports this module and takes the first global named `app`, `server` or `agent`
    that is an AgentServer (livekit/agents/cli/discover.py::get_app_name). Renaming the
    global, or handing the CLI a WorkerOptions instead, fails only at container start.
    """

    def test_module_exposes_an_agent_server_named_server(self):
        self.assertIsInstance(agent_run.server, AgentServer)

    def test_agent_name_still_matches_the_dispatched_job(self):
        # The dispatcher requests "api-agent" by name; a mismatch means every dispatched call
        # waits for a worker that never claims it.
        self.assertEqual(agent_run.server._agent_name, "api-agent")


class TestWorkerLoad(unittest.TestCase):
    def _load(self, active_jobs: int) -> float:
        return agent_run._worker_load(SimpleNamespace(active_jobs=[None] * active_jobs))

    def test_idle_worker_reports_no_load(self):
        self.assertEqual(self._load(0), 0.0)

    def test_load_reaches_one_at_the_global_ceiling(self):
        # load_threshold=1.0, so this is exactly the point the SDK starts refusing jobs.
        self.assertEqual(self._load(settings.MAX_CONCURRENT_SESSIONS), 1.0)

    def test_load_is_capped_when_more_jobs_are_running_than_the_ceiling(self):
        self.assertEqual(self._load(settings.MAX_CONCURRENT_SESSIONS * 2), 1.0)

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.models.api_schemas.standalone import (
    ChatCompletionRequest,
    ChatMessage,
    SynthesizeRequest,
)
from src.api.routes import llm, standalone_helper, stt, tts
from src.core.db.db_schemas import Assistant, UsageRecord
from src.services.storage.audio_transcode import MAX_UPLOAD_BYTES


class QueryField:
    def __eq__(self, other):
        return other


class _FakeUpload:
    filename = "test.wav"

    def __init__(self, content: bytes):
        self._content = content
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            res = self._content[self._pos :]
            self._pos = len(self._content)
            return res
        res = self._content[self._pos : self._pos + size]
        self._pos += len(res)
        return res


class TestStandaloneVoiceSchemas(unittest.TestCase):
    """Schema validations."""

    def test_tts_rejects_empty_text(self):
        with self.assertRaises(Exception):
            SynthesizeRequest(text="")

    def test_tts_rejects_whitespace_text(self):
        with self.assertRaises(Exception):
            SynthesizeRequest(text="    ")

    def test_tts_rejects_text_over_5000_chars(self):
        with self.assertRaises(Exception):
            SynthesizeRequest(text="a" * 5001)

    def test_tts_accepts_valid_payload(self):
        req = SynthesizeRequest(text="Hello world", provider="cartesia", voice="voice-1")
        self.assertEqual(req.text, "Hello world")
        self.assertEqual(req.provider, "cartesia")

    def test_llm_rejects_empty_messages(self):
        with self.assertRaises(Exception):
            ChatCompletionRequest(messages=[])

    def test_llm_accepts_valid_chat_messages(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            provider="openai",
            model="gpt-5.4",
        )
        self.assertEqual(len(req.messages), 1)
        self.assertEqual(req.provider, "openai")


class TestStandaloneVoiceRoutes(unittest.IsolatedAsyncioTestCase):
    """Route logic and acceptance criteria validation."""

    def setUp(self):
        self.user = SimpleNamespace(
            api_key="lvk_test_12345",
            user_email="dev@example.com",
            user_name="Dev User",
            is_active=True,
        )

    async def test_auth_rejection(self):
        """AC-2: Unauthenticated requests return 401."""
        from src.api.server import app

        with patch("src.core.db.database.init_db", AsyncMock()):
            client = TestClient(app)
            for endpoint, method, kwargs in [
                ("/stt/transcribe", "post", {"files": {"file": ("test.wav", b"RIFF1234WAVE", "audio/wav")}}),
                ("/tts/synthesize", "post", {"json": {"text": "hello"}}),
                ("/llm/chat", "post", {"json": {"messages": [{"role": "user", "content": "hi"}]}}),
            ]:
                resp = getattr(client, method)(endpoint, **kwargs)
                self.assertEqual(resp.status_code, 401, f"{endpoint} did not return 401 without auth")

    async def test_stt_transcribe_success(self):
        """AC-1: Valid audio returns 200 with transcription and duration."""
        fake_file = _FakeUpload(b"RIFFdummywavecontent")
        mock_result = {
            "text": "Hello world transcription",
            "language": "en",
            "duration_seconds": 1.5,
            "provider": "sarvam",
            "model": "saaras:v3",
        }
        mock_usage_res = {
            "estimated_cost_usd": 0.0001,
            "pricing_complete": True,
            "audio_duration_seconds": 1.5,
        }
        with patch("src.api.routes.stt.transcribe_audio", AsyncMock(return_value=mock_result)), patch(
            "src.api.routes.stt.log_standalone_usage", AsyncMock(return_value=mock_usage_res)
        ) as mock_usage:
            resp = await stt.transcribe(
                file=fake_file,
                provider="sarvam",
                model="saaras:v3",
                current_user=self.user,
            )
            self.assertTrue(resp.success)
            self.assertEqual(resp.data["text"], "Hello world transcription")
            self.assertIn("usage", resp.data)
            self.assertEqual(resp.data["usage"]["estimated_cost_usd"], 0.0001)
            mock_usage.assert_awaited_once()

    async def test_stt_rejects_oversized_audio(self):
        """AC-3: Audio exceeding 25 MB returns 413."""
        fake_file = _FakeUpload(b"\x00" * (MAX_UPLOAD_BYTES + 10))
        with self.assertRaises(HTTPException) as ctx:
            await stt.transcribe(file=fake_file, current_user=self.user)
        self.assertEqual(ctx.exception.status_code, 413)

    async def test_stt_rejects_empty_audio(self):
        """AC-3: Empty audio upload returns 422."""
        fake_file = _FakeUpload(b"")
        with self.assertRaises(HTTPException) as ctx:
            await stt.transcribe(file=fake_file, current_user=self.user)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_tts_synthesize_success(self):
        """AC-4: Valid text streams binary audio with appropriate headers."""
        req = SynthesizeRequest(text="Hello world", provider="cartesia")
        mock_usage_res = {
            "estimated_cost_usd": 0.00015,
            "pricing_complete": True,
            "characters_count": 11,
            "audio_duration_seconds": 1.2,
        }
        with patch(
            "src.api.routes.tts.synthesize_speech",
            AsyncMock(return_value=(b"RIFFwavdata", "audio/wav")),
        ), patch(
            "src.api.routes.tts.log_standalone_usage",
            AsyncMock(return_value=mock_usage_res),
        ) as mock_usage:
            resp = await tts.synthesize(request=req, current_user=self.user)
            self.assertEqual(resp.media_type, "audio/wav")
            self.assertEqual(resp.body, b"RIFFwavdata")
            self.assertIn("X-Estimated-Cost-USD", resp.headers)
            self.assertIn("X-TTS-Characters", resp.headers)
            mock_usage.assert_awaited_once()

    async def test_tts_synthesize_json_format(self):
        """Valid text with response_format=json returns base64 audio and usage."""
        req = SynthesizeRequest(text="Hello world", provider="cartesia", response_format="json")
        mock_usage_res = {
            "estimated_cost_usd": 0.00015,
            "pricing_complete": True,
            "characters_count": 11,
            "audio_duration_seconds": 1.2,
        }
        with patch(
            "src.api.routes.tts.synthesize_speech",
            AsyncMock(return_value=(b"RIFFwavdata", "audio/wav")),
        ), patch(
            "src.api.routes.tts.log_standalone_usage",
            AsyncMock(return_value=mock_usage_res),
        ):
            resp = await tts.synthesize(request=req, current_user=self.user)
            self.assertTrue(resp.success)
            self.assertEqual(resp.data["provider"], "cartesia")
            self.assertIn("audio_base64", resp.data)
            self.assertEqual(resp.data["usage"]["estimated_cost_usd"], 0.00015)

    async def test_llm_chat_non_stream_success(self):
        """AC-6: Valid chat messages with stream=false return assistant message and token usage."""
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            provider="openai",
            model="gpt-5.4",
            stream=False,
        )
        mock_result = {
            "message": {"role": "assistant", "content": "Hi there!"},
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "provider": "openai",
            "model": "gpt-5.4",
        }
        mock_usage_res = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "estimated_cost_usd": 0.0002,
            "pricing_complete": True,
        }
        with patch("src.api.routes.llm.chat_completion", AsyncMock(return_value=mock_result)), patch(
            "src.api.routes.llm.log_standalone_usage", AsyncMock(return_value=mock_usage_res)
        ) as mock_usage:
            resp = await llm.chat(request=req, current_user=self.user)
            self.assertTrue(resp.success)
            self.assertEqual(resp.data["message"]["content"], "Hi there!")
            self.assertIn("usage", resp.data)
            self.assertEqual(resp.data["usage"]["estimated_cost_usd"], 0.0002)
            mock_usage.assert_awaited_once()

    async def test_llm_chat_stream_success(self):
        """AC-7: Chat request with stream=true returns SSE StreamingResponse."""
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            provider="openai",
            model="gpt-5.4",
            stream=True,
        )

        async def fake_stream(*args, **kwargs):
            yield "data: chunk1\n\n"
            yield "data: [DONE]\n\n"

        with patch("src.api.routes.llm.stream_chat_completion", fake_stream):
            resp = await llm.chat(request=req, current_user=self.user)
            self.assertEqual(resp.media_type, "text/event-stream")

    async def test_assistant_inheritance_and_override(self):
        """AC-8: Valid assistant_id inherits settings, explicit params override them."""
        assistant = SimpleNamespace(
            assistant_id="ast-1",
            created_by_email="dev@example.com",
            assistant_stt_model="sarvam",
            assistant_stt_config={"model": "saaras:v3", "language": "hi-IN", "api_key": "sarvam_key"},
            assistant_tts_model="cartesia",
            assistant_tts_config={"model": "sonic-3", "voice": "v-1"},
            assistant_llm_config={"provider": "openai", "model": "gpt-5.4"},
        )
        with patch("src.api.routes.standalone_helper.Assistant") as mock_ast:
            mock_ast.assistant_id = QueryField()
            mock_ast.created_by_email = QueryField()
            mock_ast.find_one = AsyncMock(return_value=assistant)

            # Inherit STT
            cfg = await standalone_helper.resolve_stage_config(
                stage="stt", user=self.user, assistant_id="ast-1"
            )
            self.assertEqual(cfg["provider"], "sarvam")
            self.assertEqual(cfg["language"], "hi-IN")
            self.assertEqual(cfg["api_key"], "sarvam_key")

            # Override STT language
            cfg_override = await standalone_helper.resolve_stage_config(
                stage="stt",
                user=self.user,
                assistant_id="ast-1",
                explicit_language="en-US",
            )
            self.assertEqual(cfg_override["language"], "en-US")

    async def test_unowned_assistant_returns_404(self):
        """AC-9: Non-existent or unowned assistant_id returns 404."""
        with patch("src.api.routes.standalone_helper.Assistant") as mock_ast:
            mock_ast.assistant_id = QueryField()
            mock_ast.created_by_email = QueryField()
            mock_ast.find_one = AsyncMock(return_value=None)

            with self.assertRaises(HTTPException) as ctx:
                await standalone_helper.resolve_stage_config(
                    stage="stt", user=self.user, assistant_id="non-existent"
                )
            self.assertEqual(ctx.exception.status_code, 404)

    async def test_invalid_provider_returns_422(self):
        """AC-10: Invalid provider name returns 422."""
        with self.assertRaises(HTTPException) as ctx:
            await standalone_helper.resolve_stage_config(
                stage="stt", user=self.user, explicit_provider="unsupported_vendor"
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_compute_stage_pricing(self):
        """Pricing helper calculates costs for STT, TTS, and LLM."""
        stt_pricing = standalone_helper.compute_stage_pricing(
            stage="stt", provider="sarvam", model="saaras:v3", audio_duration=10.0
        )
        self.assertGreater(stt_pricing["estimated_cost_usd"], 0)
        self.assertTrue(stt_pricing["pricing_complete"])

        tts_pricing = standalone_helper.compute_stage_pricing(
            stage="tts", provider="cartesia", model="sonic-3", characters_count=100, audio_duration=5.0
        )
        self.assertGreater(tts_pricing["estimated_cost_usd"], 0)
        self.assertTrue(tts_pricing["pricing_complete"])

        llm_pricing = standalone_helper.compute_stage_pricing(
            stage="llm", provider="openai", model="gpt-5.4", prompt_tokens=100, completion_tokens=50
        )
        self.assertGreater(llm_pricing["estimated_cost_usd"], 0)
        self.assertTrue(llm_pricing["pricing_complete"])

    async def test_log_standalone_usage(self):
        """AC-11: Usage logged to UsageRecord with call_type=standalone_api."""
        mock_record_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.insert = AsyncMock()
        mock_record_cls.return_value = mock_instance

        with patch("src.api.routes.standalone_helper.UsageRecord", mock_record_cls):
            await standalone_helper.log_standalone_usage(
                stage="stt",
                user_email="dev@example.com",
                provider="sarvam",
                model="saaras:v3",
                duration_seconds=3.2,
            )
            mock_record_cls.assert_called_once()
            call_kwargs = mock_record_cls.call_args.kwargs
            self.assertEqual(call_kwargs["call_service"], "standalone_api")
            self.assertEqual(call_kwargs["user_email"], "dev@example.com")
            self.assertEqual(mock_instance.stt_provider, "sarvam")
            self.assertEqual(mock_instance.stt_audio_duration, 3.2)
            mock_instance.insert.assert_awaited_once()


class TestServiceClientAdapters(unittest.IsolatedAsyncioTestCase):
    """Direct tests for client service functions across providers."""

    async def test_stt_transcribe_missing_key_raises(self):
        from src.services.stt.client import transcribe_audio

        with patch("src.services.stt.client.settings") as mock_settings:
            mock_settings.SARVAM_API_KEY = None
            with self.assertRaises(ValueError):
                await transcribe_audio(
                    audio_bytes=b"dummy",
                    filename="audio.wav",
                    provider="sarvam",
                    model="saaras:v3",
                    api_key=None,
                )

    async def test_stt_transcribe_sarvam(self):
        from src.services.stt.client import transcribe_audio

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"transcript": "Sarvam output", "language_code": "hi"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.stt.client.httpx.AsyncClient", return_value=mock_client):
            res = await transcribe_audio(
                audio_bytes=b"wavdata",
                filename="test.wav",
                provider="sarvam",
                model="saaras:v3",
                language="hi-IN",
                api_key="sk-test",
            )
            self.assertEqual(res["text"], "Sarvam output")
            self.assertEqual(res["language"], "hi")

    async def test_stt_transcribe_openai(self):
        from src.services.stt.client import transcribe_audio

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"text": "OpenAI transcript", "duration": 4.5}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.stt.client.httpx.AsyncClient", return_value=mock_client):
            res = await transcribe_audio(
                audio_bytes=b"wavdata",
                filename="test.wav",
                provider="openai",
                model="whisper-1",
                api_key="sk-openai",
            )
            self.assertEqual(res["text"], "OpenAI transcript")
            self.assertEqual(res["duration_seconds"], 4.5)

    async def test_tts_synthesize_cartesia(self):
        from src.services.tts.client import synthesize_speech

        mock_resp = MagicMock()
        mock_resp.content = b"cartesia_wav"
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.tts.client.httpx.AsyncClient", return_value=mock_client):
            audio_bytes, media_type = await synthesize_speech(
                text="Hello cartesia",
                provider="cartesia",
                model="sonic-3",
                api_key="cartesia_key",
            )
            self.assertEqual(audio_bytes, b"cartesia_wav")
            self.assertEqual(media_type, "audio/wav")

    async def test_tts_synthesize_sarvam(self):
        import base64
        from src.services.tts.client import synthesize_speech

        dummy_b64 = base64.b64encode(b"sarvam_wav").decode("ascii")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"audios": [dummy_b64]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.tts.client.httpx.AsyncClient", return_value=mock_client):
            audio_bytes, media_type = await synthesize_speech(
                text="Namaste",
                provider="sarvam",
                model="bulbul:v3",
                api_key="sarvam_key",
            )
            self.assertEqual(audio_bytes, b"sarvam_wav")
            self.assertEqual(media_type, "audio/wav")

    async def test_llm_chat_completion_openai(self):
        from src.services.llm.client import chat_completion

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "OpenAI answer"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.llm.client.httpx.AsyncClient", return_value=mock_client):
            res = await chat_completion(
                messages=[{"role": "user", "content": "Question"}],
                provider="openai",
                model="gpt-5.4",
                api_key="sk-test",
            )
            self.assertEqual(res["message"]["content"], "OpenAI answer")
            self.assertEqual(res["usage"]["total_tokens"], 18)

    async def test_llm_chat_completion_gemini(self):
        from src.services.llm.client import chat_completion

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini answer"}]}}],
            "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 4, "totalTokenCount": 12},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("src.services.llm.client.httpx.AsyncClient", return_value=mock_client):
            res = await chat_completion(
                messages=[{"role": "user", "content": "Question"}],
                provider="gemini",
                model="gemini-2.5-flash",
                api_key="gemini_key",
            )
            self.assertEqual(res["message"]["content"], "Gemini answer")
            self.assertEqual(res["usage"]["total_tokens"], 12)


if __name__ == "__main__":
    unittest.main()

"""
RTP Media Bridge — bidirectional audio between LiveKit and SIP/RTP.

Handles:
  • Binding a UDP socket for RTP
  • Receiving inbound RTP, decoding G.711, resampling to 48 kHz, pushing to LiveKit
  • Receiving LiveKit audio, resampling to 8 kHz, encoding G.711, sending as RTP
  • Mixing multiple outbound audio tracks (agent voice + background sounds)
  • Buffering agent audio while SIP INVITE is in progress
"""

import asyncio
import collections
import random
import socket
import struct
import time
from collections.abc import AsyncIterator

import audioop
import numpy as np
from scipy.signal import butter, resample_poly, sosfilt, sosfilt_zi, firwin

from livekit import rtc

from .config import (
    PCMA_PAYLOAD_TYPE,
    PCMU_PAYLOAD_TYPE,
    RTP_HEADER_SIZE,
    SAMPLE_RATE_LK,
    SAMPLE_RATE_SIP,
    MAX_FRAME_BUFFER,
)
from src.core.logger import logger

# High-pass at 80 Hz removes DC offset and sub-bass hum without touching speech.
# The low-pass (anti-aliasing at 4 kHz) is already handled by resample_poly's internal FIR —
# a 3400 Hz bandpass upper cutoff is redundant and its phase distortion made voices sound hollow.
_HP_SOS = butter(2, 80, btype="high", fs=SAMPLE_RATE_SIP, output="sos")
_HP_ZI_TEMPLATE = sosfilt_zi(_HP_SOS)  # shape (n_sections, 2), scaled per-packet

# Pin our own custom FIR filter to protect against SciPy updates.
# A filter with half_len=10 has 2 * 10 * 6 + 1 = 121 taps, group delay is exactly 10 samples (at low rate)
_RESAMPLE_FILTER = firwin(121, 1.0 / 6.0, window=("kaiser", 5.0))


def _decode_rtp_payload(payload: bytes, pt: int, state: object) -> tuple[bytes, object]:
    """Decode G.711, high-pass filter (80 Hz), resample 8 kHz→48 kHz.

    Uses stateful polyphase resampling (scipy) with overlap-save to avoid packet
    boundary transients and aliasing artifacts that degrade voice quality and STT.
    state: tuple of (hp_zi, resample_history) or None, or just hp_zi (for backward compatibility).
    """
    # Only G.711 audio decoded. PT=101 (RFC 2833 DTMF), comfort noise, and any other
    # dynamic PTs would otherwise be alaw-decoded into garbage PCM → STT noise.
    if pt != PCMA_PAYLOAD_TYPE and pt != PCMU_PAYLOAD_TYPE:
        return b"", state

    # Parse state dynamically for robust backward compatibility
    if isinstance(state, tuple) and len(state) == 2:
        hp_zi, history = state
    else:
        # If old format (or None), initialize
        hp_zi = state if state is not None else None
        history = None

    if history is None:
        history = np.zeros(20, dtype=np.float32)

    pcm8 = audioop.alaw2lin(payload, 2) if pt == PCMA_PAYLOAD_TYPE else audioop.ulaw2lin(payload, 2)

    samples = np.frombuffer(pcm8, dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
    if len(samples) == 0:
        return b"", (hp_zi, history)

    # Scale template to first-sample DC level (scipy idiom) to suppress startup transient.
    if hp_zi is None:
        hp_zi = _HP_ZI_TEMPLATE * samples[0]
    samples, hp_zi = sosfilt(_HP_SOS, samples, zi=hp_zi)

    # Stateful polyphase upsampling (8 kHz -> 48 kHz, up=6, down=1)
    # Prepend the history of 20 samples to avoid left-edge filter boundary transients.
    full_input = np.concatenate([history, samples])
    new_history = full_input[-len(history):]

    resampled_full = resample_poly(full_input, 6, 1, window=_RESAMPLE_FILTER)

    # Group delay is 10 samples (at low rate). Align output:
    start_idx = (len(history) - 10) * 6
    end_idx = start_idx + len(samples) * 6
    samples_48k = resampled_full[start_idx:end_idx]

    samples_48k = np.tanh(samples_48k * 1.5)  # boost quiet phone audio, soft-clip peaks

    return (samples_48k * 32767.0).astype(np.int16).tobytes(), (hp_zi, new_history)


class RTPMediaBridge:
    def __init__(self, public_ip: str, bind_port: int):
        """
        public_ip  : Server's public/Elastic IP — written into SDP c= line.
        bind_port  : UDP port to listen on (from PortPool).
        """
        if not public_ip or public_ip == "0.0.0.0":
            raise ValueError(
                "public_ip must be your EC2 public/Elastic IP. "
                f"Got: '{public_ip}'. Check EXOTEL_MEDIA_IP."
            )
        self._public_ip = public_ip
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        self._sock.bind(("0.0.0.0", bind_port))
        self._sock.setblocking(False)
        self.local_port = self._sock.getsockname()[1]
        logger.info(
            f"[RTP] Socket bound 0.0.0.0:{self.local_port} "
            f"| SDP advertises {public_ip}:{self.local_port}"
        )

        self._remote_addr: tuple[str, int] | None = None
        # _tx_ready: gates outbound (web→SIP). Set only after 200 OK.
        # _rx_ready: gates inbound (SIP→web). Set after 200 OK for agent calls;
        #            set after 183+SDP for passthrough calls so humans hear ringback.
        self._tx_ready = False
        self._rx_ready = False
        self._running = False
        self.negotiated_pt = PCMA_PAYLOAD_TYPE

        self._audio_source: rtc.AudioSource | None = None
        self._local_track: rtc.LocalAudioTrack | None = None

        self._rtp_seq = random.randint(0, 0xFFFF)
        self._rtp_ts = random.randint(0, 0xFFFFFFFF)
        self._rtp_ssrc = random.randint(0, 0xFFFFFFFF)

        self._hp_zi = (None, np.zeros(20, dtype=np.float32))  # state tuple for inbound high-pass + stateful upsampler
        self._outbound_resample_history = np.zeros(120, dtype=np.float32)  # stateful downsampler overlap history

        self._rx = 0
        self._tx = 0
        self._first_rx = False
        self._logged_early_rtp = False
        self._first_tx = False
        self._last_rx_ts: float | None = None

        # Buffer agent frames until set_remote_endpoint() is called
        self._frame_buffer: collections.deque = collections.deque(
            maxlen=MAX_FRAME_BUFFER
        )

        # ptime accumulator: collect PCM until we have exactly 20ms to send.
        # At 8kHz, 16-bit mono: 20ms = 160 samples = 320 bytes of PCM.
        # G.711 encodes 1:1, so payload = 160 bytes. Total RTP = 172 bytes.
        # LiveKit sends 10ms frames, so we pack 2 frames → 1 RTP packet.
        self._PTIME_BYTES = 320  # 20ms at 8kHz 16-bit mono (160 samples * 2 bytes)
        self._pcm_accumulator = bytearray()

        # Multi-track mixer: combines agent voice + background/thinking sounds.
        # blocksize=480 (10ms @ 48kHz) matches LiveKit's native frame size — no extra buffering.
        # stream_timeout_ms=20: emit silence after one missed frame instead of waiting 200ms.
        self._mixer = rtc.AudioMixer(
            SAMPLE_RATE_LK, 1, blocksize=480, stream_timeout_ms=20, capacity=50
        )
        self._mixer_task: asyncio.Task | None = None
        self._track_streams: list[rtc.AudioStream] = []

        # Bounded inbound RTP queue. ~1s @ 50pps. _on_rtp_readable drops oldest on overflow
        # so playback can't drift behind real-time under bursty input.
        self._recv_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    def set_early_media_endpoint(self, ip: str, port: int, pt: int = PCMA_PAYLOAD_TYPE):
        """Unlock inbound RTP (SIP→web) before answer. Used by passthrough calls on 183+SDP.
        TX stays locked — we don't send web audio to SIP until 200 OK."""
        self._remote_addr = (ip, port)
        self.negotiated_pt = pt
        self._rx_ready = True
        logger.info(f"[RTP] Early media endpoint → {ip}:{port} PT={pt} (RX only)")

    def set_remote_endpoint(self, ip: str, port: int, pt: int = PCMA_PAYLOAD_TYPE):
        self._remote_addr = (ip, port)
        self.negotiated_pt = pt
        # Unlock both directions after SIP 200 OK.
        self._tx_ready = True
        self._rx_ready = True
        logger.info(f"[RTP] Remote endpoint → {ip}:{port} PT={pt}")
        # Immediately flush any agent audio that was buffered during the SIP
        # INVITE / ringing phase.  We cannot await here (sync method) so we
        # schedule it as a fire-and-forget task on the running event loop.
        if self._frame_buffer:
            asyncio.create_task(self._flush_buffer())

    async def _flush_buffer(self):
        """Drain frames that arrived before the SIP call was answered.

        Without this, the buffer is only flushed the next time send_to_rtp()
        is called.  If the agent spoke its opening greeting during INVITE and
        then went silent (waiting for the user to say something), no new frame
        ever arrives and the greeting is silently discarded.
        """
        count = len(self._frame_buffer)
        if not count:
            return
        logger.info(f"[RTP] Flushing {count} buffered frame(s) after SIP answer")
        while self._frame_buffer:
            await self._send_frame(self._frame_buffer.popleft())
            await asyncio.sleep(0)  # yield between frames so concurrent bridges aren't starved
        logger.info(f"[RTP] Buffer flush complete ({count} frames sent)")

    async def start_inbound(self, room: rtc.Room):
        self._audio_source = rtc.AudioSource(SAMPLE_RATE_LK, 1)
        self._local_track = rtc.LocalAudioTrack.create_audio_track(
            "sip_audio", self._audio_source
        )
        # ← ADD THIS: tell the agent session this is a microphone track
        publish_options = rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_MICROPHONE
        )
        await room.local_participant.publish_track(self._local_track, publish_options)
        self._running = True

        # add_reader works with uvloop — sock_recvfrom does NOT
        loop = asyncio.get_running_loop()
        loop.add_reader(self._sock.fileno(), self._on_rtp_readable)

        task = asyncio.create_task(self._recv_loop())

        def _on_recv_done(t: asyncio.Task):
            if t.cancelled():
                logger.info("[RTP] recv_loop cancelled")
            elif t.exception():
                logger.error("[RTP] recv_loop DIED", exc_info=t.exception())
            else:
                logger.info("[RTP] recv_loop exited cleanly")

        task.add_done_callback(_on_recv_done)
        logger.info(
            f"[RTP] Inbound loop started, listening on 0.0.0.0:{self.local_port}"
        )

    def _on_rtp_readable(self):
        """Called by event loop when UDP socket has data. Works with uvloop."""
        try:
            data, addr = self._sock.recvfrom(4096)
            # DROP packets from any source that is not the endpoint the SDP negotiated. This
            # used to allow packets through while _remote_addr was still None, and _recv_loop
            # then adopted the first sender as the peer — so RTP still in flight from a call
            # that had just released this port could be latched onto as the new call's peer,
            # which is how one caller ended up hearing another. Every code path sets the
            # endpoint from the SDP answer/offer before media starts, so there is nothing
            # legitimate to learn from the wire.
            if addr != self._remote_addr:
                if self._remote_addr is None and not self._logged_early_rtp:
                    self._logged_early_rtp = True
                    logger.warning(
                        f"[RTP] Dropping RTP from {addr} on port {self.local_port} — "
                        "no negotiated endpoint yet"
                    )
                return
            try:
                self._recv_queue.put_nowait((data, addr))
            except asyncio.QueueFull:
                # Drop oldest to keep playback aligned with real-time.
                try:
                    self._recv_queue.get_nowait()
                    self._recv_queue.put_nowait((data, addr))
                except Exception:
                    pass
        except BlockingIOError:
            pass  # no data yet, ignore
        except Exception as e:
            logger.error(f"[RTP] recvfrom error: {e}")

    async def _recv_loop(self):
        logger.info(f"[RTP] recv_loop STARTED port={self.local_port}")
        while self._running:
            try:
                data, addr = await asyncio.wait_for(self._recv_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue  # just check _running flag
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[RTP] Queue error: {e}")
                continue

            if len(data) <= RTP_HEADER_SIZE:
                continue

            if not self._first_rx:
                logger.info(f"[RTP] ✅ First inbound RTP from {addr} ({len(data)} B)")
                self._first_rx = True

            self._rx += 1
            self._last_rx_ts = time.time()

            if not self._rx_ready:
                continue  # gates closed: agent calls wait for 200 OK, passthrough opens on 183

            pt = data[1] & 0x7F
            payload = data[RTP_HEADER_SIZE:]

            try:
                # Decoded inline, not via asyncio.to_thread. The decode costs ~2 ms per 50 ms of
                # audio, so the thread hop cost more than the work it offloaded — and because
                # every bridge ran its own event loop, each one also brought up its own default
                # ThreadPoolExecutor (min(32, cpu+4) threads). At a dozen concurrent calls that
                # was hundreds of threads contending for the GIL to do microseconds of work each.
                pcm48, self._hp_zi = _decode_rtp_payload(payload, pt, self._hp_zi)
                if not pcm48:
                    continue
                frame = rtc.AudioFrame(
                    data=pcm48,
                    sample_rate=SAMPLE_RATE_LK,
                    num_channels=1,
                    samples_per_channel=len(pcm48) // 2,
                )
                await self._audio_source.capture_frame(frame)
            except Exception as e:
                logger.error(f"[RTP] Decode error: {e}", exc_info=True)

    def add_outbound_track(self, track: rtc.Track):
        """Subscribe to an audio track and feed it into the mixer."""
        stream = rtc.AudioStream(track, sample_rate=SAMPLE_RATE_LK, num_channels=1)
        self._track_streams.append(stream)

        # Wrap AudioStream (yields AudioFrameEvent) as AsyncIterator[AudioFrame]
        async def _frame_iter() -> AsyncIterator[rtc.AudioFrame]:
            async for event in stream:
                yield event.frame

        self._mixer.add_stream(_frame_iter())
        logger.info(f"[RTP] Added track to outbound mixer (total={len(self._track_streams)})")

    def start_outbound_mixer(self):
        """Start the task that reads mixed audio and sends it as RTP."""
        if self._mixer_task is None:
            self._mixer_task = asyncio.create_task(self._mixer_to_rtp_loop())
            logger.info("[RTP] Outbound mixer loop started")

    async def _mixer_to_rtp_loop(self):
        """Read mixed frames from AudioMixer and forward them to RTP."""
        try:
            async for frame in self._mixer:
                await self.send_to_rtp(frame)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[RTP] Mixer loop error: {e}", exc_info=True)

    async def send_to_rtp(self, frame: rtc.AudioFrame):
        """Send mixed audio to remote RTP. Buffers if SIP not yet answered."""
        if not self._tx_ready:
            self._frame_buffer.append(frame)
            return
        # Flush buffer once (after set_remote_endpoint called)
        while self._frame_buffer:
            await self._send_frame(self._frame_buffer.popleft())
            await asyncio.sleep(0)  # yield between frames so concurrent bridges aren't starved
        await self._send_frame(frame)

    async def _send_frame(self, frame: rtc.AudioFrame):
        """Accumulate PCM until we have 20ms, then send one RTP packet.

        Why: SDP advertises a=ptime:20. Exotel expects 160-byte G.711 payloads
        (20ms @ 8kHz). LiveKit produces 10ms frames (80 bytes). Sending 10ms
        packets causes Exotel to drop them → caller hears silence.
        We buffer until we have exactly 320 bytes of 8kHz 16-bit PCM (= 20ms),
        then encode and send one correctly-sized packet.
        """
        if not self._tx_ready or not self._remote_addr:
            return
        try:
            raw = bytes(frame.data.cast("b"))
            samples_48k = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            samples_48k = np.tanh(samples_48k * 0.7)      # soft limit — prevents SIP distortion

            # Stateful polyphase downsampling (48 kHz -> 8 kHz, up=1, down=6)
            # Prepend history of 120 samples to avoid left-edge filter boundary transients.
            full_input = np.concatenate([self._outbound_resample_history, samples_48k])
            self._outbound_resample_history = full_input[-len(self._outbound_resample_history):]

            resampled_full = resample_poly(full_input, 1, 6, window=_RESAMPLE_FILTER)

            # Group delay is 60 samples at high-rate. Align output:
            start_idx = (len(self._outbound_resample_history) - 60) // 6
            end_idx = start_idx + len(samples_48k) // 6
            samples_8k = resampled_full[start_idx:end_idx]

            pcm8 = (samples_8k * 32767.0).astype(np.int16).tobytes()
            self._pcm_accumulator.extend(pcm8)

            # Send one packet per full 20ms chunk; discard any remainder
            # (remainder is < 10ms and will be completed by the next frame)
            while len(self._pcm_accumulator) >= self._PTIME_BYTES:
                chunk = bytes(self._pcm_accumulator[: self._PTIME_BYTES])
                del self._pcm_accumulator[: self._PTIME_BYTES]

                payload = (
                    audioop.lin2alaw(chunk, 2)
                    if self.negotiated_pt == PCMA_PAYLOAD_TYPE
                    else audioop.lin2ulaw(chunk, 2)
                )

                # Timestamp advances by exactly 160 samples (20ms @ 8kHz)
                self._rtp_seq = (self._rtp_seq + 1) & 0xFFFF
                self._rtp_ts = (self._rtp_ts + 160) & 0xFFFFFFFF
                hdr = struct.pack(
                    "!BBHII",
                    0x80,
                    self.negotiated_pt,
                    self._rtp_seq,
                    self._rtp_ts,
                    self._rtp_ssrc,
                )
                self._sock.sendto(hdr + payload, self._remote_addr)
                self._tx += 1

                if not self._first_tx:
                    logger.info(
                        f"[RTP] ✅ First outbound RTP sent to {self._remote_addr} "
                        f"(payload={len(payload)}B = 20ms ✓)"
                    )
                    self._first_tx = True
        except Exception as e:
            logger.error(f"[RTP] Send error: {e}")

    async def close_streams(self):
        """Explicitly unsubscribe all AudioStreams from the FFI queue.

        Must be called before room.disconnect() / loop close. The FFI client is a
        process-wide singleton — under load, its native thread can't drain a closing
        bridge's subscriptions fast enough, causing 'Event loop is closed' floods.
        aclose() removes each stream from the FFI queue synchronously so nothing is
        left to drain.
        """
        for stream in self._track_streams:
            try:
                await stream.aclose()
            except Exception:
                pass
        self._track_streams.clear()

    def stop(self):
        self._running = False
        # Cancel the mixer output loop
        if self._mixer_task and not self._mixer_task.done():
            self._mixer_task.cancel()
        try:
            loop = asyncio.get_running_loop()
            loop.remove_reader(self._sock.fileno())
        except RuntimeError:
            # no running loop (test teardown / late cleanup) — skip
            pass
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
        logger.info(f"[RTP] Stopped | RX={self._rx} TX={self._tx}")
        if self._rx == 0:
            logger.warning(
                "[RTP] ⚠️  ZERO inbound packets! Likely causes:\n"
                "  1. EXOTEL_MEDIA_IP='%s' is wrong — must be EC2 Elastic/Public IP\n"
                "  2. UDP port %d not open in Security Group for Exotel media IPs\n"
                "  3. Port conflicts with another service (LiveKit SIP uses 10000-40000 — stay out of that range!)\n"
                "  4. Exotel routing to wrong destination",
                self._public_ip,
                self.local_port,
            )

    def seconds_since_rx(self) -> float | None:
        if self._last_rx_ts is None:
            return None
        return time.time() - self._last_rx_ts

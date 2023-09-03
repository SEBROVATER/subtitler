import asyncio
import os
from operator import itemgetter

import dotenv
import pyaudio
from deepgram import Deepgram

from general_utils.loggers import get_logger
from general_utils.utils import GracefulKiller


class Subtitler:
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK = 8000
    LOGGER = get_logger("subtitler", False)

    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self.killer = GracefulKiller()
        self.current_sentence = list()
        dotenv.load_dotenv()
        self.api_key = os.environ["API_KEY"]

    def mic_callback(self, input_data, frame_count, time_info, status_flag):
        self.audio_queue.put_nowait(input_data)
        return (input_data, pyaudio.paContinue)

    def transcribe_callback(self, data):
        best_transcript = self.get_best_transcript(data)
        if not best_transcript:
            return
        print(best_transcript, end="\n" if data["is_final"] else "\r")

    @staticmethod
    def get_best_transcript(data):
        return max(data["channel"]["alternatives"], key=itemgetter("confidence"))["transcript"]
        # return tuple(d["transcript"] for d in data["channel"]["alternatives"])

    async def start(self):
        dg_client = Deepgram(self.api_key)
        try:
            self.deepgramLive = await dg_client.transcription.live(
                {
                    "model": "base",
                    "punctuate": False,
                    "interim_results": False,
                    "language": "ru",
                    "encoding": "linear16",
                    "sample_rate": self.RATE,
                    "channels": self.CHANNELS,
                    "endpointing": 100,
                }
            )
        except Exception:
            self.LOGGER.exception(f"Could not open socket")
            return

        try:
            self.deepgramLive.registerHandler(
                self.deepgramLive.event.OPEN,
                lambda msg: self.LOGGER.info(f"WS connection established: {msg}"),
            )
            self.deepgramLive.registerHandler(
                self.deepgramLive.event.ERROR,
                lambda msg: self.LOGGER.info(f"Error in WS connection: {msg}"),
            )

            self.deepgramLive.registerHandler(
                self.deepgramLive.event.CLOSE,
                lambda code: self.LOGGER.info(f"Connection closed with code {code}"),
            )
            self.deepgramLive.registerHandler(
                self.deepgramLive.event.TRANSCRIPT_RECEIVED, self.transcribe_callback
            )
        except Exception:
            self.LOGGER.exception(f"Could not add handlers to connection socket")
            await self.deepgramLive.finish()
            return

        mic_task = asyncio.create_task(self.read_microphone())
        sender_task = asyncio.create_task(self.sender())

        await mic_task
        await sender_task

    async def sender(self):
        try:
            while self.killer.is_running:
                mic_data = await self.audio_queue.get()
                self.deepgramLive.send(mic_data)

            self.LOGGER.info("Stop sending data")
            await asyncio.sleep(0.5)
        except Exception as exc:
            self.LOGGER.error(f"Error while sending data")
            raise exc

        finally:
            await self.deepgramLive.finish()

    async def read_microphone(self):
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.mic_callback,
        )

        stream.start_stream()

        while stream.is_active() and self.killer.is_running:
            await asyncio.sleep(0.1)

        self.LOGGER.info("Stop reading microphone")
        await asyncio.sleep(0.5)
        stream.stop_stream()
        stream.close()


if __name__ == "__main__":
    asyncio.run(Subtitler().start())

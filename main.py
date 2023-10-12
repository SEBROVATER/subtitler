import os

import grpc
import pyaudio
from dotenv import load_dotenv

import yandex.cloud.ai.stt.v3.stt_pb2 as stt_pb2
import yandex.cloud.ai.stt.v3.stt_service_pb2_grpc as stt_service_pb2_grpc
from general_utils.loggers import get_logger
from general_utils.utils import GracefulKiller

LOGGER = get_logger(__name__)


class Subtitler:
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    SAMPLE_RATE = 8000
    CHUNK = 4096
    RECORD_SECONDS = 30
    PROFANITY_FILTER = False
    LITERATURE_TEXT = False

    def __init__(self):
        load_dotenv()
        self.secret = os.environ.get("YANDEX_API_KEY", None)
        if self.secret is None:
            raise

        self.killer = GracefulKiller()

    def generate_samples(self):
        audio = pyaudio.PyAudio()
        try:
            recognize_options = stt_pb2.StreamingOptions(
                recognition_model=stt_pb2.RecognitionModelOptions(
                    audio_format=stt_pb2.AudioFormatOptions(
                        raw_audio=stt_pb2.RawAudio(
                            audio_encoding=stt_pb2.RawAudio.LINEAR16_PCM,
                            sample_rate_hertz=self.SAMPLE_RATE,
                            audio_channel_count=self.CHANNELS,
                        )
                    ),
                    text_normalization=stt_pb2.TextNormalizationOptions(
                        text_normalization=stt_pb2.TextNormalizationOptions.TEXT_NORMALIZATION_ENABLED,
                        profanity_filter=self.PROFANITY_FILTER,
                        literature_text=self.LITERATURE_TEXT,
                    ),
                    language_restriction=stt_pb2.LanguageRestrictionOptions(
                        restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                        language_code=["ru-RU"],
                    ),
                    audio_processing_type=stt_pb2.RecognitionModelOptions.REAL_TIME,
                )
            )

            LOGGER.debug("Send settings")
            yield stt_pb2.StreamingRequest(session_options=recognize_options)

            LOGGER.debug("Start recording")
            stream = audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.SAMPLE_RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
            )
            try:
                frames = []

                while self.killer.is_running:
                    data = stream.read(self.CHUNK)
                    yield stt_pb2.StreamingRequest(chunk=stt_pb2.AudioChunk(data=data))
                    frames.append(data)

                LOGGER.debug("Recognition finished")

            finally:
                stream.stop_stream()
                stream.close()
        finally:
            audio.terminate()

    def run(self):
        LOGGER.debug("Establishing connection with server")
        cred = grpc.ssl_channel_credentials()
        channel = grpc.secure_channel("stt.api.cloud.yandex.net:443", cred)
        stub = stt_service_pb2_grpc.RecognizerStub(channel)

        LOGGER.debug("Send data for recognition")
        it = stub.RecognizeStreaming(
            self.generate_samples(), metadata=(("authorization", f"Api-Key {self.secret}"),)
        )

        LOGGER.debug("Get responses and display them")
        try:
            prev_type = None
            for r in it:
                event_type = r.WhichOneof("Event")

                match event_type:
                    case "partial":
                        if len(r.partial.alternatives) == 0:
                            continue

                        if prev_type in {"final", "final_refinement"}:
                            print()
                        alternatives = r.partial.alternatives
                        text = " ".join(a.text for a in alternatives)

                    case "final":
                        alternatives = r.final.alternatives
                        text = " ".join(a.text for a in alternatives)

                    case "final_refinement":
                        alternatives = r.final_refinement.normalized_text.alternatives
                        text = " ".join(a.text for a in alternatives)

                    case "status_code":
                        continue
                    case "eou_update":
                        continue
                    case None:
                        return
                    case _:
                        LOGGER.warning(f"Unexpected event type {event_type}. Skip it")
                        continue
                print(text, end="\r")
                prev_type = event_type

        except grpc._channel._Rendezvous as err:
            LOGGER.exception(f"Error code {err._state.code}, message: {err._state.details}")
            raise err


if __name__ == "__main__":
    subtitler = Subtitler()
    subtitler.run()

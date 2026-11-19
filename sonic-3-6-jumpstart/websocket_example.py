#!/usr/bin/env python3
"""Stream text to a Sonic 3.6 SageMaker endpoint over the WebSocket (bidirectional) API.

Sends one sentence at a time into a single context, the way an LLM hands text to a
voice agent, and writes the audio to a WAV file. See WEBSOCKET.md for the protocol.

Setup (Python 3.12 or newer):
    pip install "aws-sdk-sagemaker-runtime-http2[awscrt]==0.13.1"

Run:
    python websocket_example.py --endpoint-name sonic-3-6 --region us-east-2

AWS credentials come from the usual places: environment variables, the shared
config and credentials files, or the role attached to the instance or notebook.
"""

import argparse
import asyncio
import base64
import json
import time
import uuid
import wave

from aws_sdk_sagemaker_runtime_http2.aio.client import AsyncSageMakerRuntimeHTTP2Client
from aws_sdk_sagemaker_runtime_http2.aio.config import AsyncSageMakerRuntimeHTTP2Config
from aws_sdk_sagemaker_runtime_http2.models import (
    InvokeEndpointWithBidirectionalStreamInput,
    RequestPayloadPart,
    RequestStreamEventPayloadPart,
    ResponseStreamEventPayloadPart,
)
from smithy_http.aio.crt import AWSCRTHTTPClient

VOICE_ID = "bf0a246a-8642-498a-9950-80c35e9276b5"
SAMPLE_RATE = 44100

# Text arriving in pieces. Each piece is one message on the same context, so the
# model voices them as one continuous utterance.
SENTENCES = [
    "Thanks for calling. ",
    "I found your order, ",
    "and it shipped this morning. ",
    "Is there anything else I can help you with?",
]


async def open_stream(endpoint_name: str, region: str):
    """Open one bidirectional stream. It can carry many contexts, one after another or at once."""
    config = await AsyncSageMakerRuntimeHTTP2Config.resolve(
        region=region,
        # The bidirectional API needs HTTP/2 with both directions open at the same time,
        # which the AWS CRT transport provides. The SDK's default transport does not.
        transport=AWSCRTHTTPClient(),
    )
    client = AsyncSageMakerRuntimeHTTP2Client(config=config)
    return await client.invoke_endpoint_with_bidirectional_stream(
        InvokeEndpointWithBidirectionalStreamInput(endpoint_name=endpoint_name)
    )


async def send(stream, message: dict) -> None:
    """Send one JSON message. One message is one payload part."""
    part = RequestPayloadPart(
        bytes_=json.dumps(message).encode("utf-8"),
        data_type="UTF8",
        completion_state="COMPLETE",
    )
    await stream.input_stream.send(RequestStreamEventPayloadPart(value=part))


async def events(output_stream):
    """Yield each event the endpoint sends. One payload part is one JSON event."""
    while True:
        event = await output_stream.receive()
        if event is None:
            return
        if not isinstance(event, ResponseStreamEventPayloadPart):
            # SageMaker ended the stream itself: ModelStreamError or InternalStreamFailure.
            raise RuntimeError(f"stream failed: {event.value}")
        if event.value.bytes_:
            yield json.loads(event.value.bytes_)


async def main(endpoint_name: str, region: str, output_file: str) -> None:
    stream = await open_stream(endpoint_name, region)
    context_id = str(uuid.uuid4())
    started = time.perf_counter()

    async def send_text() -> None:
        for index, sentence in enumerate(SENTENCES):
            message = {
                "context_id": context_id,
                "transcript": sentence,
                # true: more text is coming. false on the last message ends the context.
                "continue": index < len(SENTENCES) - 1,
            }
            if index == 0:
                # The first message of a context sets the voice and the output format.
                message.update(
                    {
                        "language": "en",
                        "voice": {"mode": "id", "id": VOICE_ID},
                        "output_format": {
                            "container": "raw",
                            "encoding": "pcm_s16le",
                            "sample_rate": SAMPLE_RATE,
                        },
                        "add_timestamps": True,
                    }
                )
            await send(stream, message)
            await asyncio.sleep(0.2)  # stand-in for waiting on the next piece of text

    sender = asyncio.create_task(send_text())
    _, output_stream = await stream.await_output()

    audio = bytearray()
    characters_billed = 0
    first_audio_ms = None
    async for event in events(output_stream):
        kind = event["type"]
        if kind == "chunk":
            if first_audio_ms is None:
                first_audio_ms = (time.perf_counter() - started) * 1000
            audio.extend(base64.b64decode(event["data"]))
        elif kind == "usage":
            # What the message you just sent is billed. Add these up for your own records.
            characters_billed += event["characters_billed"]
        elif kind == "timestamps":
            print("words:", " ".join(event["word_timestamps"]["words"]))
        elif kind == "done":
            # The context is finished. Its total matches the usage events added up.
            print("context total:", event["server_metrics"]["characters_billed"], "characters")
            break
        elif kind == "error":
            raise RuntimeError(f"{event['status_code']}: {event['error']}")
        # Skip any type you do not handle, such as flush_done.

    await sender
    await stream.input_stream.close()

    with wave.open(output_file, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(audio))

    seconds = len(audio) / (SAMPLE_RATE * 2)
    print(f"time to first audio: {first_audio_ms:.0f} ms")
    print(f"characters billed: {characters_billed} ({characters_billed / 1000} inference units)")
    print(f"saved {output_file} ({seconds:.2f} s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--output", default="websocket_output.wav")
    args = parser.parse_args()
    asyncio.run(main(args.endpoint_name, args.region, args.output))

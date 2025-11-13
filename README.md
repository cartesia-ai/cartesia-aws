# Sonic 3 Models on Sagemaker Jumpstart

###  Input Summary

The response streaming endpoint takes in a JSON object as the input that specifies the transcript, voice, language, and output format for the generation

### Input Parameters

| **Parameter** | **Description** | **Type** | **Required** |
|----------------|-----------------|-----------|---------------|
| **client_side_request_id** | A unique ID provided by the client to identify the request. It can be any string value and helps with tracking or debugging. | `string` | ✅ Yes |
| **transcript** | The text that will be converted into speech. You can include additional controls (e.g., emotion, speed, volume) as supported by [Sonic 3 models](https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion). | `string` | ✅ Yes |
| **language** | The language code of the transcript text. Supported codes include: <br> `en`, `fr`, `de`, `es`, `pt`, `zh`, `ja`, `hi`, `it`, `ko`, `nl`, `pl`, `ru`, `sv`, `tr`, `tl`, `bg`, `ro`, `ar`, `cs`, `el`, `fi`, `hr`, `ms`, `sk`, `da`, `ta`, `uk`, `hu`, `no`, `vi`, `bn`, `th`, `he`, `ka`, `id`, `te`, `gu`, `kn`, `ml`, `mr`, `pa` | `string` | ✅ Yes |
| **output_format** | The format of the generated audio file. The output format is always of the form `{format}_{sample_rate}`. Supported options: <br>• `pcme_44100` – PCM encoding at 44.1 kHz (high-quality audio) <br>• `mulaw_8000` – μ-law encoding at 8 kHz (telephone-quality audio) | `string` | ✅ Yes |
| **voice_id** | The ID of the voice to be used for speech synthesis. Refer to the [Choosing a Voice guide](https://docs.cartesia.ai/build-with-cartesia/capability-guides/choosing-a-voice) for available voices and customization options. | `string` | ✅ Yes |

### Data Sample

```
{
    "client_side_request_id": "0",
    "transcript": "The detective burst through the door. 'We've got maybe five minutes before they realize we're here, so listen carefully and listen well: <speed ratio='1.5'/> the artifact is hidden beneath the old courthouse, exactly three feet below the cornerstone, and <volume ratio='0.5'/>whatever you do, DO NOT touch it with your bare hands!' She paused, catching her breath. 'Now... here's the important part... <speed ratio='0.6'/>you need to... very slowly... very carefully... wrap it in the copper wire first... then the silk cloth... then seal it in the lead box.' <volume ratio='2.0'/> Footsteps echoed in the hallway. 'GO GO GO! They're coming up the stairs RIGHT NOW!'",
    "language": "en",
    "output_format": "pcm_44100",
    "voice_id": "bf0a246a-8642-498a-9950-80c35e9276b5",
}
```

### Output Details

#### Output Events

Sagemaker sends back the response events in a [Response Stream](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_ResponseStream.html). The payload is sent to you as base 64 encoded blobs. Due to Sagemaker limitation, it may truncate one event into several segements. Or API always attach a linebreak to the end of each complete event, such that you can reconciliate them on client side. Each event we send back is a json object that contains the generated audio chunk and some metadatas. The event can be one of the following types, identified by `event.type`:

##### Chunk Event

A chunk event always contains at most 20 ms worth of audio chunk in the output format and sample rate you specified.

| **Parameter** | **Description** | **Type** | **Required** |
|----------------|-----------------|-----------|---------------|
| **type** | The type of response event. For chunk events, this value is always `"chunk"`. | `string` | ✅ Yes |
| **context_id** | Optional identifier for the response context. Useful for correlating responses with requests or sessions. | `string` | ❌ No |
| **status_code** | The HTTP-like status code representing the success or error state of the chunk event. | `int` | ✅ Yes |
| **done** | Indicates whether this is the final chunk (`true`) or if more chunks are expected (`false`). | `bool` | ✅ Yes |
| **data** | The base 64 encoded chunk of audio data. Each chunk represents a portion of the full audio output. | `string` | ✅ Yes |
| **sampling_rate** | The sampling rate (in Hz) of the audio data in this chunk (e.g., `44100` or `8000`). | `int` | ✅ Yes |
| **step_time** | The time (in seconds) representing the generation step for this chunk, useful for synchronization or latency tracking. | `float` | ✅ Yes |

##### Done Event

A done event signals the completion of the generation. Done events are identified by `event.type == "done"` and `event.done == True`.

### Error Handling

If an error occurs during the generation type, Sagemaker will send back the error as a [Model Error](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpoint.html#API_runtime_InvokeEndpoint_ResponseElements:~:text=Status%20Code%3A%20500-,ModelError,-Model%20(owned%20by)). To handle the error, you may inspect the `OriginalStatusCode` field of the error object (See examples for error handling in python).

#### 422 Errors

A 422 error indicates that your input is not of the correct format. You may see more details in the `Messsage` field.

#### 429 Errors

A 429 error indicates that the model container you are hitting does not have capacity to serve requests at the point. Our models serve at most 4 concurrent generation requests at a time. If you are running multiple inference container replicas, we suggest that you use load-aware routing in sagemaker by configuring the parameters `RoutingConfig` inside the `ProductionVariants` configuration, Set it to `LEAST_OUTSTANDING_REQUESTS` for optimal load distribution.

### Container Logs

You should be able to see container logs in cloudwatch. Most logs should be emitted with a request id. The server side request id is of the format `{uuid}-{client supplied request id}`.

### Performance Optimization

In order to get the best performance, Sagemaker suggests that you reuse the client-to-SageMaker connection, as it can save the time to re-establish the connection. In boto3, you can configure max_pool_connections . Multiple requests will reuse the connections, which avoids the cost of establishing new TCP/TLS connections for each request.

### Example

A sample python client to call our Sagemaker API using the boto3 client

```python
import asyncio
import base64
import json
import time
import wave
from typing import Generator, Iterable, List
import os

import boto3

AWS_REGION = os.environ['AWS_REGION']
ENDPOINT_NAME = os.environ['ENDPOINT_NAME']

sagemaker_runtime = boto3.client("sagemaker-runtime", region_name=AWS_REGION)


def events_from_aws_stream(eventstream: Iterable[dict]) -> Generator[dict, None, None]:
    """
    Convert SageMaker event stream (InvokeEndpointWithResponseStream) into json events
    """
    buffered_text = ""
    for event in eventstream:
        if "PayloadPart" in event:
            chunk_bytes = event["PayloadPart"]["Bytes"]
            chunk_text = chunk_bytes.decode("utf-8")
            if chunk_text.endswith("\n"):
                yield json.loads(buffered_text + chunk_text)
                buffered_text = ""
            else:
                buffered_text += chunk_text
        elif "ModelStreamError" in event:
            err = event["ModelStreamError"]
            raise RuntimeError(f"ModelStreamError: {err.get('ErrorCode')}: {err.get('Message')}")
        elif "InternalStreamFailure" in event:
            raise RuntimeError("InternalStreamFailure from SageMaker")
        else:
            # Unknown event type; ignore or log
            continue


async def get_tts_chunks_async():
    def sync_stream():
        """Invokes the AWS response streaming endpoint and returns processed responses from aws event stream"""
        body_str = json.dumps(
            {
                "transcript": """
            The detective burst through the door. "We've got maybe five minutes before they realize we're here, so listen carefully and listen well: <speed ratio='1.5'/> the artifact is hidden beneath the old courthouse, exactly three feet below the cornerstone, and <volume ratio='0.5'/>whatever you do, DO NOT touch it with your bare hands!" She paused, catching her breath. "Now... here's the important part... <speed ratio='0.6'/>you need to... very slowly... very carefully... wrap it in the copper wire first... then the silk cloth... then seal it in the lead box." <volume ratio='2.0'/> Footsteps echoed in the hallway. "GO GO GO! They're coming up the stairs RIGHT NOW!"
                    """,
                "language": "en",
                "voice_id": "bf0a246a-8642-498a-9950-80c35e9276b5",
                "output_format": "pcm_44100",
                "client_side_request_id": "1",
            }
        )

        request_start_time = time.perf_counter()
        response = sagemaker_runtime.invoke_endpoint_with_response_stream(
            EndpointName=ENDPOINT_NAME,
            Body=body_str,
            ContentType="application/json",
            Accept="text/event-stream",
        )
        print(
            f"[METRIC] InvokeEndpointWithResponseStream request time: {time.perf_counter() - request_start_time:.3f}s"
        )
        print(response)

        event_stream = response.get("Body")
        return events_from_aws_stream(event_stream)

    audio_chunks = []
    start_time = time.perf_counter()
    first_chunk_time = None

    async def consume_events():
        nonlocal first_chunk_time

        # Run the synchronous generator in a background thread
        # Process response events and extract audio chunks
        for chunk in await asyncio.to_thread(sync_stream):
            if chunk["type"] == "chunk":
                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter()
                    ttfa = first_chunk_time - start_time
                    print(f"[METRIC] Time to first audio: {ttfa:.3f}s")

                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "done":
                print("[LOG] Stream finished.")
            elif chunk["type"] == "error":
                print(f"[ERROR] {chunk['data']}")

    try:
        await consume_events()
    except sagemaker_runtime.exceptions.ModelError as e:
        print(e.response['Message'])
        print(e.response["OriginalStatusCode"])

    # Calculate full stream time
    total_time = time.perf_counter() - start_time
    print(f"[METRIC] Total TTS stream time: {total_time:.3f}s")

    return audio_chunks


def save_audio_chunks_to_wav(
    chunks: List[str], output_file: str = "output.wav", sample_rate: int = 44100
):
    """Decode base64 audio chunks and save as WAV file."""
    combined_audio = bytearray()
    for chunk_data in chunks:
        audio_bytes = base64.b64decode(chunk_data)
        combined_audio.extend(audio_bytes)

    with wave.open(output_file, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(combined_audio)

    file_size = len(combined_audio)
    duration = len(combined_audio) / (sample_rate * 2)  # 16-bit = 2 bytes per sample
    print(f"[LOG] Saved WAV: {output_file} ({file_size} bytes, {duration:.2f}s)")
    return file_size, duration


async def main():
    chunks = await get_tts_chunks_async()
    save_audio_chunks_to_wav(chunks, output_file="output.wav")


if __name__ == "__main__":
    asyncio.run(main())
```
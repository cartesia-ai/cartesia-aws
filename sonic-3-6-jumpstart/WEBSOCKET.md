# Sonic 3.6 WebSocket API on SageMaker JumpStart

The WebSocket API lets you send text to a Sonic 3.6 endpoint a piece at a time and receive audio while you are still sending. Use it when your text arrives incrementally, for example from an LLM in a voice agent, and you want it spoken as one continuous utterance.

When the full text is known up front, the response streaming endpoint described in the [README](./README.md) is simpler.

### Getting Started

For a complete client that streams text into the endpoint, adds up the usage and saves the audio, please refer to [websocket_example.py](./websocket_example.py)

```bash
pip install "aws-sdk-sagemaker-runtime-http2[awscrt]==0.13.1"
python websocket_example.py --endpoint-name sonic-3-6 --region us-east-2
```

You will need:

- A Sonic 3.6 endpoint deployed from a model package version that supports bidirectional streaming.
- IAM permission to invoke the endpoint. AWS recommends allowing `sagemaker:InvokeEndpoint*`.
- Python 3.12 or newer and the AWS SDK package above. It implements SageMaker's [InvokeEndpointWithBidirectionalStream](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpointWithBidirectionalStream.html) API, which `boto3` does not support. The package is pre-1.0 and has renamed modules between releases, so pin the version.

Every client opens a stream, sends messages on it, and reads events from it:

```python
import json

from aws_sdk_sagemaker_runtime_http2.aio.client import AsyncSageMakerRuntimeHTTP2Client
from aws_sdk_sagemaker_runtime_http2.aio.config import AsyncSageMakerRuntimeHTTP2Config
from aws_sdk_sagemaker_runtime_http2.models import (
    InvokeEndpointWithBidirectionalStreamInput,
    RequestPayloadPart,
    RequestStreamEventPayloadPart,
    ResponseStreamEventPayloadPart,
)
from smithy_http.aio.crt import AWSCRTHTTPClient


async def open_stream(endpoint_name: str, region: str):
    config = await AsyncSageMakerRuntimeHTTP2Config.resolve(
        region=region,
        transport=AWSCRTHTTPClient(),  # required: the default transport cannot stream both ways
    )
    client = AsyncSageMakerRuntimeHTTP2Client(config=config)
    return await client.invoke_endpoint_with_bidirectional_stream(
        InvokeEndpointWithBidirectionalStreamInput(endpoint_name=endpoint_name)
    )


async def send(stream, message: dict) -> None:
    part = RequestPayloadPart(
        bytes_=json.dumps(message).encode("utf-8"),
        data_type="UTF8",
        completion_state="COMPLETE",
    )
    await stream.input_stream.send(RequestStreamEventPayloadPart(value=part))


async def events(output_stream):
    while True:
        event = await output_stream.receive()
        if event is None:
            return
        if not isinstance(event, ResponseStreamEventPayloadPart):
            raise RuntimeError(f"stream failed: {event.value}")
        if event.value.bytes_:
            yield json.loads(event.value.bytes_)
```

Send one JSON message per payload part, marked `COMPLETE`. A part marked `PARTIAL` is held by SageMaker until a `COMPLETE` part follows.

### Inference Setup

Use the same instance type as the response streaming endpoint (see [Inference Setup](./README.md#inference-setup)).

A stream is one connection to the model. Keep it open and reuse it: opening a stream adds a few hundred milliseconds to the first audio, which later requests on the same stream do not pay.

Text is sent in contexts. A context is one utterance, identified by a `context_id` you choose. Every message with the same `context_id` adds text to it, and the model keeps the voice and prosody continuous across those messages. One stream can carry many contexts, one after another or at the same time.

Each open context counts as one concurrent request on the instance, from the same limit the response streaming endpoint uses.

A context ends when one of the following happens. In each case you receive a [done event](#done-event).

- You send a message with `"continue": false`. The remaining audio is sent first.
- You send a message with `"cancel": true`. Generation stops.
- The context has no text left to speak and receives none for a few seconds.

After a context ends, a message with the same `context_id` starts a new context.

### Input Summary

Each message is a JSON object. The first message of a context specifies the transcript, voice, language, and output format, as on the response streaming endpoint. Later messages on the same context only need the `context_id`, the next piece of `transcript`, and `continue`.

### Input Parameters

| **Parameter** | **Description** | **Type** | **Required** |
|---------------|-----------------|-----------|---------------|
| **context_id** | Identifies the context. Messages with the same ID are spoken as one utterance. Letters, digits, hyphens, underscores and colons only. | `string` | ✅ Yes |
| **transcript** | The text to add to the context. Messages are joined exactly as written, so include the spaces and punctuation that belong between them. You can include additional controls (e.g., emotion, speed, volume) as supported by Sonic 3.6 models: https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion | `string` | ✅ First message |
| **continue** | Set to `true` if more text will follow on this context. `false` ends the context after this message. Defaults to false. | `boolean` | ❌ No |
| **flush** | Generate everything received so far now, without waiting for more text. Answered with a [flush done event](#flush-done-event) once that audio has been sent. | `boolean` | ❌ No |
| **cancel** | Stop the context. Send it with only `context_id`. | `boolean` | ❌ No |
| **max_buffer_delay_ms** | How long the model waits for more text before speaking an unfinished fragment. Text that completes a sentence is spoken right away. `0` to `5000`. Defaults to 3000. | `int` | ❌ No |
| **voice** | Matches the `voice` field of the response streaming endpoint. Only **mode = `id`** is supported. Example: `{ "mode": "id", "id": "voice_123" }` | `object` | ✅ First message |
| **output_format** | Matches the `output_format` field of the response streaming endpoint. Only `raw` is supported. | `object` | ✅ First message |
| **language** | The language code of the transcript text. Supports the same codes as the response streaming endpoint. | `string` | ❌ No |
| **generation_config** | Optional configuration object matching the API schema: https://docs.cartesia.ai/api-reference/tts/sse#body-generation-config | `object` | ❌ No |
| **add_timestamps** | Whether to include word-level timestamps in the output. | `boolean` | ❌ No |
| **use_normalized_timestamps** | Whether word timestamps should refer to the normalized text the model spoke rather than the text you sent. | `boolean` | ❌ No |
| **pronunciation_map** | A dictionary mapping words or phrases to plain-text pronunciations. See [Pronunciation Dictionary](./README.md#pronunciation-dictionary). | `object` | ❌ No |

`output_format`, `add_timestamps`, `use_normalized_timestamps` and `pronunciation_map` are fixed by the first message of a context. Start a new context to change them.

`include_history` and `history` are not accepted. They carry continuity between separate response streaming requests; a context already does that across its messages.

For more background on how text is buffered and flushed, the Cartesia docs have guides on [contexts](https://docs.cartesia.ai/use-the-api/tts-websocket/contexts), [buffering](https://docs.cartesia.ai/use-the-api/tts-websocket/buffering) and [flushing](https://docs.cartesia.ai/use-the-api/tts-websocket/context-flushing-and-flush-i-ds).

### Data Sample

The first message of a context:

```json
{
    "context_id": "call-42-turn-3",
    "transcript": "Thanks for calling. ",
    "continue": true,
    "language": "en",
    "voice": {
        "mode": "id",
        "id": "bf0a246a-8642-498a-9950-80c35e9276b5"
    },
    "output_format": {
        "container": "raw",
        "sample_rate": 44100,
        "encoding": "pcm_s16le"
    },
    "add_timestamps": true
}
```

More text on the same context:

```json
{
    "context_id": "call-42-turn-3",
    "transcript": "I found your order, ",
    "continue": true
}
```

The last message of the context:

```json
{
    "context_id": "call-42-turn-3",
    "transcript": "and it shipped this morning.",
    "continue": false
}
```

To stop a context early:

```json
{
    "context_id": "call-42-turn-3",
    "cancel": true
}
```

### Output Details

#### Output Events

SageMaker sends back the response events as payload parts on the stream. Each payload part holds exactly one event, a JSON object, so there is no need to reassemble events or look for line breaks as on the response streaming endpoint. Events for different contexts can be interleaved; use `context_id` to tell them apart. The event can be one of the following types, identified by `event.type`. Skip any type you do not handle.

##### Usage Event

A usage event reports what a message is billed. It is sent for every accepted message that carries text, before any audio for that message. See [Usage and Billing](#usage-and-billing).

| **Parameter** | **Description** | **Type** | **Required** |
|----------------|-----------------|-----------|---------------|
| **type** | The type of response event. For usage events, this value is always `"usage"`. | `string` | ✅ Yes |
| **context_id** | The context the message was sent on. | `string` | ✅ Yes |
| **status_code** | Always `200`. | `int` | ✅ Yes |
| **done** | Always `false`. | `bool` | ✅ Yes |
| **characters_billed** | Characters billed for the message you just sent. | `int` | ✅ Yes |
| **context_characters_billed** | Running total for the context, including this message. | `int` | ✅ Yes |

##### Chunk Event

A chunk event contains a chunk of audio in the output format and sample rate you specified. To build the audio, decode and concatenate the `data` of a context's chunk events in the order received.

| **Parameter** | **Description** | **Type** | **Required** |
|----------------|-----------------|-----------|---------------|
| **type** | The type of response event. For chunk events, this value is always `"chunk"`. | `string` | ✅ Yes |
| **context_id** | The context this audio belongs to. | `string` | ✅ Yes |
| **status_code** | The HTTP-like status code of the event. `206` for chunk events. | `int` | ✅ Yes |
| **done** | Always `false`. The end of a context is signalled by a done event. | `bool` | ✅ Yes |
| **data** | The base 64 encoded chunk of audio data. | `string` | ✅ Yes |
| **sampling_rate** | The sampling rate (in Hz) of the audio data in this chunk (e.g., `44100` or `8000`). | `int` | ✅ Yes |
| **step_time** | The time (in milliseconds) the model spent generating this chunk, useful for latency tracking. | `float` | ✅ Yes |
| **flush_id** | Which flush this audio belongs to. Starts at `0` and goes up by one after each flush. | `int` | ✅ Yes |

##### Timestamp Event

A **timestamp event** provides word timings, when `add_timestamps` is set.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"timestamps"`. | `string` | ✅ Yes |
| **context_id** | The context these timestamps belong to. | `string` | ✅ Yes |
| **status_code** | Status code of the event. `206` for timestamp events. | `int` | ✅ Yes |
| **done** | Always `false`. | `bool` | ✅ Yes |
| **word_timestamps** | Three lists of equal length: `words`, and the `start` and `end` time of each word in seconds from the start of the context's audio. | `dict<string, any>` | ✅ Yes |

##### Flush Done Event

A **flush done event** signals that all audio for one flush has been sent.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"flush_done"`. | `string` | ✅ Yes |
| **context_id** | The context that was flushed. | `string` | ✅ Yes |
| **status_code** | Status code of the event. `206` for flush done events. | `int` | ✅ Yes |
| **done** | Always `false`. The context stays open after a flush. | `bool` | ✅ Yes |
| **flush_id** | The `flush_id` carried by the chunk events of this flush. | `int` | ✅ Yes |
| **flush_done** | Always `true`. | `bool` | ✅ Yes |

##### Done Event

A done event signals that a context has ended. No more events will carry its `context_id`. Done events are identified by `event.type == "done"` and `event.done == True`.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"done"`. | `string` | ✅ Yes |
| **context_id** | The context that ended. | `string` | ✅ Yes |
| **status_code** | Always `200`. | `int` | ✅ Yes |
| **done** | Always `true`. | `bool` | ✅ Yes |
| **cancelled** | `true` if the context ended because you cancelled it. | `bool` | ✅ Yes |
| **server_metrics** | Totals for the context: `characters_billed`, `audio_duration_s`, and latency measurements taken on the endpoint. | `dict<string, any>` | ✅ Yes |

##### Event Sample

A context that sends two messages, with a flush after the first, produces the following events. Many chunk events arrive for each message; one is shown for each here.

```
{"type": "usage", "context_id": "ctx-1", "status_code": 200, "done": false, "characters_billed": 12, "context_characters_billed": 12}
{"type": "chunk", "context_id": "ctx-1", "status_code": 206, "done": false, "data": "///9//z//P/5//n/...", "sampling_rate": 44100, "step_time": 30.99, "flush_id": 0}
{"type": "timestamps", "context_id": "ctx-1", "status_code": 206, "done": false, "word_timestamps": {"words": ["Hello"], "start": [0.119], "end": [0.44]}}
{"type": "flush_done", "context_id": "ctx-1", "status_code": 206, "done": false, "flush_id": 0, "flush_done": true}
{"type": "usage", "context_id": "ctx-1", "status_code": 200, "done": false, "characters_billed": 19, "context_characters_billed": 31}
{"type": "chunk", "context_id": "ctx-1", "status_code": 206, "done": false, "data": "AAABAAAAAQAAAAAA...", "sampling_rate": 44100, "step_time": 104.9, "flush_id": 1}
{"type": "done", "context_id": "ctx-1", "status_code": 200, "done": true, "cancelled": false, "server_metrics": {"characters_billed": 31, "server_side_ttfa_ms": 32.692, "model_side_ttfa_ms": 30.996, "server_side_rtf": 2.8147, "audio_duration_s": 2.16}}
```

### Usage and Billing

The endpoint bills by character at the same rate as the response streaming endpoint. One inference unit is 1,000 characters, and units are fractional, so 112 characters is 0.112 units.

To track usage yourself, add up `characters_billed` across the [usage events](#usage-event) you receive and divide by 1,000:

```python
characters_billed = 0
async for event in events(output_stream):
    if event["type"] == "usage":
        characters_billed += event["characters_billed"]
    elif event["type"] == "chunk":
        ...
inference_units = characters_billed / 1000
```

- **Text is billed when it is accepted.** The usage event is sent at that point, ahead of the audio. Cancelling a context, closing the connection, or a context failing afterwards does not refund text already accepted.
- **Messages that are not accepted are not billed.** A message answered with an error and no usage event was not billed.
- **Messages without text are not billed.** A flush or a cancel produces no usage event.
- **The count is of spoken characters.** `<speed/>`, `<volume/>` and `<emotion/>` tags are not counted. Where a `pronunciation_map` entry matches, the replacement text is counted.
- **The done event repeats the total.** `server_metrics.characters_billed` on a context's done event equals the sum of its usage events.

On the response streaming endpoint there are no usage events. The same count comes back once per request, in the response's `CustomAttributes`:

```python
response = sagemaker_runtime.invoke_endpoint_with_response_stream(...)
json.loads(response["CustomAttributes"])  # {"characters_billed": 12, "model_id": "sonic-3.6"}
```

### Error Handling

If an error occurs on a context, the endpoint sends back an error event. An error ends that context only: other contexts on the stream keep running and you can start new ones.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"error"`. | `string` | ✅ Yes |
| **context_id** | The context that failed. `null` when the message could not be read. | `string` | ❌ No |
| **status_code** | The HTTP-like status code of the error. | `int` | ✅ Yes |
| **done** | Always `true`. | `bool` | ✅ Yes |
| **error** | A description of the error. | `string` | ✅ Yes |

```json
{
    "type": "error",
    "context_id": "ctx-7",
    "status_code": 404,
    "done": true,
    "error": "Voice '00000000-0000-0000-0000-000000000000' not found"
}
```

#### 400 Errors

A 400 error indicates that your message is not of the correct format: an unknown field, a first message without `voice` or `output_format`, a fixed field changed mid-context, or a message that is not JSON. You may see more details in the `error` field.

#### 404 Errors

A 404 error indicates that the voice does not exist on this endpoint. Use a voice included in the model package.

#### 429 Errors

A 429 error indicates that the model container you are hitting does not have capacity for another context at this point. Retry after one of your contexts finishes. If you are running multiple inference container replicas, we suggest that you use load-aware routing in SageMaker by configuring the parameters `RoutingConfig` inside the `ProductionVariants` configuration. Set it to `LEAST_OUTSTANDING_REQUESTS` for optimal load distribution.

#### 500 and 503 Errors

A 500 error indicates that the context failed on the endpoint, and a 503 error that the endpoint is not ready to generate. Retry on a new `context_id`.

#### Stream Errors

If SageMaker itself ends the stream, `receive()` returns a `ModelStreamError` or `InternalStreamFailure` event in place of a payload part. Open a new stream.

### Closing the Connection

Wait for the done event of each context, then close your side of the stream:

```python
await stream.input_stream.close()
```

Closing earlier cancels the contexts still open, and audio not yet delivered is lost.

### Coming from the Cartesia API

The messages and events follow the [Cartesia TTS WebSocket](https://docs.cartesia.ai/api-reference/tts/websocket), so an existing client carries over with these changes:

- **Connection.** `InvokeEndpointWithBidirectionalStream` through the AWS SDK with AWS credentials, in place of a `wss://` URL and API key.
- **Usage events.** The usage event exists only here. Ignore it or handle it.
- **Model.** Fixed by the endpoint. `model_id` is optional and must match if sent.
- **Voices.** Only the voices included in the model package.
- **Errors.** The error event carries a single `error` string.

### Container Logs

You should be able to see container logs in CloudWatch. Attach a meaningful `context_id` for tracking purposes.

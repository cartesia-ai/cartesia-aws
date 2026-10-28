# Sonic 3.6 Models on Sagemaker Jumpstart

### Getting Started

For a step by step guide to create your first Sonic 3.6 Inference endpoint on Sagemaker, please refer to [sample notebook](https://github.com/cartesia-ai/cartesia-aws/blob/main/sonic-3-6-jumpstart/Sonic-3-6-Jumpstart.ipynb)

### Inference Setup

Sonic 3.6 supports only real time inference on Sagemaker. Please select `ml.g6e.xlarge` as your inference endpoint instance type. Each instance is capable of serving 10 concurrent requests. In order to get the best performance, Sagemaker suggests that you reuse the client-to-SageMaker connection, as it can save the time to re-establish the connection. In boto3, you can configure max_pool_connections . Multiple requests will reuse the connections, which avoids the cost of establishing new TCP/TLS connections for each request.

###  Input Summary

The response streaming endpoint takes in a JSON object as the input that specifies the transcript, voice, language, and output format for the generation

### Input Parameters

| **Parameter** | **Description** | **Type** | **Required** |
|---------------|-----------------|-----------|---------------|
| **context_id** | A unique ID provided by the client to identify the request. It can be any string value and helps with tracking or debugging. | `string` | ✅ Yes |
| **transcript** | The text that will be converted into speech. You can include additional controls (e.g., emotion, speed, volume) as supported by Sonic 3.6 models: https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion | `string` | ✅ Yes |
| **language** | The language code of the transcript text. Supported codes include: <br> `ar`, `bg`, `bn`, `cs`, `da`, `de`, `el`, `en`, `es`, `fi`, `fr`, `gu`, `he`, `hi`, `hr`, `hu`, `id`, `it`, `ja`, `ka`, `kn`, `ko`, `ml`, `mr`, `ms`, `nl`, `no`, `pa`, `pl`, `pt`, `ro`, `ru`, `sk`, `sv`, `ta`, `te`, `th`, `tl`, `tr`, `uk`, `vi`, `zh`, `en-US`, `de-DE`, `es-MX`, `fr-FR`, `hi-IN`, `it-IT`, `ja-JP`, `nl-NL`, `pt-BR` | `string` | ❌ No |
| **output_format** | Must match the `raw` option from the Cartesia TTS SSE API: https://docs.cartesia.ai/api-reference/tts/sse#body-output-format. Only `raw` is supported. | `string` | ✅ Yes |
| **voice** | Matches the `voice` field from the Cartesia TTS SSE API: https://docs.cartesia.ai/api-reference/tts/sse#body-voice. Only **mode = `id`** is supported. Example: `{ "mode": "id", "id": "voice_123" }` | `object` | ✅ Yes |
| **generation_config** | Optional configuration object matching the API schema: https://docs.cartesia.ai/api-reference/tts/sse#body-generation-config | `object` | ❌ No |
| **add_timestamps** | Whether to include word-level timestamps in the output: https://docs.cartesia.ai/api-reference/tts/sse#body-add-timestamps | `boolean` | ❌ No |
| **add_phoneme_timestamps** | Whether to include phoneme-level timestamps in the output: https://docs.cartesia.ai/api-reference/tts/sse#body-add-phoneme-timestamps | `boolean` | ❌ No |
| **use_normalized_timestamps** | Whether timestamps should be normalized (0–1 range): https://docs.cartesia.ai/api-reference/tts/sse#body-use-normalized-timestamps | `boolean` | ❌ No |
| **pronunciation_map** | A dictionary mapping words or phrases to plain-text pronunciations: https://docs.cartesia.ai/build-with-cartesia/capability-guides/custom-pronunciations. Maximum total size: 16KB (sum of all key and value bytes in UTF-8). See [Pronunciation Dictionary](#pronunciation-dictionary) for details and examples. | `object` | ❌ No |
| **include_history** | Return an encrypted continuation token in the final done event. Defaults to false. See [Continuations](#continuations). | `boolean` | ❌ No |
| **history** | Token from the previous response, passed unchanged to continue speech with the same model and voice. | `string` | ❌ No |



### Pronunciation Dictionary

The `pronunciation_map` parameter lets you override how specific words are spoken. This is useful for:

- **Proper nouns and brand names** that the model may mispronounce (e.g. `"Nguyen"`, `"Xiaomi"`)
- **Acronyms and initialisms** where you want explicit letter-by-letter or expanded pronunciation (e.g. `"AWS"`, `"SQL"`)
- **Domain-specific terms** such as medical, legal, or technical vocabulary
- **IVR and contact center scripts** where consistent, predictable pronunciation is critical

**How it works**: Each key is a word or phrase that may appear in the transcript. When the model finds an exact match, it speaks the alias value in place of the original text. Matching is case-sensitive.

> **Important**: Alias values are read as plain text — IPA phonetic notation is not interpreted as phoneme directives. Use phonetic respellings instead (e.g. `"Nguyen": "Win"`, `"GIF": "jif"`).

**Byte limit**: The combined UTF-8 byte size of all keys and values must not exceed 16KB. This bounds the worst-case expansion of the transcript after substitutions are applied.

#### Example

```json
{
    "context_id": "my-request-001",
    "transcript": "Welcome to Cartesia. Our Sonic 3.6 model delivers ultra-low latency TTS via the API.",
    "language": "en",
    "voice": {
        "mode": "id",
        "id": "bf0a246a-8642-498a-9950-80c35e9276b5"
    },
    "output_format": {
        "container": "raw",
        "sample_rate": 44100,
        "encoding": "pcm_f32le"
    },
    "pronunciation_map": {
        "Cartesia": "Car-TEE-zhuh",
        "Sonic": "SAH-nik",
        "API": "A-P-I"
    }
}
```

### Data Sample

```
{
    "context_id": "0",
    "transcript": "The detective burst through the door. 'We've got maybe five minutes before they realize we're here, so listen carefully and listen well: <speed ratio='1.5'/> the artifact is hidden beneath the old courthouse, exactly three feet below the cornerstone, and <volume ratio='0.5'/>whatever you do, DO NOT touch it with your bare hands!' She paused, catching her breath. 'Now... here's the important part... <speed ratio='0.6'/>you need to... very slowly... very carefully... wrap it in the copper wire first... then the silk cloth... then seal it in the lead box.' <volume ratio='2.0'/> Footsteps echoed in the hallway. 'GO GO GO! They're coming up the stairs RIGHT NOW!'",
    "language": "en",
    "output_format": {
        "container": "raw",
        "sample_rate": 44100,
        "encoding": "pcm_s16le"
    }
    "voice_id": {
        "mode": "id",
        "id": "bf0a246a-8642-498a-9950-80c35e9276b5"
    },
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

A done event signals the completion of the generation. Done events are identified by `event.type == "done"` and `event.done == True`. When you request continuation history, this event also contains an encrypted `history` string. See [Continuations](#continuations).

##### Timestamp Event

A **timestamp event** provides timing information for recognized words or tokens.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"timestamps"`. | `string` | ✅ Yes |
| **context_id** | Optional identifier correlating this timestamp event with its request/session. | `string` | ❌ No |
| **status_code** | Status code indicating success or failure. | `int` | ✅ Yes |
| **done** | Indicates whether this is the final timestamp event. | `bool` | ✅ Yes |
| **word_timestamps** | A dictionary describing word-level timestamps (format may vary by implementation). | `dict<string, any>` | ✅ Yes |

##### Phoneme Timestamp Event

A **phoneme timestamp event** provides timing data at the phoneme level, typically for detailed speech analysis.

| **Parameter** | **Description** | **Type** | **Required** |
|--------------|-----------------|----------|--------------|
| **type** | The response type. Always `"phoneme_timestamps"`. | `string` | ✅ Yes |
| **context_id** | Optional identifier for correlating this event with a request/session. | `string` | ❌ No |
| **status_code** | Processing status code. | `int` | ✅ Yes |
| **done** | Indicates whether this is the final phoneme timestamp event. | `bool` | ✅ Yes |
| **phoneme_timestamps** | A dictionary containing phoneme-level timing information. | `dict<string, any>` | ✅ Yes |

### Continuations

Continue speech across requests by sending the previous response's encrypted `history` token with the next text segment. Use a Cartesia-provided image that supports continuations; older images need an update. The continuation encryption key is already baked into supported images, so you do not need to create a provider secret or send a key from your client.

Set `include_history: true` on the first request and read `history` from the final `done` event. Send that string unchanged as `history` on the next request, with only the new text in `transcript`. Keep the same model and `voice.id`, and carry forward the newest token for each subsequent request. Supplying `history` also requests a new token, even if you omit `include_history`.

Each request has its own `context_id`; reusing a context ID alone does not continue speech. The token carries the audio conditioning state, so requests can reach different replicas using the same model and continuation key. You do not need session affinity. Continuation uses a rolling audio context, rather than retaining an entire conversation indefinitely.

Tokens expire after 24 hours by default, measured from issuance (`TTS_CONTINUATION_TTL_SECONDS` controls the server setting). An expired token, a tampered token, or one that does not match the model, voice, or encryption key is discarded and generation proceeds without its history. A successful continuation-enabled generation returns a fresh token. Omitting both fields preserves the existing response contract without a history token.

Treat tokens as opaque application data: store and forward them without decoding, decrypting, or modifying them. Keep them private along with the generated audio. If continuation support has no usable encryption key, the service reports `history unavailable` with status code `503`; use a supported Cartesia image.

Install `boto3` with `pip install boto3` and configure AWS credentials and a region with permission to invoke your endpoint. Set `SAGEMAKER_ENDPOINT_NAME` to its name and `VOICE_ID` to a voice available on the deployment:

```bash
export SAGEMAKER_ENDPOINT_NAME='your-endpoint-name'
export VOICE_ID='bf0a246a-8642-498a-9950-80c35e9276b5'
```

The example buffers newline-delimited JSON events across SageMaker `PayloadPart` boundaries, captures the final history token, and uses it on a second request. It saves two mono, 44.1 kHz, 16-bit PCM files; play them consecutively.

```python
import base64
import json
import os
import uuid
from pathlib import Path

import boto3

runtime = boto3.client("sagemaker-runtime")


def generate(transcript, history=None):
    body = {
        "context_id": str(uuid.uuid4()),
        "transcript": transcript,
        "language": "en",
        "voice": {
            "mode": "id",
            "id": os.environ["VOICE_ID"],
        },
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 44100,
        },
        "include_history": True,
    }
    if history is not None:
        body["history"] = history
    response = runtime.invoke_endpoint_with_response_stream(
        EndpointName=os.environ["SAGEMAKER_ENDPOINT_NAME"],
        ContentType="application/json",
        Accept="text/event-stream",
        Body=json.dumps(body),
    )
    audio = bytearray()
    pending = b""
    stream = response["Body"]
    try:
        for part in stream:
            if "PayloadPart" not in part:
                raise RuntimeError(part)
            pending += part["PayloadPart"]["Bytes"]
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if not line.strip():
                    continue
                event = json.loads(line)
                if event["type"] == "error":
                    raise RuntimeError(event)
                if event["type"] == "chunk":
                    audio.extend(base64.b64decode(event["data"]))
                elif event["type"] == "done":
                    if not event.get("history"):
                        raise RuntimeError("No continuation token returned; check image support")
                    return bytes(audio), event["history"]
    finally:
        stream.close()
    raise RuntimeError("Stream ended before the done event")


audio_a, history = generate("The old lighthouse keeper climbed the stairs.")
audio_b, history = generate("He lit the lamp as daylight faded.", history)
Path("part-a.pcm").write_bytes(audio_a)
Path("part-b.pcm").write_bytes(audio_b)
```

### Error Handling

If an error occurs during the generation type, Sagemaker will send back the error as a [Model Error](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpoint.html#API_runtime_InvokeEndpoint_ResponseElements:~:text=Status%20Code%3A%20500-,ModelError,-Model%20(owned%20by)). To handle the error, you may inspect the `OriginalStatusCode` field of the error object (See examples for error handling in python).

#### 422 Errors

A 422 error indicates that your input is not of the correct format. You may see more details in the `Messsage` field.

#### 429 Errors

A 429 error indicates that the model container you are hitting does not have capacity to serve requests at the point. Our models serve at most 4 concurrent generation requests at a time. If you are running multiple inference container replicas, we suggest that you use load-aware routing in sagemaker by configuring the parameters `RoutingConfig` inside the `ProductionVariants` configuration, Set it to `LEAST_OUTSTANDING_REQUESTS` for optimal load distribution.

### Container Logs

You should be able to see container logs in cloudwatch. Most logs should be emitted with a request id. Attach a context_id for tracking purposes.

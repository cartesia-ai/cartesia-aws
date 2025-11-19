# Sonic 3 Models on Sagemaker Jumpstart

### Getting Started

For a step by step guide to create your first Sonic 3 Inference endpoint on Sagemaker, please refer to [sample notebook](https://github.com/cartesia-ai/cartesia-aws/blob/main/Sonic-3-Jumpstart.ipynb)

### Inference Setup

Sonic 3 supports only real time inference on Sagemaker. Please select `ml.g6e.xlarge` as your inference endpoint instance type. Each instance is capable of serving 8 concurrent requests. In order to get the best performance, Sagemaker suggests that you reuse the client-to-SageMaker connection, as it can save the time to re-establish the connection. In boto3, you can configure max_pool_connections . Multiple requests will reuse the connections, which avoids the cost of establishing new TCP/TLS connections for each request.

###  Input Summary

The response streaming endpoint takes in a JSON object as the input that specifies the transcript, voice, language, and output format for the generation

### Input Parameters

| **Parameter** | **Description** | **Type** | **Required** |
|---------------|-----------------|-----------|---------------|
| **context_id** | A unique ID provided by the client to identify the request. It can be any string value and helps with tracking or debugging. | `string` | ✅ Yes |
| **transcript** | The text that will be converted into speech. You can include additional controls (e.g., emotion, speed, volume) as supported by Sonic 3 models: https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion | `string` | ✅ Yes |
| **language** | The language code of the transcript text. Supported codes include: <br> `en`, `fr`, `de`, `es`, `pt`, `zh`, `ja`, `hi`, `it`, `ko`, `nl`, `pl`, `ru`, `sv`, `tr`, `tl`, `bg`, `ro`, `ar`, `cs`, `el`, `fi`, `hr`, `ms`, `sk`, `da`, `ta`, `uk`, `hu`, `no`, `vi`, `bn`, `th`, `he`, `ka`, `id`, `te`, `gu`, `kn`, `ml`, `mr`, `pa` | `string` | ✅ Yes |
| **output_format** | Must match the `raw` option from the Cartesia TTS SSE API: https://docs.cartesia.ai/api-reference/tts/sse#body-output-format. Only `raw` is supported. | `string` | ✅ Yes |
| **voice** | Matches the `voice` field from the Cartesia TTS SSE API: https://docs.cartesia.ai/api-reference/tts/sse#body-voice. Only **mode = `id`** is supported. Example: `{ "mode": "id", "id": "voice_123" }` | `object` | ✅ Yes |
| **generation_config** | Optional configuration object matching the API schema: https://docs.cartesia.ai/api-reference/tts/sse#body-generation-config | `object` | ❌ No |
| **add_timestamps** | Whether to include word-level timestamps in the output: https://docs.cartesia.ai/api-reference/tts/sse#body-add-timestamps | `boolean` | ❌ No |
| **add_phoneme_timestamps** | Whether to include phoneme-level timestamps in the output: https://docs.cartesia.ai/api-reference/tts/sse#body-add-phoneme-timestamps | `boolean` | ❌ No |
| **use_normalized_timestamps** | Whether timestamps should be normalized (0–1 range): https://docs.cartesia.ai/api-reference/tts/sse#body-use-normalized-timestamps | `boolean` | ❌ No |



### Data Sample

```
{
    "context_id": "0",
    "transcript": "The detective burst through the door. 'We've got maybe five minutes before they realize we're here, so listen carefully and listen well: <speed ratio='1.5'/> the artifact is hidden beneath the old courthouse, exactly three feet below the cornerstone, and <volume ratio='0.5'/>whatever you do, DO NOT touch it with your bare hands!' She paused, catching her breath. 'Now... here's the important part... <speed ratio='0.6'/>you need to... very slowly... very carefully... wrap it in the copper wire first... then the silk cloth... then seal it in the lead box.' <volume ratio='2.0'/> Footsteps echoed in the hallway. 'GO GO GO! They're coming up the stairs RIGHT NOW!'",
    "language": "en",
    "output_format": {
        "container": "raw",
        "sample_rate": 44100,
        "encoding": "pcm"
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

A done event signals the completion of the generation. Done events are identified by `event.type == "done"` and `event.done == True`.

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

### Error Handling

If an error occurs during the generation type, Sagemaker will send back the error as a [Model Error](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpoint.html#API_runtime_InvokeEndpoint_ResponseElements:~:text=Status%20Code%3A%20500-,ModelError,-Model%20(owned%20by)). To handle the error, you may inspect the `OriginalStatusCode` field of the error object (See examples for error handling in python).

#### 422 Errors

A 422 error indicates that your input is not of the correct format. You may see more details in the `Messsage` field.

#### 429 Errors

A 429 error indicates that the model container you are hitting does not have capacity to serve requests at the point. Our models serve at most 4 concurrent generation requests at a time. If you are running multiple inference container replicas, we suggest that you use load-aware routing in sagemaker by configuring the parameters `RoutingConfig` inside the `ProductionVariants` configuration, Set it to `LEAST_OUTSTANDING_REQUESTS` for optimal load distribution.

### Container Logs

You should be able to see container logs in cloudwatch. Most logs should be emitted with a request id. The server side request id is of the format `{uuid}-{client supplied context id}`.

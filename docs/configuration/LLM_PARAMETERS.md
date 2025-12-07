# LLM Generation Parameters Configuration

This document describes the configurable parameters for LLM generation in the Warehouse Operational Assistant.

## Overview

The LLM generation parameters can be configured via environment variables, providing default values that are used across all LLM calls unless explicitly overridden in code.

## Available Parameters

### Temperature (`LLM_TEMPERATURE`)

**Description:** Controls the randomness of the model's output. Lower values make the output more deterministic and focused, while higher values make it more creative and diverse.

**Range:** `0.0` to `2.0`
- `0.0`: Most deterministic, focused responses
- `0.1-0.3`: Balanced, slightly creative (recommended for most use cases)
- `0.5-0.7`: More creative and varied
- `1.0+`: Highly creative, less predictable

**Default:** `0.1`

**Environment Variable:**
```bash
LLM_TEMPERATURE=0.1
```

**Usage in Code:**
```python
# Uses default from config
response = await nim_client.generate_response(messages)

# Override for specific call
response = await nim_client.generate_response(messages, temperature=0.0)
```

### Max Tokens (`LLM_MAX_TOKENS`)

**Description:** Maximum number of tokens to generate in the response. This limits the length of the output.

**Range:** `1` to model's maximum context window
- For Llama 3.3 Nemotron Super 49B: Up to 131,072 tokens (context window)
- Typical values: `500-4000` for most queries, `2000-8000` for complex queries

**Default:** `2000`

**Environment Variable:**
```bash
LLM_MAX_TOKENS=2000
```

**Usage in Code:**
```python
# Uses default from config
response = await nim_client.generate_response(messages)

# Override for longer responses
response = await nim_client.generate_response(messages, max_tokens=4000)
```

### Top P (`LLM_TOP_P`)

**Description:** Nucleus sampling parameter. Controls diversity via nucleus sampling. The model considers tokens with top_p probability mass.

**Range:** `0.0` to `1.0`
- `1.0`: Consider all tokens (default)
- `0.9`: Consider tokens comprising 90% of probability mass
- `0.5`: More focused, considers top 50% probability mass

**Default:** `1.0`

**Environment Variable:**
```bash
LLM_TOP_P=1.0
```

**Usage in Code:**
```python
# Uses default from config
response = await nim_client.generate_response(messages)

# Override for more focused sampling
response = await nim_client.generate_response(messages, top_p=0.9)
```

### Frequency Penalty (`LLM_FREQUENCY_PENALTY`)

**Description:** Reduces the likelihood of repeating tokens that have already appeared in the text. Positive values penalize new tokens based on their existing frequency.

**Range:** `-2.0` to `2.0`
- `0.0`: No penalty (default)
- `0.5-1.0`: Moderate penalty, reduces repetition
- `1.5-2.0`: Strong penalty, significantly reduces repetition

**Default:** `0.0`

**Environment Variable:**
```bash
LLM_FREQUENCY_PENALTY=0.0
```

**Usage in Code:**
```python
# Uses default from config
response = await nim_client.generate_response(messages)

# Override to reduce repetition
response = await nim_client.generate_response(messages, frequency_penalty=0.5)
```

### Presence Penalty (`LLM_PRESENCE_PENALTY`)

**Description:** Reduces the likelihood of repeating any token that has appeared in the text so far. Unlike frequency penalty, this applies regardless of how many times a token has appeared.

**Range:** `-2.0` to `2.0`
- `0.0`: No penalty (default)
- `0.5-1.0`: Moderate penalty, encourages new topics
- `1.5-2.0`: Strong penalty, strongly encourages new topics

**Default:** `0.0`

**Environment Variable:**
```bash
LLM_PRESENCE_PENALTY=0.0
```

**Usage in Code:**
```python
# Uses default from config
response = await nim_client.generate_response(messages)

# Override to encourage new topics
response = await nim_client.generate_response(messages, presence_penalty=0.5)
```

## Configuration

### Environment Variables

Add these to your `.env` file (or set as environment variables):

```bash
# LLM Model Configuration
LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5

# LLM Generation Parameters
LLM_TEMPERATURE=0.1          # Default: 0.1 (balanced, slightly creative)
LLM_MAX_TOKENS=2000          # Default: 2000 (good for most queries)
LLM_TOP_P=1.0                # Default: 1.0 (consider all tokens)
LLM_FREQUENCY_PENALTY=0.0    # Default: 0.0 (no repetition penalty)
LLM_PRESENCE_PENALTY=0.0     # Default: 0.0 (no presence penalty)
```

### Recommended Settings by Use Case

#### General Chat/Conversation
```bash
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2000
LLM_TOP_P=0.95
LLM_FREQUENCY_PENALTY=0.1
LLM_PRESENCE_PENALTY=0.1
```

#### Structured Data/JSON Generation
```bash
LLM_TEMPERATURE=0.0          # Most deterministic for consistent JSON
LLM_MAX_TOKENS=2000
LLM_TOP_P=1.0
LLM_FREQUENCY_PENALTY=0.0
LLM_PRESENCE_PENALTY=0.0
```

#### Creative/Exploratory Responses
```bash
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=3000
LLM_TOP_P=0.9
LLM_FREQUENCY_PENALTY=0.3
LLM_PRESENCE_PENALTY=0.2
```

#### Long-form Content Generation
```bash
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4000
LLM_TOP_P=0.95
LLM_FREQUENCY_PENALTY=0.2
LLM_PRESENCE_PENALTY=0.1
```

## Current Agent Usage

Different agents in the system use different parameter settings:

### Equipment Agent
- **Temperature:** `0.0` (hardcoded for JSON consistency)
- **Max Tokens:** `2000` (hardcoded)

### Safety Agent
- **Temperature:** `0.0` (hardcoded for JSON consistency)
- **Max Tokens:** `2000` (hardcoded)

### Operations Agent
- **Temperature:** `0.2` (hardcoded)

### Forecasting Agent
- Uses default configuration values

**Note:** Agents that hardcode values will continue to use those values. The environment variables set defaults for calls that don't specify parameters.

## Implementation Details

### Code Location
- **Configuration:** `src/api/services/llm/nim_client.py` - `NIMConfig` class
- **Generation Method:** `src/api/services/llm/nim_client.py` - `NIMClient.generate_response()`

### How It Works

1. **Default Values:** Set via environment variables in `NIMConfig`
2. **Per-Call Override:** Any parameter can be overridden when calling `generate_response()`
3. **Fallback:** If a parameter is `None`, the config default is used

### Example

```python
from src.api.services.llm.nim_client import get_nim_client

# Get the client (uses config defaults from environment)
nim_client = await get_nim_client()

# Use defaults from config
response = await nim_client.generate_response(messages)

# Override specific parameters
response = await nim_client.generate_response(
    messages,
    temperature=0.0,      # Override default
    max_tokens=3000,      # Override default
    # top_p, frequency_penalty, presence_penalty use defaults
)
```

## Best Practices

1. **Start with Defaults:** Use the default values unless you have a specific need
2. **Temperature Guidelines:**
   - Use `0.0-0.2` for structured outputs (JSON, code)
   - Use `0.2-0.5` for general conversation
   - Use `0.5-0.8` for creative tasks
3. **Max Tokens:** Set based on expected response length
   - Short responses: `500-1000`
   - Medium responses: `1500-2500`
   - Long responses: `3000-5000`
4. **Penalties:** Use sparingly, only if you notice repetition issues
5. **Testing:** Test parameter changes with real queries to see the impact

## Troubleshooting

### Responses are too short
- Increase `LLM_MAX_TOKENS`

### Responses are too repetitive
- Increase `LLM_FREQUENCY_PENALTY` or `LLM_PRESENCE_PENALTY`

### Responses are too random/inconsistent
- Decrease `LLM_TEMPERATURE`

### Responses are too deterministic/boring
- Increase `LLM_TEMPERATURE`

### JSON parsing errors
- Set `LLM_TEMPERATURE=0.0` for more consistent JSON formatting

## See Also

- [NVIDIA NIM Documentation](https://build.nvidia.com/)
- [Llama 3.3 Nemotron Super 49B Model Card](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5/modelcard)
- [OpenAI API Parameters Reference](https://platform.openai.com/docs/api-reference/chat/create) (similar parameter definitions)


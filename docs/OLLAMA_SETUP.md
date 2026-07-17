# Ollama Integration Guide for Cloud-Reaper

This guide explains how to set up and use Ollama local models with Cloud-Reaper for cost-free AI operations.

## Overview

Cloud-Reaper now supports **Ollama** as a local AI backend, allowing you to:
- Run AI features without API costs
- Keep sensitive cloud data on-premises
- Work offline without internet connectivity
- Use custom models fine-tuned on your data

## Prerequisites

### Hardware Requirements

- **CPU**: Modern multi-core processor (4+ cores recommended)
- **RAM**: 
  - 8GB minimum for small models (3B parameters)
  - 16GB recommended for medium models (7B parameters)
  - 32GB+ for large models (13B+ parameters)
- **Storage**: 10GB+ for model weights
- **GPU**: Optional but highly recommended for faster inference

### Software Requirements

- Docker or native Ollama installation
- Cloud-Reaper with Ollama dependencies installed

## Installation

### Option 1: Native Installation (Recommended)

#### Linux/macOS:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve
```

#### Windows:
```powershell
# Download Ollama from https://ollama.com/download
# Run the installer and start Ollama from the Start menu
```

### Option 2: Docker Installation

```bash
# Pull and run Ollama
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama

# Verify it's running
docker ps
```

## Model Setup

### Required Models

Cloud-Reaper needs two types of models:

1. **Embedding Model** (for RAG search):
   ```bash
   ollama pull nomic-embed-text
   ```

2. **Generation Model** (for Copilot, Architect, etc.):
   ```bash
   # Recommended: Llama 3.1 (8B)
   ollama pull llama3.1
   
   # Alternative: Mistral (7B)
   ollama pull mistral
   
   # Alternative: Phi-3 (smaller, faster)
   ollama pull phi3
   ```

### Verify Model Installation

```bash
# List installed models
ollama list

# Test a model
ollama run llama3.1 "Hello, how are you?"
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```env
# AI Backend Selection
AI_BACKEND=ollama

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Configuration Options

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `AI_BACKEND` | AI backend to use | `gemini` | `ollama`, `gemini`, `openai`, `ensemble` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` | Any valid HTTP URL |
| `OLLAMA_MODEL` | Generation model | `llama3.1` | Any installed Ollama model |
| `OLLAMA_EMBEDDING_MODEL` | Embedding model | `nomic-embed-text` | Any embedding model |

## Usage

### Basic Usage

1. **Start Ollama** (if not running):
   ```bash
   ollama serve
   ```

2. **Configure Cloud-Reaper**:
   ```bash
   # Set AI backend to Ollama
   export AI_BACKEND=ollama
   
   # Start Cloud-Reaper
   python -m reaper.web.app_async
   ```

3. **Use AI Features**:
   - RAG search will use local embeddings
   - Copilot will use local generation
   - AI Architect will use local models

### Hybrid Mode (Ensemble)

Use multiple AI backends for improved results:

```env
AI_BACKEND=ensemble
```

This will:
- Use Ollama if available
- Fall back to cloud APIs if Ollama fails
- Combine results from multiple backends

### Model Selection

Choose different models based on your needs:

```env
# For faster inference (smaller model)
OLLAMA_MODEL=phi3

# For better quality (larger model)
OLLAMA_MODEL=llama3.1

# For specific tasks
OLLAMA_MODEL=mistral
```

## Performance Optimization

### GPU Acceleration

If you have an NVIDIA GPU:

```bash
# Install NVIDIA Container Toolkit (for Docker)
# Or ensure NVIDIA drivers are installed (native)

# Ollama will automatically use GPU if available
ollama run llama3.1
```

### Memory Management

```bash
# Limit VRAM usage
ollama run llama3.1 --num_gpu 1

# Use CPU only
ollama run llama3.1 --num_gpu 0
```

### Batch Processing

For large-scale operations:

```bash
# Increase context window
ollama run llama3.1 --num_ctx 8192
```

## Troubleshooting

### Ollama Server Not Running

**Symptom**: Connection refused errors

**Solution**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

### Model Not Found

**Symptom**: "model not found" errors

**Solution**:
```bash
# List available models
ollama list

# Pull required models
ollama pull nomic-embed-text
ollama pull llama3.1
```

### Out of Memory

**Symptom**: OOM errors or crashes

**Solution**:
```bash
# Use a smaller model
OLLAMA_MODEL=phi3

# Limit context size
ollama run llama3.1 --num_ctx 4096
```

### Slow Performance

**Symptom**: Very slow inference

**Solution**:
```bash
# Check GPU usage
nvidia-smi

# Ensure GPU is being used
ollama run llama3.1 --num_gpu 1

# Use quantized model
ollama pull llama3.1:q4_0
```

### Health Check

Check Ollama health from Cloud-Reaper:

```python
from reaper.engine.ai_backends.health import check_ollama_health

health = check_ollama_health()
print(health)
```

## Advanced Configuration

### Custom Models

Use your own fine-tuned models:

```bash
# Create a Modelfile
FROM llama3.1
SYSTEM You are a cloud cost optimization expert.

# Build and run
ollama create cloud-reaper-model -f Modelfile
ollama run cloud-reaper-model
```

```env
OLLAMA_MODEL=cloud-reaper-model
```

### Multiple Ollama Instances

Run multiple Ollama instances for load balancing:

```bash
# Instance 1
OLLAMA_BASE_URL=http://localhost:11434

# Instance 2
OLLAMA_BASE_URL=http://localhost:11435
```

### API Proxy

Access Ollama from remote machines:

```bash
# Allow remote connections
export OLLAMA_HOST=0.0.0.0:11434
ollama serve
```

```env
OLLAMA_BASE_URL=http://your-server-ip:11434
```

## Cost-Benefit Analysis

### Ollama vs Cloud APIs

| Factor | Ollama | Cloud APIs |
|--------|--------|------------|
| **Cost** | Free (hardware cost only) | $0.002-0.05 per 1K tokens |
| **Privacy** | 100% local | Data sent to external servers |
| **Offline** | Works offline | Requires internet |
| **Quality** | Good (depends on model) | Best (GPT-4, Claude) |
| **Speed** | Slower (CPU) / Fast (GPU) | Fast (cloud infrastructure) |
| **Setup** | Requires setup | No setup required |

### Break-Even Analysis

Assuming:
- Cloud API: $0.01 per 1K tokens
- Usage: 1M tokens/month
- Hardware: $500 one-time

**Cloud API Cost**: $10/month
**Ollama Cost**: $0/month + $500 hardware amortization

**Break-even**: 50 months (4+ years)

However, for **privacy** and **offline** benefits, Ollama may be worth it even at higher cost.

## Migration Guide

### From Cloud APIs to Ollama

1. **Install Ollama** (see Installation)
2. **Pull Models**:
   ```bash
   ollama pull nomic-embed-text
   ollama pull llama3.1
   ```
3. **Update Configuration**:
   ```env
   AI_BACKEND=ollama
   ```
4. **Test**:
   ```python
   from reaper.engine.ai_backends.health import check_all_ai_backends
   print(check_all_ai_backends())
   ```

### Hybrid Approach

Use Ollama for development, cloud APIs for production:

```env
# Development
AI_BACKEND=ollama

# Production
AI_BACKEND=gemini
```

## Best Practices

1. **Start Small**: Begin with smaller models (phi3) for testing
2. **Monitor Resources**: Use `htop` or `nvidia-smi` to monitor resource usage
3. **Cache Results**: Enable caching to reduce repeated computations
4. **Use Ensemble**: Combine Ollama with cloud APIs for best results
5. **Regular Updates**: Keep Ollama and models updated for improvements

## Support

For issues specific to:
- **Ollama**: https://github.com/ollama/ollama
- **Cloud-Reaper**: https://github.com/ankitrout07/Cloud-Reaper/issues

## Contributing

To improve Ollama integration:
1. Test with different models
2. Share performance benchmarks
3. Contribute optimization tips
4. Report bugs with detailed logs

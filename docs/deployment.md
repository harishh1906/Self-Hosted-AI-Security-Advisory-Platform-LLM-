# Production Deployment & Verification Guide

This guide details the steps required to deploy and verify the **Self-Hosted AI Security Advisory Platform** on production hardware.

---

## Target System Specifications
*   **Hardware:** Dell Precision 5820 (Intel Xeon W-2145, 32GB RAM, NVIDIA Quadro P1000 4GB VRAM)
*   **Operating System:** Ubuntu 24.04 LTS (or compatible Linux distribution)

---

## 1. System Preparation

To enable GPU acceleration for the Ollama inference service, you must install the NVIDIA drivers and the NVIDIA Container Toolkit so that Docker can expose GPU resources to containers.

```bash
# Update system package registry
sudo apt update && sudo apt upgrade -y

# Detect and automatically install recommended NVIDIA Drivers
sudo ubuntu-drivers autoinstall

# Configure the production repository for the NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install the toolkit
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker to use the NVIDIA Container Runtime and restart daemon
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## 2. Environment Configuration

Clone the repository to your host system, configure environmental variables, and lock down file permissions.

```bash
# Navigate to the deployment folder
cd ~/Self-Hosted-AI-Security-Advisory-Platform-LLM

# Generate the active environment configuration
cp .env.example .env

# Open and customize secrets/keys
nano .env
```

> [!WARNING]
> Restrict the `.env` file permissions to ensure that database credentials, JWT secrets, and API keys are not readable by other non-privileged users on the host system:
> ```bash
> chmod 600 .env
> ```

---

## 3. Launching the Stack

Build the custom FastAPI advisory-api image and the asynchronous worker containers, then orchestrate the entire multi-tenant stack.

```bash
# Build and run the service orchestration in detached mode
docker compose up -d --build

# Verify all orchestrated containers are active and healthy
docker compose ps
```

---

## 4. Initial Synchronization & Model Warmup

On the first start, the Ollama service automatically pulls the primary model (`gemma4:e2b`, ~7.2 GB) from the registry.

```bash
# Follow the model download and loading progress
docker compose logs -f ollama

# Once pulled, verify the model is active and mapped into GPU VRAM
docker exec -it virtue-ollama nvidia-smi
```

---

## 5. Ingestion Verification Sequence

Follow this step-by-step verification pipeline to trace vulnerability data flow from the internet (NVD/CISA) into local storage, through the processing and embedding worker, and finally into the Qdrant vector database.

### Step 5.1: Check Fetcher Logs
Verify that the `knowledge-fetcher` worker successfully queries the National Vulnerability Database (NVD) and CISA KEV feeds.

```bash
docker compose logs -f knowledge-fetcher
```
*Look for successful query logs, pagination markers, and records fetched counts.*

### Step 5.2: Verify the Shared Ingest Inbox
The fetcher runs on an internet-facing isolated container and writes canonical JSON batch files to a shared Docker volume. Ensure files are successfully produced:

```bash
# List files in the shared storage bridge
docker exec -it knowledge-fetcher ls -lh /data/knowledge-inbox
```
*Look for generated files matching `NVD_batch_*.json` or `CISA_batch_*.json` along with `.fetch_state.json`.*

### Step 5.3: Check Ingester Processing & Embedding
The air-gapped `knowledge-ingester` polls the shared inbox every 60 seconds, reads the JSON files, converts the descriptions into 384-dimensional dense vectors using a local `SentenceTransformer` model, and inserts them into Qdrant.

```bash
docker compose logs -f knowledge-ingester
```
*Look for `Processing: ...` and `Flushed batch of X points to Qdrant` logs.*

### Step 5.4: Verify Qdrant Vector Points
Verify that the vectors exist within Qdrant's schema space.

```bash
curl http://localhost:6333/collections/security_knowledge
```
*Confirm that `"points_count"` is greater than zero.*

---

## 6. Maintenance & Troubleshooting

*   **Host VRAM Exhaustion:** If Ollama encounters Out-Of-Memory (OOM) errors on the Quadro P1000, ensure `max_concurrent_inference` in the system settings config is set to `1` (enforcing strict GPU serialization).
*   **Ingester Inactivity:** If the ingester is active but skipping files, ensure Qdrant is fully initialized and that the ` SentenceTransformer` weights were successfully cached at container build time.
*   **System Cleanup:** To clean up build-time layers and reclaim storage space, run:
    ```bash
    docker system prune -f
    ```

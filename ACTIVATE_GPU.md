# GPU-activatie voor Ollama in Docker

Ollama draait standaard op de CPU in Docker. Om de NVIDIA GPU te gebruiken
moeten twee dingen kloppen: (1) de juiste drivers/toolkit op de host, en
(2) het `deploy`-blok geactiveerd in `docker-compose.yml`.

> **Opmerking:** Alleen NVIDIA GPU's worden ondersteund via de Docker GPU-integratie.
> AMD en Intel GPU's vallen buiten scope van deze handleiding.

---

## Stap 1 — Host-vereisten per platform

### Windows (met Docker Desktop + WSL2)

1. Installeer de **NVIDIA Game Ready of Studio Driver** via
   [nvidia.com/drivers](https://www.nvidia.com/drivers) — versie ≥ 527.  
   *(Geen aparte WSL2-driver nodig; de Windows-driver exposeert CUDA automatisch in WSL2.)*
2. Zorg dat **Docker Desktop** draait met de WSL2-backend ingeschakeld
   (`Settings → General → Use the WSL 2 based engine`).
3. Verifieer in een WSL2-terminal:
   ```bash
   nvidia-smi
   ```
   Je ziet de GPU-naam en driver-versie als alles correct is.

---

### Linux (native Docker Engine)

1. Installeer de **NVIDIA driver** via je package manager of
   [nvidia.com/drivers](https://www.nvidia.com/drivers) — versie ≥ 525 aanbevolen.
2. Installeer de **NVIDIA Container Toolkit**:
   ```bash
   # Voeg de NVIDIA-repo toe
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
     | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
     | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
     | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit

   # Configureer Docker en herstart de daemon
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
3. Verifieer:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
   ```

---

### macOS

NVIDIA GPU-passthrough in Docker is **niet mogelijk op macOS**. Apple-hardware
gebruikt uitsluitend Apple Silicon (M-serie) of oudere AMD GPU's, en Docker op
macOS draait via een Linux-VM die geen directe GPU-toegang heeft.

Ollama draait op macOS wél geoptimaliseerd via **Metal** (Apple GPU-API), maar
enkel als je Ollama *buiten Docker* installeert:

```bash
brew install ollama
ollama serve
```

Wil je toch Ollama via Docker gebruiken op macOS, aanvaard dan dat het op de
CPU draait en dus trager is.

---

## Stap 2 — GPU-blok activeren in docker-compose.yml

Uncomment het `deploy`-blok in de `ollama`-service:

```yaml
ollama:
  image: ollama/ollama:0.23.0
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

Herstart daarna de container:

```bash
docker compose up -d --force-recreate ollama
```

---

## Verificatie

Controleer of Ollama de GPU herkent:

```bash
docker exec -it modal-unit-ollama-1 nvidia-smi
```

Of kijk in de Ollama-logs bij het laden van een model — je ziet dan iets als:

```
llm server loading model ... offloaded X layers to GPU
```

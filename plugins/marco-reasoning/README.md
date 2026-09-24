# Marco Reasoning plugin

A read-only MCP adapter plus skill that uses MARCO as a deterministic reasoning sidecar for ChatGPT and Codex.

## Tools

- `marco_reason`: derive an answer from exact, source-grounded premise spans.
- `marco_verify`: conservatively check a proposed answer against MARCO.
- `marco_explain`: fetch evidence and trace for a returned `proof_id`.

The adapter never enables MARCO network research. It uses the public `mco` API and keeps plugin-specific code outside the core runtime.

## Run locally

From the Marco repository root:

```bash
python -m pip install -r plugins/marco-reasoning/requirements.txt
python plugins/marco-reasoning/server.py
```

The endpoint is `http://127.0.0.1:8765/mcp` by default.

Model selection, in order:

1. `MARCO_MODEL_PATH` if set.
2. `MARCO-1-preview.mco` in the repository root if present.
3. A cached model at `~/.cache/marco-reasoning/MARCO-sidecar.mco`, compiled lazily from the checkout on first use.

Optional environment variables:

```text
MARCO_MODEL_PATH=/absolute/model.mco
MARCO_MODEL_CACHE=/absolute/cache.mco
MARCO_MCP_HOST=127.0.0.1
MARCO_MCP_PORT=8765
MARCO_MCP_PATH=/mcp
MARCO_MCP_TRANSPORT=streamable-http   # or stdio
```

## ChatGPT/Codex development

`mcp.json` and `skills/marco-reasoning/agents/openai.yaml` point at the local development endpoint. For ChatGPT developer-mode testing, expose it through Secure MCP Tunnel or another approved HTTPS development endpoint and replace both URLs. For public submission, deploy a stable HTTPS Streamable HTTP endpoint and update both files.

## Why spans instead of arbitrary facts?

The caller supplies source texts plus exact character ranges. The server extracts the premise text itself. This prevents an LLM from passing a paraphrase as though it were source evidence and mirrors MARCO's existing exact-evidence philosophy.

The sidecar still cannot prove that the caller chose the *right* spans; it only ensures that accepted premises actually occur in the supplied source. Domain-specific packs can add stronger validation later.

## Replit

The repository includes a root `.replit` file for GitHub import and deployment. It installs the local `mco` package plus the MCP dependencies during the deployment build and runs the sidecar on `0.0.0.0:3000`, mapped to the public HTTPS port.

For a continuously available MCP endpoint, prefer a **Reserved VM** deployment. Autoscale can work for request-driven use, but the in-process `proof_id` cache is intentionally ephemeral and may be lost when instances scale to zero or are replaced. The endpoint remains `/mcp`; the health endpoint is `/health`.

## Docker

Build from the **repository root** so the image contains the MARCO runtime and knowledge assets:

```bash
docker build -f plugins/marco-reasoning/Dockerfile -t marco-reasoning .
docker run --rm -p 8765:8765 marco-reasoning
```

The server is intentionally read-only but this MVP does not implement MCP authentication itself. Put authentication/rate limiting at the deployment boundary before exposing a personal instance publicly.

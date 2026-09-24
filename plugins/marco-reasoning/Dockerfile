FROM python:3.13-slim

WORKDIR /app
COPY . /app

RUN python -m pip install --no-cache-dir -e . \
    && python -m pip install --no-cache-dir -r plugins/marco-reasoning/requirements.txt

ENV MARCO_MCP_HOST=0.0.0.0
ENV MARCO_MCP_PORT=8765
EXPOSE 8765

CMD ["python", "plugins/marco-reasoning/server.py"]

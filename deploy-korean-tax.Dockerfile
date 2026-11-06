FROM python:3.12-slim
WORKDIR /app
COPY requirements-korean-tax.txt /app/
RUN pip install --no-cache-dir -r requirements-korean-tax.txt
COPY . /app
ENV HOST=0.0.0.0 PORT=8080 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65534:65534
CMD ["python", "-m", "marco.knowledge.korean_tax.server"]

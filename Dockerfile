FROM python:3.12-slim

WORKDIR /agent

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash util-linux ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY ops ./ops
RUN find /agent/ops -type f -name "*.sh" -exec chmod +x {} \;

CMD ["python", "main.py"]

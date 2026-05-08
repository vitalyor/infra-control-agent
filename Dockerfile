FROM python:3.12-slim

WORKDIR /agent

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io docker-compose procps util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py ./
<<<<<<< HEAD
=======
COPY ops ./ops
RUN find /agent/ops -type f -name "*.sh" -exec chmod +x {} \;
>>>>>>> 50286f7 (Refactor agent v2: ops-runner architecture, docs, tests)

CMD ["python", "main.py"]

# Part 1 (Brain) in a container. EMANE itself is installed separately (see README, Part 2).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python3", "tdma_brain.py"]

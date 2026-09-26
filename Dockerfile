# Python + headless Chromium: collect, match and report without installing anything on the host.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHROME_HEADLESS=1 \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER=/usr/bin/chromedriver

# Chromium and its driver come from Debian as a matching pair; fonts for readable screenshots;
# tzdata so that run times are local, like runs made without Docker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# "docker compose run --rm app <arguments>" runs "python <arguments>".
ENTRYPOINT ["python"]
CMD ["main.py"]

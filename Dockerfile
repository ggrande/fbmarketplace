FROM apify/actor-python-playwright:3.12-1.39.0

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ARG UPSTREAM_REPO=https://github.com/passivebot/facebook-marketplace-scraper.git
RUN git clone --depth=1 ${UPSTREAM_REPO} /opt/upstream || true

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src /usr/src/app/src

CMD ["python", "-m", "src"]

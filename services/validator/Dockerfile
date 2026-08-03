FROM debian:bookworm-slim AS omsim-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

ARG OMSIM_REPOSITORY=https://github.com/ianh/omsim.git
ARG OMSIM_COMMIT=master

RUN git clone "$OMSIM_REPOSITORY" /src/omsim \
    && cd /src/omsim \
    && git checkout "$OMSIM_COMMIT" \
    && make omsim

FROM python:3.12-slim-bookworm

ARG OMSIM_COMMIT=master
ENV OMSIM_BIN=/usr/local/bin/omsim \
    OMSIM_COMMIT=$OMSIM_COMMIT \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 appuser

COPY --from=omsim-build /src/omsim/omsim /usr/local/bin/omsim
COPY services/validator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/validator/app.py /app/app.py
WORKDIR /app
USER appuser

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

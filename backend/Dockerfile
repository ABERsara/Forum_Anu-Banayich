FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Some dev machines run local network-filtering software (e.g. NetFree) that
# intercepts HTTPS with its own root CA, which pip won't trust by default.
# Pass its PEM content at build time (--build-arg NETFREE_CA="$(cat
# netfree-ca.crt)") on machines that need it. The arg defaults to empty and
# is never committed to the repo, so every other build (CI, cloud, teammates)
# is unaffected.
ARG NETFREE_CA=""
RUN if [ -n "$NETFREE_CA" ]; then \
      printf '%s\n' "$NETFREE_CA" > /usr/local/share/ca-certificates/netfree.crt \
      && update-ca-certificates; \
    fi
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Install dependencies from pyproject.toml first so this layer stays cached
# across builds unless dependencies actually change (app code changes alone
# won't invalidate it and force a full dependency reinstall).
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY . .
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

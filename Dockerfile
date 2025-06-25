ARG DJANGO_CA_VERSION=2.2.1
FROM mathiasertl/django-ca:${DJANGO_CA_VERSION} AS build
ARG DJANGO_CA_CMC_VERSION=0.0.1

# Install uv: https://docs.astral.sh/uv/guides/integration/docker/
COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /uvx /bin/

# Activate virtual environment
ENV PATH="/usr/src/django-ca/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/usr/src/django-ca/.venv"

# Configure uv
ENV UV_PYTHON_PREFERENCE=only-system
ENV UV_LINK_MODE=copy

USER root
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install django-ca-cmc==${DJANGO_CA_CMC_VERSION}

FROM mathiasertl/django-ca:${DJANGO_CA_VERSION}
COPY --from=build /usr/src/django-ca/.venv/ /usr/src/django-ca/.venv/

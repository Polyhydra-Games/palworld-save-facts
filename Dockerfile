# syntax=docker/dockerfile:1
# The index digest preserves native amd64/arm64 selection while preventing a
# mutable Python tag from silently changing release inputs.
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS build

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY vendor/PalworldSaveTools ./vendor/PalworldSaveTools
RUN apt-get update \
 && apt-get install --no-install-recommends --yes build-essential \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir vendor/PalworldSaveTools/src/palsav/palooz \
 && python -m pip install --no-cache-dir --no-deps vendor/PalworldSaveTools/src/palsav \
 && python -m pip install --no-cache-dir 'orjson>=3.11.8' \
 && python -m pip install --no-cache-dir .

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app
COPY --from=build /usr/local /usr/local
USER 10001:10001
ENTRYPOINT ["palworld-save-facts"]

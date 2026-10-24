ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && groupadd -g 10001 app && useradd -u 10001 -g app -M app
COPY --chown=10001:10001 app ./app
USER 10001:10001
EXPOSE 8000
CMD ["python","-m","uvicorn","app.main:create_app","--factory","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log","--no-proxy-headers","--timeout-graceful-shutdown","40","--limit-concurrency","100"]

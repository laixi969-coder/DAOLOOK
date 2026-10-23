FROM python:3.12-slim
WORKDIR /app
COPY server ./server
COPY web ./web
COPY scripts ./scripts
RUN useradd -m daolook && mkdir -m 700 data && chown daolook:daolook data
USER daolook
ENV HOST=0.0.0.0 PORT=8000 DAOLOOK_DB=/app/data/daolook.db
EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s CMD ["python", "scripts/healthcheck.py"]
CMD ["python", "-m", "server.app"]

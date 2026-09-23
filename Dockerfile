FROM python:3.12-slim
WORKDIR /app
COPY server ./server
COPY web ./web
RUN useradd -m daolook && mkdir data && chown daolook:daolook data
USER daolook
ENV HOST=0.0.0.0 PORT=8000 DAOLOOK_DB=/app/data/daolook.db
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["python", "-m", "server.app"]

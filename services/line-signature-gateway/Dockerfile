FROM python:3.13-alpine

RUN addgroup -S gateway && adduser -S -G gateway gateway

WORKDIR /app
COPY --chown=gateway:gateway app.py /app/app.py

USER gateway
EXPOSE 8080

CMD ["python", "/app/app.py"]

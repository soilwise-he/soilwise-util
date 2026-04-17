FROM ghcr.io/jumpserver/python:3.12-slim-buster
LABEL maintainer="genuchten@yahoo.com"

RUN adduser --uid 1000 --gecos '' --disabled-password soilwise

ENV ROOTPATH=/
ENV POSTGRES_HOST=host.docker.internal
ENV POSTGRES_PORT=5432
ENV POSTGRES_DB=postgres
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=*****

WORKDIR /home/soilwise

RUN chown --recursive soilwise:soilwise .

# initially copy only the requirements files
COPY --chown=soilwise \
    requirements.txt \
    ./

RUN pip install -U pip && \
    python3 -m pip install \
    -r requirements.txt \
    psycopg2-binary  

COPY --chown=soilwise ./src .

WORKDIR /home/soilwise

EXPOSE 8000

USER soilwise

ENTRYPOINT [ "python3", "-m", "uvicorn", "api:app", "--reload", "--host", "0.0.0.0", "--port", "8000" ]

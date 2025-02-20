

# API to browse through harvested feeds

News feeds of the soil mission projects are harvested into a database, this API enables to browse through the feeds. Feeds are ordered by date.

## Usage

Navigate to /docs to see interactive documentation (swagger)

Use params `limit` and `offset` to paginate through the results

## Run locally

A database connection needs to be set up. You can configure the database connection in a .env file (or set environment variables).

```
OGCAPI_URL=https://example.com
OGCAPI_COLLECTION=example
POSTGRES_HOST=example.com
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_SCHEMA=linky
POSTGRES_USER=postgres
POSTGRES_PASSWORD=******
```

Install requirements

```
pip3 install -r requirements.txt
```

```

To run the API locally 

```
python3 -m uvicorn api:app --reload --host 0.0.0.0 --port 8000 
```
The FastAPI service runs on: [http://127.0.0.1:8000/]

To view the service of the FastAPI on [http://127.0.0.1:8000/]

## Container Deployment

Set environment variables in Dockerfile to enable database connection.

Run the following command:

The app can be deployed as a container. 
A docker-compose file has been implemented.

Run ***docker-compose up*** to run the container

## Deploy `feeds` at a path

You can set `ROOTPATH` env var to run the api at a path (default is at root)

```
export ROOTPATH=/feeds
```

## CI/CD

A CI/CD configuration file is provided in order to create an automated chronological pipeline.
It is necessary to define the secrets context using GitLab secrets in order to connect to the database.

---

## Soilwise-he project

This work has been initiated as part of the Soilwise-he project. 
The project receives funding from the European Union’s HORIZON Innovation Actions 2022 under grant agreement No. 101112838.
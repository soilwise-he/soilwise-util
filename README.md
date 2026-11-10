# SOILWISE Util

API with various Util Methods:

- [Projects](#projects); retrieve relevant projects of ESDAC
- [Feeds](#feeds); let's users browse through various soil mission project feeds
- [Record validate](#record-validation); an api to validate the status of a record or suggest a record to be included
- [Version history](#version-history); API to retrieve previous versions of records
- [Augmentations](#augmentations); API to retrieve augmentations applied to a record

And [installation instructions](#installation).

## Projects

This api returns the list of EU projects which has been extracted from esdac and soil mission as being 'relevant to soil'. These projects are used to build a filter against OpenAire.

## Feeds 

News feeds of the soil mission projects are harvested into a database, this API enables to browse through the feeds. Feeds are ordered by date.

Use params `limit` and `offset` to paginate through the results

## Record validation

An api to validate the status of a record or suggest a record to be included.
A series of validation rules is applied to identify if/why a record is (not) included.

### Tests

Runs some tests on arbitrary DOI

Tests:
- http://localhost:8000/status/foo
- http://localhost:8000/status/10.1002/15-1100 (in soilwise)
- http://localhost:8000/status/10.1603/ec10272 (not HE)
- http://localhost:8000/status/10.3196/18642950146145209 (no relation)
- http://localhost:8000/status/10.5281/zenodo.12189624 101017416 (not in soil)
- http://localhost:8000/status/10.5281/zenodo.14733168 (in he project)
'
## Version history

API to request the harvested history for a record.

## Augmentations

API to request augmentations which have been applied to a record

# Installation

A database connection needs to be set up. You can configure the database connection in a .env file (or set environment variables).

```
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

The validate service requires the rec_uri and root_url to be provided via these parameters:

```
export REC_URI=https://repository.soilwise-he.eu/cat/collections/metadata:main/items/
export ROOT_URL=https://api.soilwise.wetransform.eu/util/
```

Navigate to /docs to see interactive documentation (swagger)

## Health check

A health check endpoint is available at `/health/ready` to understand if the api is running 
and can connect to the database.

## CI/CD

A CI/CD configuration file is provided in order to create an automated chronological pipeline.
It is necessary to define the secrets context using K8S secrets in order to connect to the database.

---

## Soilwise-he project

This work has been initiated as part of the Soilwise-he project. 
The project receives funding from the European Union’s HORIZON Innovation Actions 2022 under grant agreement No. 101112838.

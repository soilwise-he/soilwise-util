from fastapi import FastAPI, HTTPException, Query, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
from databases import Database
from typing import List, Optional, Any
from typing_extensions import Annotated
from pydantic import BaseModel
from datetime import datetime
import asyncpg, requests, asyncio
from requests.auth import HTTPDigestAuth
import logging
import os, httpx, re
from urllib.parse import quote_plus, quote


# Load environment variables from .env file
load_dotenv()

# Database connection setup
print(f'Connecting to {os.environ.get('POSTGRES_USER')}:******@{os.environ.get('POSTGRES_HOST')}:{os.environ.get('POSTGRES_PORT')}/{os.environ.get('POSTGRES_DB')}')
DATABASE_URL = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@{os.environ.get('POSTGRES_HOST')}:{os.environ.get('POSTGRES_PORT')}/{os.environ.get('POSTGRES_DB')}"

database = Database(DATABASE_URL)
schema = 'harvest'
if os.environ.get("POSTGRES_SCHEMA"):
    schema = os.environ.get("POSTGRES_SCHEMA")

REC_URI = os.environ.get("REC_URI",'https://repository.soilwise-he.eu/cat/collections/metadata:main/items/')
ROOT_URL = os.environ.get("ROOT_URL",'https://api.soilwise.wetransform.eu/util/')
rootpath = os.environ.get("ROOTPATH") or "/"

# FastAPI app instance
app = FastAPI(
    title="SoilWise Util",
    summary="""Range of utility methods to facilitate the SoilWise Catalogue, 
        get projects, feeds, augmentations, validate or suggest a DOI""",
    root_path=rootpath
)

@app.get("/health/ready", summary="Readiness check for SoilWise Utility API", description="Check if the SoilWise API is ready to handle requests by verifying database connectivity.")
async def readiness():
    if not _db_connected:
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ok"}

@app.get('/', response_class=HTMLResponse, summary="Welcome to the SoilWise Utility API", description="Welcome endpoint for the SoilWise Utility API, providing a brief introduction and links to documentation.")
async def index_loader():
    return '<html><head><meta http-equiv="refresh" content="0; url=./docs"></head></html>'

@app.on_event("startup")
async def startup():
    asyncio.create_task(connect_with_retry())

@app.on_event("shutdown")
async def shutdown():
    if database.is_connected:
        await database.disconnect()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
logger = logging.getLogger(__name__)

_db_connected = False


# Define response models
class FeedResponse(BaseModel):
    published: Optional[datetime] = None
    title: Optional[str] = None 
    summary: Optional[str] = None 
    link: Optional[str] = None 
    image: Optional[str] = None 
    author: Optional[str] = None 
    tags: Optional[str] = None 
class ProjectResponse(BaseModel):
    code: Optional[str] = None
    title: Optional[str] = None 
    abstract: Optional[str] = None 
    website: Optional[str] = None 
    grantnr: Optional[str] = None 
class RecordResponse(BaseModel):
    identifier: Optional[str] = None
    itemtype: Optional[str] = None 
    resultobject: Optional[str] = None 
    date: Optional[datetime] = None 
    title: Optional[str] = None 
    source: Optional[str] = None 
    project: Optional[str] = None

class AugmentResponse(BaseModel):
    property: Optional[str] = None
    original: Optional[str] = None
    target: Optional[str] = None
    process: Optional[str] = None
    date: Optional[datetime] = None

async def connect_with_retry():
    global _db_connected

    backoff = 1
    while True:
        try:
            await database.connect()
            _db_connected = True
            logger.info("Database connected")
            return
        except Exception as e:
            _db_connected = False
            logger.warning(f"Database connection failed: {e}. Retrying in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # cap backoff

# Helper function to validate email by pattern
def validate_email(email: str) -> bool:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

# Helper function to execute SQL query and fetch results
async def fetch_data(query: str, values: dict = {}):
    try:
        return await database.fetch_all(query=query, values=values)
    except asyncpg.exceptions.UndefinedTableError:
        logging.error("The specified table does not exist", exc_info=True)
        raise HTTPException(status_code=500, detail="The specified table does not exist")
    except Exception as e:
        logging.error(f"Database query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database query failed")

# Endpoint to fetch projects
@app.get('/projects', response_model=List[ProjectResponse])
async def get_projects():
    query = f"SELECT code,title,grantnr,favicon FROM {schema}.projects ORDER by grantnr"
    data = await fetch_data(query=query,values={})
    return data

@app.get('/project/{item}', 
         response_model=ProjectResponse, 
         summary="Get project details by grant number or code", 
         description="Provide either the grant number or the project code to retrieve details about a specific project.")
async def get_project(item):
    query = f"SELECT code,title,grantnr,abstract,website,favicon FROM {schema}.projects where grantnr = :item"
    data = await fetch_data(query=query,values={'item': str(item)})
    
    if data:
        for r in data:
            return r
    else:
        raise HTTPException(status_code=404, detail="Project not found")

# Endpoint to retrieve data with redirection statuses
@app.get('/feeds/items', 
         response_model=List[FeedResponse],
         summary="Retrieve news feeds from Soil Mission projects with optional filtering",
         description="""Retrieve feed items with optional filtering by keywords and project.""")
async def get_items(offset: int = 0, limit: int = 10, keywords: str = '', project: str = ''):
    query = f"SELECT * FROM harvest.feeds f left join harvest.projects p on f.project = p.code where " # join on code because it is always populated
    if keywords != '':
        query += "replace(lower(f.tags), ' ','') like :kw "  
    else:
        query += ":kw <> 'ex0'"

    if project != '':
        query += "and (p.grantnr = :prj or lower(p.code) = lower(:prj)) " 
    else:
        query += "and :prj <> 'ex0' " 
    query += """ORDER by published desc limit :limit offset :offset"""
    data = await fetch_data(query=query,values={'limit':limit,'offset':offset,'kw':f'%{keywords}%','prj':project})
    return data

class JsonLdPayload(BaseModel):
    MetadataContent: Any

DOI_URL = "https://doi.org/{}"

# Helper function to validate DOI existence
async def validate_doi(doi: str) -> bool:
    url = DOI_URL.format(doi.split('doi.org/').pop())
    headers = {
        "Accept": "application/x-bibtex"
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 200 and resp.text.strip():
                return True
            if resp.status_code == 302:
                return True
            elif resp.status_code == 404:
                return False
            else:
                return False

        except httpx.RequestError:
            return False

# Endpoint to get status of a doi
@app.get('/pid/status/{item:path}', 
         response_model=List[str],
         summary="Check the status/availability of a DOI in relation to SoilWise selection criteria",
         description="Check the status of a DOI in relation to SoilWise selection criteria, including its presence in SoilWise, OpenAire, and its validity as a DOI.")
async def status(item, request: Request):
    if 'doi.org' in item:
        item = item.split('doi.org/').pop()
    elif 'handle.net' in item:
        item = item.split('handle.net/').pop()

    resp = [f"Test item {quote(item)}"]
    ip = request.client.host
    if item:
        
        # is id in soilwise?
        qry1 = """SELECT identifier, fk_source, harvest_date from metadata.records r left join metadata.record_sources s on r.identifier = s.record_id
            WHERE r.identifier = :item"""
        d1 = await fetch_data(query=qry1, values={'item': item,  })
        
        qry2 = """SELECT identifier, error, source, insert_date from harvest.items WHERE identifier = :item or identifier like :_item"""
        d2 = await fetch_data(query=qry2, values={'item': item, '_item': '%'+item})
        
        qry3 = """select record_id from metadata.alternate_identifiers 
            where alt_identifier = :item or alt_identifier like :_item"""
        d3 = await fetch_data(query=qry3, values={'item': item, '_item': '%'+item })

        hasSOLR = None
        ttl = ''
        try: 
            url = "https://catalogue.soilwise-he.eu/search-api/solr/search"
            response = requests.post(url, data={ "query": "identifier:"+item })
            if response.json()['response']['numFound'] > 0:
                hasSOLR = True 
                ttl = response.json()['response']['docs'][0]['title']
        except Exception as e:
            print('error retrieve solr', item, e) 
    
        if hasSOLR == True:
            resp.append(f"Record <a href='https://catalogue.soilwise-he.eu/resource/{item.replace('/','%2F')}'>{ttl}</a> exists in Soilwise catalogue")
        elif len(d1) > 0:
            resp.append(f"Record exists in Soilwise database, last harvest date {d1[0][2]}")
            s = []
            for r in d1:
                s.append(r[1])
            resp.append(f"Record harvested from {', '.join(s)}")
        elif len(d3) > 0:
            resp.append(f"""Record {item} seems a alternate identification (or version) 
                        of the existing record <a href='{REC_URI}{d3[0][0]}'>{d3[0][0]}</a>""")
        elif len(d2) > 0:
            for r in d2:
                resp.append(f"Record {r[0]} was harvested at {r[3]} from {r[2]} but did not make it to the final catalogue (yet), {r[1]}")
        else:
            resp.append("Record not (yet) available in Soilwise")    

            # is id in openaire?
            req = f"https://api.openaire.eu/graph/v2/researchProducts?pid={item.split('doi.org/').pop()}"
            try:
                res = requests.get(req, headers={'accept':'application/json'})
                res2 = res.json()
                if res2 and 'results' in res2 and len(res2['results']) > 0:
                    prj = []
                    if 'projects' in res2:
                        for p in res2['projects']:  
                            prj.append({
                                'code':p.get('code',''),
                                'name':p.get('acronym',p.get('title','')),
                                'funder':p.get('funder','')})  
                        
                    if len(prj) == 0:
                        resp.append("""- Record is in OpenAire, but no project reference has been found. 
                        Contact the authors to update their funding reference.""")
                    else:
                        # check if grantnr is in list
                        qry3 = """SELECT grantnr, code FROM harvest.projects WHERE grantnr = ANY(:item)"""
                        d3 = await fetch_data(query=qry3, values={'item': [g['code'] for g in prj]})
                        if len (d3) > 0:
                            prjs = "; ".join([f"{gg['code']}:{gg['acronym']}" for gg in prj])
                            resp.append(f"""Record is included in OpenAire, and is related to project(s): 
                                    {prjs}. {d3[0][0]} is tagged by ESDAC as being soil related, 
                                    please contact Soilwise about this issue.""")
                        else:    
                            resp.append(f"""Record is included in OpenAire, and is related to project(s): 
                                    {prjs}. None of these projects is tagged by ESDAC as being soil related, 
                                    please contact ESDAC to suggest your project for inclusion.""")

                else:
                    resp.append(f"Record is not in OpenAire. ")
                    if 'zenodo' in item:
                        resp.append(f"Record identifier contains `zenodo`")
                        req = f"https://zenodo.org/api/records/{item.split('zenodo.').pop()}"
                        try:
                            res = requests.get(req, headers={'accept':'application/json'})
                            res2 = res.json()
                            if res2 and 'metadata' in res2:
                                resp.append(f"Record does exist in Zenodo, it may be indexed yet in OpenAire or indexing failed.")
                            else:
                                resp.append(f"Record is not available in Zenodo")
                        except Exception as e: 
                            resp.append(f"A query request to zenodo with that identifier failed, {e}")

                    # see if in Datacite
                    if validate_doi(item):
                        resp.append("Record is a valid DOI") 
                    else:
                        resp.append(f"Record is not a valid DOI") 

            except Exception as e: 
                resp.append(f"Error while processing DOI, {e}")
            
            resp.append(f"""Please notify the SoilWise team if you think this resource should
                        be included in SoilWise.""")


            # is id in data.europa.eu?  
            # try:
            #     mid = quote_plus(item.split('/').pop().split('?')[0])
            #     if mid not in [None,'']:
            #         quri = f"https://data.europa.eu/api/hub/search/datasets/{mid}"
            #         d = requests.get(quri,headers={'accept':'application/json'}).json()
            #         # does metadata include keyword soil?
            #         if d and d.get('result'):
            #             for kw in d.get('result').get('keywords',[]):
            #                 if "soil" in kw.get('label','') or "soil" in kw.get('id',''):
            #                     resp.append(f"record {mid} is in data.europa.eu, and has a `soil` keyword, it should be in soilwise")
            #                 else:  
            #                     resp.append(f"record {mid} is in data.europa.eu, but does <b>not</b> have a `soil` keyword")
            #         else:
            #             resp.append(f"record {mid} not in data.europa.eu")   
            # except Exception as e:
            #    resp.append(f"Generic error, {e}")      
            # is id in cordis?

            # Insert a log of this case
            query = "INSERT INTO harvest.doi_validate_history(date, ip, doi, msg) VALUES (LOCALTIMESTAMP, :ip, :doi, :msg)"
            values = {"doi": quote(item), "ip": ip ,"msg": ";".join(resp) }
            await database.execute(query=query, values=values)

    return resp

# helper function, check if record is already in soilwise
async def check_record_in_soilwise(doi: str) -> bool:
    qry = """SELECT identifier FROM metadata.records WHERE identifier = :doi"""
    d = await fetch_data(query=qry, values={'doi': doi})
    return len(d) > 0

# helper funtion to retrieve client IP, handling proxies
def get_ip(req):
    forwarded = req.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = req.client.host
    return ip

@app.post("/pid/suggest/{doi:path}",
          summary="Suggest a correction for a specific property of a record",
          description="""Suggest a correction for a specific property of a record, providing your name, email, and comment. The suggestion will be reviewed by the SoilWise team.""")
async def handle_form(
    request: Request,
    doi: str,
    name: str = Form(...),
    email: str = Form(...),
    comment: str = Form(...),
    property: str = Form(...),
    value: str = Form(...)
):

    # Get IP address (handles proxies too)
    ip = get_ip(request)

    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address") 

    if not await check_record_in_soilwise(doi):
        raise HTTPException(status_code=404, detail="Record not found in SoilWise")

    query = """
        INSERT INTO metadata.doi_prop_suggest (name, email, property, value, fk_record, comment, ip)
        VALUES (:name, :email, :property, :value, :doi, :comment, :ip)
    """

    values = {
        "name": name,
        "email": email,
        "property": property,
        "value": value,
        "doi": doi,
        "comment": comment,
        "ip": ip
    }

    try:
        await database.execute(query=query, values=values)

        return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pid/suggest",
          summary="Suggest a new DOI for inclusion in SoilWise",
          description="""Suggest a new DOI for inclusion in SoilWise, providing your name, email, and comment. The suggestion will be reviewed by the SoilWise team.""")
async def handle_form(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    comment: str = Form(...),
    doi: str = Form(...)
):
    
    # Get IP address (handles proxies too)
    ip = get_ip(request)

    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address") 

    if await check_record_in_soilwise(doi):
        raise HTTPException(status_code=400, detail="Record is already available in soilwise")

    print(f"New DOI suggestion received: {doi}")

    is_valid = await validate_doi(doi)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid DOI")

    query = """
        INSERT INTO harvest.doi_suggest (name, email, doi, comment, ip)
        VALUES (:name, :email, :doi, :comment, :ip)
    """

    values = {
        "name": name,
        "email": email,
        "doi": doi,
        "comment": comment,
        "ip": ip
    }

    try:
        await database.execute(query=query, values=values)

        return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


## version history 
@app.get('/history/{item:path}', 
         response_model=List[RecordResponse],
         summary="Retrieve the version history of a record in SoilWise",
         description="Retrieve the version history of a record in SoilWise, including all previous versions and their details.")
async def get_record_history(item: str):
    query = f"""SELECT identifier, itemtype, 
        resultobject, insert_date as date, title, source, project 
        FROM harvest.items where identifier=:id"""
    data = await fetch_data(query=query,values={ "id": item})
    print('dt',len(data))
    return data

## version history 
@app.get('/augments/{item:path}', 
         response_model=List[AugmentResponse],
         summary="Retrieve all augmentations made to a record in SoilWise",
         description="Retrieve all augmentations made to a record in SoilWise, including their details and timestamps.")
async def get_record_augments(item: str):
    query = f"""SELECT distinct on (a.property) a.property,
                    a.value as target, 
                    a.process, 
                    a.date
                FROM metadata.augments a 
                WHERE a.record_id=:id
                ORDER by a.property, a.date desc"""
    _data = await fetch_data(query=query,values={"id": item})
    data = [AugmentResponse(**row) for row in _data]
    for d in data:
        try:
            qry2 = f"""SELECT {d.property} FROM metadata.records where identifier=:id"""
            data2 = await database.fetch_all(query=qry2,values={"id": item})
            d.original = data2[0][0] if data2 and len(data2) > 0 else None
        except Exception as e:
            None # specific augment column does not exist

    return data



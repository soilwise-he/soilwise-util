from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv
from databases import Database
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import asyncpg, requests
import logging
import os

from urllib.parse import quote_plus, quote

# Load environment variables from .env file
load_dotenv()

# Database connection setup
DATABASE_URL = f"postgresql://{os.environ.get('POSTGRES_USER')}:{os.environ.get('POSTGRES_PASSWORD')}@{os.environ.get('POSTGRES_HOST')}:{os.environ.get('POSTGRES_PORT')}/{os.environ.get('POSTGRES_DB')}"

# if os.environ.get("POSTGRES_SCHEMA"):
#    unfortunately this does not work
#    DATABASE_URL += f"?options=-c+search_path%3D{quote_plus(os.environ.get('POSTGRES_SCHEMA'))}"

database = Database(DATABASE_URL)
schema = 'harvest'
if os.environ.get("POSTGRES_SCHEMA"):
    schema = os.environ.get("POSTGRES_SCHEMA")
print(f"DB: {DATABASE_URL.replace(os.environ.get('POSTGRES_PASSWORD'),'*****')}; Schema: {schema}")

rootpath = os.environ.get("ROOTPATH") or "/"

# FastAPI app instance
app = FastAPI(
    title="Soil-Mission-Feed-API",
    summary="Provide access to harvested feeds from Soil Mission projects",
    root_path=rootpath
)
logger = logging.getLogger(__name__)

# Define response models
class FeedResponse(BaseModel):
    published: Optional[datetime] = None
    title: Optional[str] = None 
    summary: Optional[str] = None 
    link: Optional[str] = None 
    image: Optional[str] = None 
    author: Optional[str] = None 
    tags: Optional[str] = None 

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

# Endpoint to retrieve data with redirection statuses
@app.get('/items', response_model=List[FeedResponse])
async def get_items(offset: int = 0, limit: int = 10, keywords: str = '', project: str = ''):
    query = f"SELECT * FROM {schema}.feeds f left join {schema}.projects p on f.project = p.code where " # join on code because it is always populated
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

# Endpoint to get status of a doi
@app.get('/status/{item:path}', response_model=List[str])
async def status(item):
    resp = [f"Test item {quote(item)}"]
    if item:
        
        # is id in soilwise?
        qry1 = """SELECT identifier from public.records WHERE identifier like :item or identifier like :splititem"""
        d1 = await fetch_data(query=qry1, values={'item': '%'+item, 'splititem': '%'+(item.split('/').pop() or 'random-non-matching-string') })
        qry2 = """SELECT identifier,error from harvest.items WHERE identifier like :item or identifier like :splititem"""
        d2 = await fetch_data(query=qry2, values={'item': item, 'splititem': '%'+(item.split('/').pop() or 'random-non-matching-string')})
        if len(d1) > 0:
            resp.append(f"Record {d1[0][0]} exists in Soilwise")
        elif len(d2) > 0:
            resp.append(f"Record {d2[0][0]} was harvested but did not make it to the final catalogue; {d2[0][1]}")
        else:
            resp.append("Record not available in Soilwise")    
            
            # is id in openaire?
            req = f"https://api.openaire.eu/search/researchProducts?format=json&doi={item.split('doi.org/').pop()}"
            try:
                res = requests.get(req,headers={'accept':'application/json'})
                res2 = res.json()
                if res2:
                    res3 = res2.get('response',{}).get('results')
                    if res3: 
                        rels2 = res3.get('result',[{}])[0].get('metadata',{}).get('oaf:entity',{}).get('oaf:result',{}).get('rels',{})
                        if rels2:
                            rels = rels2.get('rel',[{}])
                            code = ''
                            acronym = ''
                            if isinstance(rels, dict):
                                rels = [rels] 
                            for r in rels:
                                print('r', r)
                                if isinstance(r, dict) and r.get('funding',{}).get('funder',{}).get('@name') == 'European Commission':
                                    code = r.get('code',{}).get('$','')
                                    acronym = r.get('acronym',{}).get('$','')
                            if code == '':
                                resp.append("Record is in OpenAire, but no relevant HE grantnr has been found")
                            else:
                                # check if grantnr is in list
                                qry3 = """SELECT grantnr, code FROM harvest.projects WHERE grantnr = :item"""
                                d3 = await fetch_data(query=qry3, values={'item': code})
                                if len (d3) > 0:
                                    resp.append(f"Record is included in OpenAire, and is related to project {code}:{acronym}, that project is tagged by ESDAC as being soil related")
                                else:    
                                    resp.append(f"Record is included in OpenAire, and is related to project {code}:{acronym}, however that project is not tagged by ESDAC as being soil related")
                        else:
                            resp.append(f"Record has no funding relations") 
                    else:
                        resp.append(f"Record is not in OpenAire")
                        # see if in Datacite
                        req2 = f"https://doi.org/{item.split('doi.org/').pop()}"
                        try:
                            res2 = requests.get(req2,headers={'accept':'application/x-bibtex'})
                            resp.append(f"Record is bibtex; {res2.text()}") 
                        except Exception as e:
                            resp.append(f"Error query bibtex, {e}") 
                else:
                    resp.append(f"No OpenAire result") 
                
            except Exception as e: 
                resp.append(f"Error while querying OpenAire, {e}")
        
    return resp

    # is id in data.europa.eu?  

    # quri = f"https://data.europa.eu/api/hub/search/datasets/{}"
    #try:
    #            d = requests.get(req,headers={'accept':'application/json'}).json()

        # does metadata include keyword soil?
    # is id in cordis?



# Start the application
@app.on_event('startup')
async def startup():
    try:
        await database.connect()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database connection failed") from e

@app.on_event('shutdown')
async def shutdown():
    try:
        await database.disconnect()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database disconnection failed") from e
from fastapi import FastAPI, HTTPException, Query
from dotenv import load_dotenv
from databases import Database
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import asyncpg
import logging
import os
from urllib.parse import quote_plus

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
async def get_items(offset: int = 0, limit: int = 10):
    query = f"""
        SELECT *
        FROM {schema}.feeds 
        ORDER by published desc
        limit :limit offset :offset
    """
    data = await fetch_data(query=query,values={'limit':limit,'offset':offset})
    return data

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
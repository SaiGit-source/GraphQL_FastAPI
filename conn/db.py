import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

def get_db():
    uri = os.getenv("MONGODB_URI")
    client = MongoClient(uri)
    db = client["FastAPI_GraphQL"]
    return db

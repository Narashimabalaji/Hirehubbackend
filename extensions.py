# # extensions.py
# from flask_sqlalchemy import SQLAlchemy

# db = SQLAlchemy()

from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017")  # or your Render URL
db = client["job_portal"]  # or your DB name


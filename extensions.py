# # extensions.py
# from flask_sqlalchemy import SQLAlchemy

# db = SQLAlchemy()

from pymongo import MongoClient
client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")  # or your Render URL
db = client["job_portal"]  # or your DB name


from flask import Blueprint, request, jsonify
from models.users import create_job
from pymongo import MongoClient

hirer_bp = Blueprint("hirer", __name__)

# @hirer_bp.route("/post-job", methods=["POST"])
# def post_job():
#     data = request.get_json()
#     job_id = create_job(data)
#     return jsonify({"message": "Job submitted for approval", "job_id": job_id}), 201

client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db_jobportal = client["job_portal"]

@hirer_bp.route("/post-job", methods=["POST"])
def post_job():
    data = request.get_json()

    required = ["title", "description", "hireremailid"]
    if not all(key in data for key in required):
        return jsonify({"error": "Missing required fields"}), 400

    emailid = data["emailid"]

    # Check if hirer exists
    emailid = db_jobportal.hirers.find_one({"emailid": emailid})

    if hirer:
        jobposts = hirer.get("jobposts", [])
        if len(jobposts) >= 25:
            return jsonify({
                "error": "Job post limit reached",
                "message": "You have reached the limit of 25 job posts. For more, contact support@hirehub.com"
            }), 403
    else:
        # New hirer, create document with hirer_id
        hirer = {
            "emailid": emailid,
            "userType": "hirer",
            "hirer_id": str(ObjectId()),  # permanent unique ID
            "jobposts": []
        }
        db_jobportal.hirers.insert_one(hirer)

    # Create the job post
    job = {
        "id": str(ObjectId()),
        "title": data["title"],
        "description": data["description"],
        "qualification": data.get("qualification", ""),
        "category": data.get("category", ""),
        "keywords": data.get("keywords", []),
        "status": "pending",
        "created_by": hirer["hirer_id"],
        "created_at": datetime.utcnow()
    }

    # Append to jobposts
    db_jobportal.hirers.update_one(
        {"emailid": hirer_email},
        {"$push": {"jobposts": job}}
    )

    # Return updated structure
    updated = db_jobportal.hirers.find_one({"emailid": hirer_email})
    jobposts = updated.get("jobposts", [])

    return jsonify({
        "emailid": updated["emailid"],
        "userType": updated["userType"],
        "hirer_id": updated["hirer_id"],
        "jobscount": len(jobposts),
        "jobposts": jobposts
    }), 201

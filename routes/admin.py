from flask import Blueprint, request, jsonify
from models.users import approve_job,reject_job
admin_blp = Blueprint("admin", __name__)

@admin_blp.route("/approve-job/<job_id>", methods=["POST"])
def approve(job_id):
    approve_job(job_id)
    return jsonify({"message": "Job approved"}), 200

@admin_blp.route("/reject_job/<job_id>", methods=["POST"])
def reject(job_id):
    reject_job(job_id)
    return jsonify({"message": "rejected"}), 200



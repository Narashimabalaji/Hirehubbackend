from flask import request, jsonify,Blueprint
from flask_restful import Resource, Api
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import users_collection 

from utils.auth import generate_accesstoken, generate_refresh_token, decode_token,user_refresh_tokens, monitor_token_expiry,REFRESH_SECRET
from datetime import datetime, timedelta, timezone
from extensions import db


user_access_bp = Blueprint('user_access', __name__)

users_collection = db["users"] 



        
@user_access_bp.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        Emailid = data.get("Emailid")
        password = data.get("password")
        userType = data.get("userType")

        if not Emailid or not password:
            return jsonify({"message": "Emailid or password is missing"}), 400

        existing_user = users_collection.find_one({"Emailid": Emailid})
        if existing_user:
            return jsonify({"message": "Emailid already taken"}), 400

        hashed_password = generate_password_hash(password)

        
        users_collection.insert_one({
            "Emailid": Emailid,
            "password": hashed_password,
            "userType": userType
        })

        return jsonify({"message": "User created successfully"}), 201

    except Exception as e:
        return jsonify({"message": "Internal server error", "error": str(e)}), 500



@user_access_bp.route("/login", methods=["POST"])
def login_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "No input data provided"}), 400

        Emailid = data.get("Emailid")
        password = data.get("password")

        user = users_collection.find_one({"Emailid": Emailid})
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"message": "Invalid credentials"}), 400

        user_id = str(user["_id"])
        access_token, access_exp = generate_accesstoken(user_id)

        existing_refresh = user_refresh_tokens.get(user_id)
        now = datetime.now(tz=timezone.utc)

        if existing_refresh and now < existing_refresh["expires_at"]:
            refreshToken = existing_refresh["refreshToken"]
            refresh_exp = existing_refresh["expires_at"]
        else:
            refreshToken, refresh_exp = generate_refresh_token(user_id)

        return jsonify({
            "user_id": user_id,
            "Emailid": user["Emailid"],
            "access_token": access_token,
            "refresh_token": refreshToken,
            "userType": user.get("userType")
        }), 200

    except Exception as e:
        return jsonify({"message": "Internal server error", "error": str(e)}), 500

@user_access_bp.route('/protected', methods=['GET'])
def protected_resource():
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"message": "Missing token. Please log in."}), 401

        token = auth_header.split(" ")[1] if " " in auth_header else auth_header

        payload, error = decode_token(token)
        if error:
            return jsonify({"message": error}), 401

        return jsonify({"message": "You are authorized!"}), 200

    except Exception as e:
        return jsonify({"message": "Internal server error", "error": str(e)}), 500

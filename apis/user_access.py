from flask import request, jsonify,Blueprint
from flask_restful import Resource, Api
from werkzeug.security import generate_password_hash, check_password_hash
from models.users import users_collection 
from utils.auth import generate_accesstoken, generate_refresh_token, decode_token,user_refresh_tokens, monitor_token_expiry,REFRESH_SECRET
from datetime import datetime, timedelta, timezone
from extensions import db
import smtplib
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.security import generate_password_hash
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText





user_access_bp = Blueprint('user_access', __name__)

users_collection = db["users"] 
serializer = URLSafeTimedSerializer("SUPER_SECRET_KEY")

EMAIL_HOST="smtp.gmail.com"
EMAIL_PORT=587
EMAIL_ADDRESS="GadgetZoneEcom@gmail.com"
EMAIL_PASSWORD="icho xyqy mgsu qrdv"



def send_email(to_email, subject, body):
    from_email = EMAIL_ADDRESS
    password = EMAIL_PASSWORD
    host = EMAIL_HOST
    port = EMAIL_PORT

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False


        
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
            "Emailid":user.get("Emailid")
            "userType": user.get("userType"),
            
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

# === Forgot Password Endpoint ===
@user_access_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email")

        if not email:
            return jsonify({"message": "Email is required"}), 400

        user = users_collection.find_one({"Emailid": email})
        if not user:
            return jsonify({"message": "User not found"}), 404

        token = serializer.dumps(email, salt='reset-password')
        reset_url = f"https://hirehubbackend-5.onrender.com/reset-password/{token}"

        body = f"""
Hi,

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

- Hire Hub Team
"""
        send_email(email, "Reset Your Password", body)

        return jsonify({"message": "Password reset link sent to your email"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === Reset Password Endpoint ===
@user_access_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    try:
        data = request.get_json()
        new_password = data.get("password")

        if not new_password:
            return jsonify({"message": "Password is required"}), 400

        try:
            email = serializer.loads(token, salt='reset-password', max_age=3600)
        except SignatureExpired:
            return jsonify({"message": "The token has expired"}), 400
        except BadSignature:
            return jsonify({"message": "Invalid token"}), 400

        hashed_pw = generate_password_hash(new_password)
        db_jobportal.users.update_one({"Emailid": email}, {"$set": {"password": hashed_pw}})

        return jsonify({"message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
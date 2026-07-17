import os
MONGO_URI = os.environ.get("MONGO_URI" , "")
DATABASE_NAME = os.getenv("DATABASE_NAME", "resunexus")

USERS_COLLECTION = os.getenv("USERS_COLLECTION", "users")
JWT_SECRET = os.getenv("JWT_SECRET")

JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256"
)

JWT_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_EXPIRE_MINUTES",
        60
    )
)
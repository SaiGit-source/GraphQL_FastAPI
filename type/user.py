import strawberry
import typing
from bson import ObjectId
from conn.db import get_db
from models.user import UserModel

@strawberry.type
class UserType:
    id: str
    name: str
    age: int
    phone: str
    
@strawberry.type
class Query:
    @strawberry.field
    def users(self) -> typing.List[UserType]:
        db = get_db()
        users = db.users.find()
        return [UserType(id=str(user["_id"]), name=user["name"], age=user["age"], phone=user["phone"]) for user in users]    
    @strawberry.field
    def user(self, id: str) -> UserType:
        db = get_db()
        user = db.users.find_one({"_id": ObjectId(id)})
        if user:
            return UserType(id=str(user["_id"]), name=user["name"], age=user["age"], phone=user["phone"])
        return None
    
@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_user(self, name: str, age: int, phone: str) -> UserType:
        db = get_db()
        user = UserModel(name=name, age=age, phone=phone)
        result = db.users.insert_one(user.dict())
        return UserType(id=str(result.inserted_id), name=user.name, age=user.age, phone=user.phone)
    @strawberry.mutation
    def update_user(self, id: str, name: str, age: int, phone: str) -> UserType:
        db = get_db()
        result = db.users.update_one({"_id": ObjectId(id)}, {"$set": {"name": name, "age": age, "phone": phone}})
        if result.modified_count > 0:
            return UserType(id=id, name=name, age=age, phone=phone)
        return None
    @strawberry.mutation
    def delete_user(self, id: str) -> bool:
        db = get_db()
        result = db.users.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0

from fastapi import APIRouter
import strawberry
from conn.db import get_db
from models.user import UserModel
from type.user import Mutation, Query
from type.user import UserType
from strawberry.asgi import GraphQL

user = APIRouter()
schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQL(schema)
user.add_route("/graphql", graphql_app)


from fastapi import APIRouter

from app.api import agents, conversations, deployments, documents, jobs, models, runtimes, samples

api_router = APIRouter(prefix="/api")
for module in (models, runtimes, deployments, samples, agents, jobs, documents, conversations):
    api_router.include_router(module.router)

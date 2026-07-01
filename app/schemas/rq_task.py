from pydantic import BaseModel

class RQTaskRequest(BaseModel):
    message: str
class RQTaskResponse(BaseModel):
    status:str
    job_id: str
class RQJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: str|None = None
    error: str|None = None
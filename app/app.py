from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class Input(BaseModel):
    x: float

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(data: Input):
    return {"prediction": data.x * 2}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

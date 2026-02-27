import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.routing import router
from services.data_loader import data_store

app = FastAPI(title="Planning Service API", description="Prototype GIS planning backend for last-mile fiber routing")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data into memory at startup
@app.on_event("startup")
def startup_event():
    data_store.load_data()

# Include routers
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.server:app",
        host    = "0.0.0.0",
        port    = 8080,
        reload  = False,
        workers = 1,  # must be 1 - in-memory state is not process-safe
    )
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/employees")
async def get_employees(name):
    rst = f"{name}님 반갑습니다."
    return {"response": rst}
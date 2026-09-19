from fastapi import FastAPI  # Or: from flask import Flask

# Vercel specifically looks for a top-level variable named 'app'
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "online"}
  

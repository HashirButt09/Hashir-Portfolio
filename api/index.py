import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production URL later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
@app.get("/health")
@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend is running!"}

class ContactForm(BaseModel):
    name: str
    email: str
    subject: str
    message: str

# Use the key copied from your "Email Reputation" section
ABSTRACT_API_KEY = os.getenv("ABSTRACT_API_KEY", "1240b693709b4eaca3f9b6d307b12b1a")
FORMSPREE_ENDPOINT = "https://formspree.io/f/xwvgznvz"

@app.post("/api/contact")
@app.post("/contact")
async def verify_and_send(data: ContactForm):
    # 1. Query Abstract API
    verify_url = f"https://emailvalidation.abstractapi.com/v1/?api_key={ABSTRACT_API_KEY}&email={data.email}"
    
    # Disable SSL verification and set a relaxed timeout of 20 seconds
    async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
        try:
            response = await client.get(verify_url)
            
            # If quota exceeded (100/100 used), fallback to allow sending
            if response.status_code == 429:
                print("Abstract API Quota Exceeded. Proceeding without inbox check.")
            elif response.status_code == 200:
                result = response.json()
                
                # Check deliverability status returned by Abstract API
                deliverability = result.get("deliverability")
                is_valid_format = result.get("is_valid_format", {}).get("value")
                
                if deliverability == "UNDELIVERABLE" or is_valid_format is False:
                    raise HTTPException(
                        status_code=400, 
                        detail="This email address does not exist or cannot receive mail."
                    )
        except HTTPException as he:
            # Re-raise standard HTTP exceptions from validation rules
            raise he
        except Exception as e:
            # Fallback gracefully if API service goes down temporarily
            print("Error verifying email via Abstract API:")
            import traceback
            traceback.print_exc()
            pass

    # 2. Forward message to Formspree if valid
    async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
        try:
            form_response = await client.post(
                FORMSPREE_ENDPOINT,
                json=data.dict(),
                headers={"Accept": "application/json"}
            )
            if form_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to deliver message.")
        except HTTPException as he:
            raise he
        except Exception as fe:
            print("Error forwarding message to Formspree:")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500, 
                detail=f"Delivery endpoint error: {fe.__class__.__name__} - {str(fe)}"
            )

    return {"status": "success", "message": "Message verified and sent successfully!"}

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path_name: str):
    return {
        "request_url": str(request.url),
        "path_name": path_name,
        "root_path": request.scope.get("root_path"),
        "path": request.scope.get("path"),
        "query_string": request.scope.get("query_string", b"").decode(),
        "detail": "This is a catch-all debug route"
    }

if __name__ == "__main__":
    # Get port from environment or fallback to standard port
    port = int(os.environ.get("PORT", 5000))
    # Ensure the parent directory is in sys.path so uvicorn can find the 'api' module
    import sys
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    uvicorn.run("api.index:app", host="0.0.0.0", port=port, reload=False)

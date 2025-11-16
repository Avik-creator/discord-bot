"""
FastAPI server for CSV upload endpoint to update/insert player cards
"""
import csv
import io
import logging
import json
from typing import List, Dict
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.database import AsyncSessionLocal
from database.models import Card, CardType
import config

logger = logging.getLogger('api_server')

# Discord signature verification
try:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    HAS_NACL = True
except ImportError:
    HAS_NACL = False
    logger.warning("PyNaCl not installed. Discord signature verification will be disabled.")

app = FastAPI(title="Football Card Bot API", version="1.0.0")

def parse_card_type(event_str: str) -> CardType:
    """Parse event string to CardType enum"""
    event_lower = event_str.lower().strip()
    if event_lower == "base":
        return CardType.BASE
    elif event_lower == "icon":
        return CardType.ICON
    elif event_lower in ["event", "totw", "tots", "toty", "ucl", "uel", "international", "special", 
                         "ballon d'or", "bdor", "summer stars", "flashback", "boxing day"]:
        return CardType.EVENT
    else:
        # Default to BASE if unknown
        return CardType.BASE

def extract_event_type(event_str: str) -> str:
    """Extract event type from event string"""
    event_lower = event_str.lower().strip()
    if event_lower in ["base", "icon"]:
        return None
    
    # Map common event names
    event_map = {
        "totw": "TOTW",
        "tots": "TOTS",
        "toty": "TOTY",
        "ucl": "UCL",
        "uel": "UEL",
        "international": "International",
        "special": "Special",
        "ballon d'or": "Ballon d'Or",
        "bdor": "Ballon d'Or",
        "summer stars": "Summer Stars",
        "flashback": "Flashback",
        "boxing day": "Boxing Day"
    }
    
    return event_map.get(event_lower, event_str.title())

async def process_csv_row(session: AsyncSession, row: Dict[str, str], row_num: int) -> Dict[str, any]:
    """Process a single CSV row and update/insert card"""
    try:
        # Extract required fields
        player_name = row.get('player', '').strip()
        event = row.get('event', '').strip()
        attack_str = row.get('attack', '').strip()
        defence_str = row.get('defence', '').strip() or row.get('defense', '').strip()
        position = row.get('position', '').strip().upper()
        
        # Validate required fields
        if not player_name:
            return {"row": row_num, "status": "error", "message": "Missing player name"}
        
        if not attack_str or not defence_str:
            return {"row": row_num, "status": "error", "message": "Missing attack or defence stats"}
        
        if not position:
            return {"row": row_num, "status": "error", "message": "Missing position"}
        
        # Validate position
        if position not in config.VALID_POSITIONS:
            return {"row": row_num, "status": "error", "message": f"Invalid position: {position}"}
        
        # Parse stats
        try:
            attack = int(attack_str)
            defence = int(defence_str)
        except ValueError:
            return {"row": row_num, "status": "error", "message": "Invalid attack or defence value (must be integer)"}
        
        # Calculate overall rating
        overall_rating = max(attack, defence)
        
        # Parse card type and event type
        card_type = parse_card_type(event)
        event_type = extract_event_type(event) if card_type == CardType.EVENT else None
        
        # Check if card exists (by name, case-insensitive)
        result = await session.execute(
            select(Card).where(Card.name.ilike(player_name))
        )
        existing_card = result.scalar_one_or_none()
        
        if existing_card:
            # Update existing card
            existing_card.attack_stat = attack
            existing_card.defense_stat = defence
            existing_card.overall_rating = overall_rating
            existing_card.position = position
            existing_card.card_type = card_type
            if event_type:
                existing_card.event_type = event_type
            
            await session.flush()
            return {
                "row": row_num,
                "status": "updated",
                "player": player_name,
                "card_id": existing_card.id
            }
        else:
            # Insert new card
            new_card = Card(
                name=player_name,
                position=position,
                attack_stat=attack,
                defense_stat=defence,
                overall_rating=overall_rating,
                card_type=card_type,
                event_type=event_type
            )
            session.add(new_card)
            await session.flush()
            await session.refresh(new_card)
            
            return {
                "row": row_num,
                "status": "inserted",
                "player": player_name,
                "card_id": new_card.id
            }
    
    except Exception as e:
        logger.error(f"Error processing row {row_num}: {e}")
        return {
            "row": row_num,
            "status": "error",
            "message": str(e)
        }

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Football Card Bot API is running"}

def verify_discord_signature(body: bytes, signature: str, timestamp: str) -> bool:
    """
    Verify Discord request signature using Ed25519
    """
    if not HAS_NACL:
        logger.warning("PyNaCl not available, skipping signature verification")
        return True  # Allow request if PyNaCl is not installed
    
    try:
        # Get public key from config
        public_key = config.DISCORD_PUBLIC_KEY
        
        # Create verify key
        verify_key = VerifyKey(bytes.fromhex(public_key))
        
        # Create message to verify: timestamp + body
        message = timestamp.encode() + body
        
        # Verify signature
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError, Exception) as e:
        logger.error(f"Signature verification failed: {e}")
        return False

@app.post("/interactions")
async def discord_interactions(request: Request):
    """
    Discord Interactions Endpoint for verification
    Handles PING requests for endpoint verification
    """
    try:
        # Get headers (Discord sends X-Signature-Ed25519 and X-Signature-Timestamp)
        headers = request.headers
        x_signature_ed25519 = headers.get("x-signature-ed25519") or headers.get("X-Signature-Ed25519")
        x_signature_timestamp = headers.get("x-signature-timestamp") or headers.get("X-Signature-Timestamp")
        
        # Read body
        body = await request.body()
        
        # Verify signature if headers are provided
        if x_signature_ed25519 and x_signature_timestamp:
            if not verify_discord_signature(body, x_signature_ed25519, x_signature_timestamp):
                logger.warning("Invalid Discord signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            # For initial verification, Discord might send a request without signature
            # Log it but allow it to proceed
            logger.info("Discord interaction received without signature headers (may be initial verification)")
        
        # Parse request body
        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            # If body is empty or not JSON, return PONG for verification
            logger.info("Empty or non-JSON body, returning PONG for verification")
            return JSONResponse(content={"type": 1})
        
        # Handle PING request (Discord sends this to verify the endpoint)
        if data.get('type') == 1:  # PING
            logger.info("Received Discord PING, responding with PONG")
            return JSONResponse(content={"type": 1})  # PONG response
        
        # For other interaction types, you would handle them here
        # For now, just return PONG for verification
        logger.info(f"Received Discord interaction type: {data.get('type')}")
        return JSONResponse(content={"type": 1})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Discord interaction: {e}", exc_info=True)
        # Return PONG even on error to help with verification
        return JSONResponse(content={"type": 1}, status_code=200)

@app.get("/interactions")
async def discord_interactions_get():
    """
    GET endpoint for Discord verification (some setups require this)
    """
    return {"status": "ok", "message": "Discord Interactions Endpoint"}

@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload CSV file to update/insert player cards
    
    CSV format:
    - Headers: event, player, attack, defence, position
    - event: base, icon, or event type (totw, tots, etc.)
    - player: Player name
    - attack: Attack stat (integer)
    - defence: Defence stat (integer)
    - position: Player position (GK, ST, etc.)
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    try:
        # Read CSV content
        contents = await file.read()
        csv_content = contents.decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        # Validate headers
        required_headers = {'event', 'player', 'attack', 'position'}
        headers = set(csv_reader.fieldnames or [])
        
        # Check for defence/defense header (accept either)
        has_defence = 'defence' in headers or 'defense' in headers
        if not has_defence:
            missing = required_headers | {'defence'} - headers
            raise HTTPException(
                status_code=400,
                detail=f"Missing required headers: {missing}. Found headers: {headers}. Note: 'defence' or 'defense' is required."
            )
        
        # Check other required headers
        missing = required_headers - headers
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required headers: {missing}. Found headers: {headers}"
            )
        
        # Process rows
        results = []
        async with AsyncSessionLocal() as session:
            row_num = 1  # Start from 1 (header is row 0)
            for row in csv_reader:
                row_num += 1
                result = await process_csv_row(session, row, row_num)
                results.append(result)
            
            # Commit all changes
            await session.commit()
        
        # Count statistics
        updated_count = sum(1 for r in results if r.get("status") == "updated")
        inserted_count = sum(1 for r in results if r.get("status") == "inserted")
        error_count = sum(1 for r in results if r.get("status") == "error")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Processed {len(results)} rows",
                "statistics": {
                    "total_rows": len(results),
                    "updated": updated_count,
                    "inserted": inserted_count,
                    "errors": error_count
                },
                "results": results
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


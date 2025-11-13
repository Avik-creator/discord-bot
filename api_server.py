"""
FastAPI server for CSV upload endpoint to update/insert player cards
"""
import csv
import io
import logging
from typing import List, Dict
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.database import AsyncSessionLocal
from database.models import Card, CardType
import config

logger = logging.getLogger('api_server')

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


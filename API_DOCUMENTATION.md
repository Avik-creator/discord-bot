# API Documentation

## CSV Upload Endpoint

### Endpoint
`POST /api/upload-csv`

### Description
Upload a CSV file to update existing player cards or insert new ones. The endpoint matches cards by player name (case-insensitive) and updates existing records or creates new ones.

### Request
- **Method**: POST
- **Content-Type**: multipart/form-data
- **Body**: CSV file upload

### CSV Format

The CSV file must have the following headers:

| Header | Required | Description | Example |
|--------|----------|-------------|---------|
| `event` | Yes | Card type: `base`, `icon`, or event type (`totw`, `tots`, `toty`, `ucl`, `uel`, `international`, `special`, `ballon d'or`, `bdor`, `summer stars`, `flashback`, `boxing day`) | `base` |
| `player` | Yes | Player name | `Lionel Messi` |
| `attack` | Yes | Attack stat (integer) | `94` |
| `defence` or `defense` | Yes | Defence stat (integer) | `46` |
| `position` | Yes | Player position (must be one of the valid positions) | `ST` |

### Valid Positions
- `GK` (Goalkeeper)
- `LB`, `LWB`, `LCB`, `CB`, `RCB`, `RWB`, `RB` (Defenders)
- `LDM`, `CDM`, `RDM` (Defensive Midfielders)
- `LM`, `LCM`, `CM`, `RCM`, `RM` (Midfielders)
- `LAM`, `CAM`, `RAM` (Attacking Midfielders)
- `LW`, `ST`, `CF`, `RW` (Forwards)

### Example CSV

```csv
event,player,attack,defence,position
base,Lionel Messi,94,46,ST
icon,Cristiano Ronaldo,94,39,ST
totw,Kylian Mbappé,96,50,ST
base,Virgil van Dijk,60,92,CB
```

### Response

#### Success Response (200 OK)

```json
{
  "status": "success",
  "message": "Processed 4 rows",
  "statistics": {
    "total_rows": 4,
    "updated": 2,
    "inserted": 2,
    "errors": 0
  },
  "results": [
    {
      "row": 2,
      "status": "updated",
      "player": "Lionel Messi",
      "card_id": 123
    },
    {
      "row": 3,
      "status": "inserted",
      "player": "Kylian Mbappé",
      "card_id": 456
    }
  ]
}
```

#### Error Response (400 Bad Request)

```json
{
  "detail": "Missing required headers: {'defence'}. Found headers: {'event', 'player', 'attack', 'position'}"
}
```

### Behavior

1. **Matching**: Cards are matched by player name (case-insensitive). If a card with the same name exists, it will be updated. Otherwise, a new card will be created.

2. **Overall Rating**: Automatically calculated as `max(attack, defence)`.

3. **Card Type**: 
   - `base` → CardType.BASE
   - `icon` → CardType.ICON
   - Any other value → CardType.EVENT (with event_type set)

4. **Event Type**: For event cards, the event type is extracted from the `event` field (e.g., `totw` → `TOTW`, `ballon d'or` → `Ballon d'Or`).

### Usage Examples

#### Using cURL

```bash
curl -X POST "http://localhost:8000/api/upload-csv" \
  -F "file=@players.csv"
```

#### Using Python

```python
import requests

url = "http://localhost:8000/api/upload-csv"
files = {"file": open("players.csv", "rb")}
response = requests.post(url, files=files)
print(response.json())
```

#### Using JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('http://localhost:8000/api/upload-csv', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

### Health Check

#### Endpoint
`GET /api/health`

#### Response
```json
{
  "status": "healthy"
}
```

### Configuration

The API server runs on:
- **Host**: `0.0.0.0` (configurable via `API_SERVER_HOST` environment variable)
- **Port**: `8000` (configurable via `API_SERVER_PORT` environment variable)

### Notes

- The API server runs alongside the Discord bot automatically when you start `bot.py`
- All database operations are transactional - if any row fails, the entire batch is rolled back
- Player names are matched case-insensitively
- The endpoint validates all input data before processing


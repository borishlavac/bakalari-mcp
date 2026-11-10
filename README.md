# Bakaláři MCP server

Read-only MCP server nad Bakalář API 3 (streamable HTTP). Tools: `get_user_info`, `get_marks`,
`get_timetable`, `get_permanent_timetable`, `get_komens_received`, `get_absence`, `get_subjects`.

## Proměnné prostředí

| Klíč | Popis |
|---|---|
| `BAKALARI_URL` | adresa Bakalářů školy, např. `https://bakalari.skola.cz` |
| `BAKALARI_USER` / `BAKALARI_PASS` | přihlašovací údaje |
| `MCP_AUTH_TOKEN` | tajný token, bez něj server vrací 401 |
| `PORT`, `HOST` | nastavuje hosting (Render), výchozí 8000 / 0.0.0.0 |
| `ALLOWED_HOSTS` | volitelné, zapne kontrolu Host hlavičky |

## Render (free)

- Build: `pip install -r requirements.txt`
- Start: `python server.py`
- Env: viz tabulka, plus `PYTHON_VERSION=3.12.8`

## Ověření

- `GET /health` -> `{"ok":true}`
- `GET /mcp` bez tokenu -> 401
- Claude konektor: `https://<sluzba>.onrender.com/mcp?token=<MCP_AUTH_TOKEN>`

## Lokálně

```bash
pip install -r requirements.txt
cp .env.example .env   # vyplnit, pak nacist do prostredi
python server.py
```

`.env` nikdy necommituj.

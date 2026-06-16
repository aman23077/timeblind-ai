from fastapi import HTTPException


def not_found(entity_name: str, entity_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity_name} '{entity_id}' was not found.")

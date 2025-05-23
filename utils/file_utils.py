import os
import uuid
from pathlib import Path

def generate_temp_file_path(extension: str) -> str:
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    return str(temp_dir / f"{uuid.uuid4()}.{extension}")
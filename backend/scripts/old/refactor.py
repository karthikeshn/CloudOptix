import os
import shutil

backend_dir = r"d:\FinOpsDashboard\backend"

# Create directories
os.makedirs(os.path.join(backend_dir, "api", "routers"), exist_ok=True)
os.makedirs(os.path.join(backend_dir, "core"), exist_ok=True)
os.makedirs(os.path.join(backend_dir, "models"), exist_ok=True)
os.makedirs(os.path.join(backend_dir, "schemas"), exist_ok=True)

# 1. Move database.py, models.py, schemas.py
if os.path.exists(os.path.join(backend_dir, "database.py")):
    shutil.move(os.path.join(backend_dir, "database.py"), os.path.join(backend_dir, "core", "database.py"))
if os.path.exists(os.path.join(backend_dir, "models.py")):
    shutil.move(os.path.join(backend_dir, "models.py"), os.path.join(backend_dir, "models", "__init__.py"))
if os.path.exists(os.path.join(backend_dir, "schemas.py")):
    shutil.move(os.path.join(backend_dir, "schemas.py"), os.path.join(backend_dir, "schemas", "__init__.py"))
if os.path.exists(os.path.join(backend_dir, "auth.py")):
    shutil.move(os.path.join(backend_dir, "auth.py"), os.path.join(backend_dir, "core", "security.py"))

# Update imports in core/security.py
security_path = os.path.join(backend_dir, "core", "security.py")
with open(security_path, "r") as f:
    content = f.read()
content = content.replace("import database", "from core import database")
with open(security_path, "w") as f:
    f.write(content)

# Update imports in models/__init__.py
models_path = os.path.join(backend_dir, "models", "__init__.py")
with open(models_path, "r") as f:
    content = f.read()
content = content.replace("from database import Base", "from core.database import Base")
with open(models_path, "w") as f:
    f.write(content)

# We will create routers next
print("File moving completed successfully.")

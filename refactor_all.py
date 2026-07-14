import ast
import os
import shutil

app_file = "src/reaper/web/app_async.py"
backup_file = "src/reaper/web/app_async.py.bak"

# Restore from backup
shutil.copy(backup_file, app_file)

with open(app_file, "r") as f:
    source = f.read()

tree = ast.parse(source)

# 1. Routes to extract
def get_router_for_path(path: str) -> str:
    if path.startswith("/api/settings"): return "settings"
    if path.startswith("/api/vault") or path.startswith("/api/credentials"): return "vault"
    if path.startswith("/api/financial"): return "financial"
    if path.startswith("/api/finops"): return "finops"
    if path.startswith("/api/resources"): return "resources"
    if path.startswith("/api/cost-optimization") or path.startswith("/api/cost-reports"): return "cost_optimization"
    return None

routers_content = {
    "settings": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["settings"])\n\n',
    "vault": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["vault"])\n\n',
    "financial": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["financial"])\n\n',
    "finops": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["finops"])\n\n',
    "resources": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["resources"])\n\n',
    "cost_optimization": 'from fastapi import APIRouter\nrouter = APIRouter(tags=["cost_optimization"])\n\n',
}

# 2. Helpers to move
move_map = {
    "_vault_settings_row": "vault",
    "_vault_salt_bytes": "vault",
    "_is_vault_unlocked": "vault",
    "_session_fernet": "vault",
    "_unlock_vault_session": "vault",
    "handle_set_currency": "settings",
    "handle_sync_pricebook": "settings",
    "handle_set_strategy": "settings",
    "handle_save_subscriptions": "settings",
    "handle_set_sleep_schedule": "settings",
    "handle_update_compliance": "settings",
    "handle_update_integrations": "settings",
    "handle_update_billing": "settings",
    "handle_initial_setup": "settings",
    "_write_gcp_service_account_file": "settings",
    "_write_kubeconfig_file": "settings",
    "_set_cloud_env": "settings",
    "_validate_cloud_credentials": "settings",
    "_cloud_connections_summary": "settings",
}

lines_to_remove = set()

# Process tree for routes and helpers
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        is_route = False
        router_target = None
        
        # Check if it's a route
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", "") == "app":
                    method = dec.func.attr
                    if method in ["get", "post", "put", "delete", "patch"]:
                        if dec.args and isinstance(dec.args[0], ast.Constant):
                            path = dec.args[0].value
                            router_target = get_router_for_path(path)
                            if router_target:
                                is_route = True
                                break
        
        # Check if it's a helper
        if node.name in move_map:
            router_target = move_map[node.name]
            is_route = True # treating it as an extraction target

        if is_route and router_target:
            source_segment = ast.get_source_segment(source, node)
            # Replace @app. with @router. for routes
            source_segment = source_segment.replace("@app.get", "@router.get")
            source_segment = source_segment.replace("@app.post", "@router.post")
            source_segment = source_segment.replace("@app.delete", "@router.delete")
            source_segment = source_segment.replace("@app.put", "@router.put")
            source_segment = source_segment.replace("@app.patch", "@router.patch")
            
            routers_content[router_target] += source_segment + "\n\n"
            
            # Mark lines for removal
            start_line = getattr(node.decorator_list[0], 'lineno', node.lineno) if node.decorator_list else node.lineno
            end_line = node.end_lineno
            for i in range(start_line, end_line + 1):
                lines_to_remove.add(i)

# Reconstruct app_async.py
source_lines = source.splitlines()
new_lines = []
for i, line in enumerate(source_lines, 1):
    if i not in lines_to_remove:
        new_lines.append(line)

router_inclusions = """
# Injected router includes
from reaper.web.routers.settings import router as settings_router
from reaper.web.routers.vault import router as vault_router
from reaper.web.routers.financial import router as financial_router
from reaper.web.routers.finops import router as finops_router
from reaper.web.routers.resources import router as resources_router
from reaper.web.routers.cost_optimization import router as cost_optimization_router

app.include_router(settings_router)
app.include_router(vault_router)
app.include_router(financial_router)
app.include_router(finops_router)
app.include_router(resources_router)
app.include_router(cost_optimization_router)
"""

insert_idx = -1
for i, line in enumerate(new_lines):
    if "app.include_router(copilot_router)" in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    new_lines.insert(insert_idx, router_inclusions)
else:
    new_lines.append(router_inclusions)

with open(app_file, "w") as f:
    f.write("\n".join(new_lines) + "\n")

# Write out routers
os.makedirs("src/reaper/web/routers", exist_ok=True)
# To preserve imports, let's prepend imports from app_async.py to every router
imports = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        imports.append(ast.get_source_segment(source, node))
import_block = "\n".join(imports)

for r_name, r_content in routers_content.items():
    with open(f"src/reaper/web/routers/{r_name}.py", "w") as f:
        # Prepend global imports to the router, so `ruff check --fix` can clean them
        f.write(import_block + "\n\n" + r_content)

print(f"Extracted {len(lines_to_remove)} lines. Refactoring complete.")

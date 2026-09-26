import ast
import os

app_file = "src/reaper/web/app_async.py"

with open(app_file, "r") as f:
    source = f.read()

tree = ast.parse(source)

# We want to keep all imports and global variables, but move the route handlers.
# Actually, moving just the route handlers might leave them without needed imports,
# but we can copy ALL imports to the new routers, and let `ruff check --fix` clean up unused ones!

imports: list[str] = []
global_statements = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        seg = ast.get_source_segment(source, node)
        if seg:
            imports.append(seg)
    elif isinstance(node, ast.Assign) or isinstance(node, ast.AnnAssign):
        # some global vars might be needed, but copying them might cause duplicate state.
        pass

import_block = "\n".join(imports)
# Add FastAPI APIRouter
import_block = "from fastapi import APIRouter\n" + import_block

router_defs = {
    "settings": 'router = APIRouter(prefix="/api/settings", tags=["settings"])\n\n',
    "vault": 'router = APIRouter(tags=["vault"])\n\n',
    "financial": 'router = APIRouter(prefix="/api/financial", tags=["financial"])\n\n',
    "finops": 'router = APIRouter(prefix="/api/finops", tags=["finops"])\n\n',
    "resources": 'router = APIRouter(prefix="/api/resources", tags=["resources"])\n\n',
    "cost_optimization": 'router = APIRouter(tags=["cost_optimization"])\n\n',
}

routers_content: dict[str, str] = {k: import_block + "\n\n" + v for k, v in router_defs.items()}

# Helper to determine which router a path belongs to
def get_router_for_path(path: str) -> str | None:
    if path.startswith("/api/settings"): return "settings"
    if path.startswith("/api/vault") or path.startswith("/api/credentials"): return "vault"
    if path.startswith("/api/financial"): return "financial"
    if path.startswith("/api/finops"): return "finops"
    if path.startswith("/api/resources"): return "resources"
    if path.startswith("/api/cost-optimization") or path.startswith("/api/cost-reports"): return "cost_optimization"
    return None

new_app_body = []
nodes_to_remove = []
route_names_to_move = set()

# First pass: find route handlers
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        is_route = False
        router_target = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", "") == "app":
                    method = dec.func.attr # get, post, etc.
                    if method in ["get", "post", "put", "delete", "patch"]:
                        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                            path = dec.args[0].value
                            router_target = get_router_for_path(path)
                            if router_target:
                                is_route = True
                                break

        if is_route and router_target:
            # We found a route to move
            route_source = ast.get_source_segment(source, node)
            if route_source:
                # Replace @app. with @router.
                route_source = route_source.replace("@app.get", "@router.get")
                route_source = route_source.replace("@app.post", "@router.post")
                route_source = route_source.replace("@app.delete", "@router.delete")
                route_source = route_source.replace("@app.put", "@router.put")
                route_source = route_source.replace("@app.patch", "@router.patch")
                
                routers_content[router_target] += route_source + "\n\n"
                nodes_to_remove.append(node)
                route_names_to_move.add(node.name)

# Notice: some helper functions are placed right next to routes and might need to be moved too.
# e.g., handle_set_currency, _write_gcp_service_account_file, etc.
# But for now, we'll try moving just the routes. If they use local helpers, we'll see import/name errors.

# Write new router files
os.makedirs("src/reaper/web/routers", exist_ok=True)
for r_name, r_content in routers_content.items():
    # Remove prefix from APIRouter definition to avoid double prefix, 
    # since we kept full paths in decorators.
    r_content = r_content.replace(f'prefix="/api/{r_name}", ', '')
    
    with open(f"src/reaper/web/routers/{r_name}.py", "w") as f:
        f.write(r_content)

print(f"Moved {len(nodes_to_remove)} routes.")

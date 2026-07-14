import ast
import os
import shutil

app_file = "src/reaper/web/app_async.py"
backup_file = "src/reaper/web/app_async.py.bak"

if not os.path.exists(backup_file):
    shutil.copy(app_file, backup_file)

with open(app_file, "r") as f:
    source = f.read()

tree = ast.parse(source)

def get_router_for_path(path: str) -> str:
    if path.startswith("/api/settings"): return "settings"
    if path.startswith("/api/vault") or path.startswith("/api/credentials"): return "vault"
    if path.startswith("/api/financial"): return "financial"
    if path.startswith("/api/finops"): return "finops"
    if path.startswith("/api/resources"): return "resources"
    if path.startswith("/api/cost-optimization") or path.startswith("/api/cost-reports"): return "cost_optimization"
    return None

lines_to_remove = set()
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if getattr(dec.func.value, "id", "") == "app":
                    method = dec.func.attr
                    if method in ["get", "post", "put", "delete", "patch"]:
                        if dec.args and isinstance(dec.args[0], ast.Constant):
                            path = dec.args[0].value
                            if get_router_for_path(path):
                                # Mark the lines for this node to be removed
                                # Also include decorators which might be on earlier lines
                                start_line = node.decorator_list[0].lineno
                                end_line = node.end_lineno
                                for i in range(start_line, end_line + 1):
                                    lines_to_remove.add(i)

# Read lines and keep only those not in lines_to_remove
source_lines = source.splitlines()
new_lines = []
for i, line in enumerate(source_lines, 1):
    if i not in lines_to_remove:
        new_lines.append(line)

# Let's insert the router inclusions after the existing includes
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

# Find a good place to inject. Looking for 'app.include_router(copilot_router)'
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
    f.write("\\n".join(new_lines) + "\\n")

print(f"Removed {len(lines_to_remove)} lines from {app_file}.")

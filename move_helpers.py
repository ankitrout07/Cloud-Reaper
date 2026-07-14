import ast

app_file = "src/reaper/web/app_async.py"
with open(app_file, "r") as f:
    source = f.read()

tree = ast.parse(source)

# We want to find specific functions and move them to their respective routers
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
router_additions = {r: [] for r in set(move_map.values())}

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in move_map:
            target = move_map[node.name]
            # extract source
            func_source = ast.get_source_segment(source, node)
            router_additions[target].append(func_source)
            
            # mark lines for removal
            start_line = getattr(node.decorator_list[0], 'lineno', node.lineno) if node.decorator_list else node.lineno
            end_line = node.end_lineno
            for i in range(start_line, end_line + 1):
                lines_to_remove.add(i)

# Remove lines from app_async.py
source_lines = source.splitlines()
new_lines = [line for i, line in enumerate(source_lines, 1) if i not in lines_to_remove]
with open(app_file, "w") as f:
    f.write("\\n".join(new_lines) + "\\n")

# Append to routers
for r_name, funcs in router_additions.items():
    if funcs:
        with open(f"src/reaper/web/routers/{r_name}.py", "a") as f:
            f.write("\\n\\n" + "\\n\\n".join(funcs) + "\\n")

print(f"Moved {len(move_map)} helper functions.")

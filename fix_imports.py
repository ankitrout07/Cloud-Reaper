import os

router_files = {
    "settings.py": [
        "from reaper.web.app_async import PROVIDER_AUTH_STATE, _reaper_engine_binary, calc, settings_state",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ],
    "vault.py": [
        "from reaper.web.app_async import VAULT_UNLOCK_TTL_SEC",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ],
    "financial.py": [
        "from reaper.web.app_async import settings_state",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ],
    "finops.py": [
        "from reaper.web.app_async import settings_state, is_first_run, _get_cached_user_info",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ],
    "resources.py": [
        "from reaper.web.app_async import settings_state, is_first_run",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ],
    "cost_optimization.py": [
        "from reaper.web.app_async import settings_state, is_first_run",
        "from reaper.utils.error_handler import get_logger\\nlogger = get_logger(__name__)"
    ]
}

jsonify_code = """
def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)
"""

# Let's fix the undefined variables in the routers.
for r_name, imports in router_files.items():
    path = f"src/reaper/web/routers/{r_name}"
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
            
        new_content = "\\n".join(imports) + "\\n" + jsonify_code + "\\n" + content
        with open(path, "w") as f:
            f.write(new_content)

print("Injected missing imports and jsonify helper.")

app_file = "src/reaper/web/app_async.py"

with open(app_file) as f:
    content = f.read()

# Fix _get_cached_user_info
content = content.replace(
    "def _get_cached_user_info(request: Request) -> tuple[str, str]:",
    "async def _get_cached_user_info(request: Request) -> tuple[str, str]:",
)

content = content.replace(
    "user_name, sub_name = _get_cached_user_info(request)",
    "user_name, sub_name = await _get_cached_user_info(request)",
)

old_fetch_block = """    # Fetch fresh data and cache it
    try:
        az = AzureCollector()
        user_name = az.get_user_name()
        sub_name = az.get_subscription_name()"""

new_fetch_block = """    # Fetch fresh data and cache it
    try:
        def _fetch_user():
            c = AzureCollector()
            return c.get_user_name(), c.get_subscription_name()
        user_name, sub_name = await asyncio.to_thread(_fetch_user)"""

content = content.replace(old_fetch_block, new_fetch_block)

# Fix line 1363: collector = AzureCollector()
old_collector_block = """        collector = AzureCollector()

        # Get actual resource costs and inventory
        resource_summary = collector.get_resource_cost_summary()
        vms = collector.get_vm_inventory()
        idle_vms = collector.get_idle_vms()
        orphaned_disks = collector.get_orphaned_disks()"""

new_collector_block = """        # Get actual resource costs and inventory
        def _fetch_all():
            c = AzureCollector()
            return c.get_resource_cost_summary(), c.get_vm_inventory(), c.get_idle_vms(), c.get_orphaned_disks()
        
        resource_summary, vms, idle_vms, orphaned_disks = await asyncio.to_thread(_fetch_all)"""

content = content.replace(old_collector_block, new_collector_block)

with open(app_file, "w") as f:
    f.write(content)

print("Second wave of replacements applied.")

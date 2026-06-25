import re
import os

app_file = "src/reaper/web/app_async.py"

with open(app_file, "r") as f:
    content = f.read()

# 1. Replace subprocess.run inside check_auth
content = re.sub(
    r'subprocess\.run\(\["az", "account", "show"\], capture_output=True, check=True\)',
    r'await asyncio.to_thread(subprocess.run, ["az", "account", "show"], capture_output=True, check=True)',
    content
)

# 2. Replace subprocess.run inside list_subscriptions
content = re.sub(
    r'result = subprocess\.run\(\s*\[str\(binary_path\), "--list-subs"\],\s*capture_output=True,\s*text=True,\s*check=False,\s*\)',
    r'result = await asyncio.to_thread(subprocess.run, [str(binary_path), "--list-subs"], capture_output=True, text=True, check=False)',
    content
)

# 3. Replace time.sleep inside budget_killswitch
content = re.sub(
    r'time\.sleep\(0\.5\)',
    r'await asyncio.sleep(0.5)',
    content
)

# 4. Remove redundant 'import asyncio' in try blocks
content = re.sub(
    r'(\s+)import asyncio\s+await asyncio\.sleep',
    r'\1await asyncio.sleep',
    content
)

# 5. Fix AzureCollector().METHOD(...) -> await asyncio.to_thread(lambda: AzureCollector().METHOD(...))
def wrap_inline_collector(match):
    indent = match.group(1)
    return f'{indent}await asyncio.to_thread(lambda: AzureCollector().{match.group(2)})'

# This matches things like: data = AzureCollector().get_anomaly_data()
# We look for "AzureCollector().METHOD(...)" where it doesn't span multiple lines for arguments (most don't).
content = re.sub(
    r'^([ \t]+).*?AzureCollector\(\)\.([a-zA-Z0-9_]+\([^)]*\))',
    lambda m: m.group(0).replace(f"AzureCollector().{m.group(2)}", f"await asyncio.to_thread(lambda: AzureCollector().{m.group(2)})"),
    content,
    flags=re.MULTILINE
)

# For az = AzureCollector()
# followed by az.method(...)
# We can't easily regex this if it's multiple lines. Let's find them manually or write a smart replacer.
content = re.sub(
    r'([ \t]+)az = AzureCollector\(\)\s+cpu_usage = az\.get_live_subscription_cpu_average\(max_vms=6\)',
    r'\1cpu_usage = await asyncio.to_thread(lambda: AzureCollector().get_live_subscription_cpu_average(max_vms=6))',
    content
)

content = re.sub(
    r'([ \t]+)az = AzureCollector\(\)\s+prices = az\.fetch_regional_prices\(sku, region\)',
    r'\1prices = await asyncio.to_thread(lambda: AzureCollector().fetch_regional_prices(sku, region))',
    content
)

# Let's save and we'll manually fix the rest if any.
with open(app_file, "w") as f:
    f.write(content)

print("Automated replacements applied.")

import ast
import os
import sys

def check_file(filepath):
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return

    for node in ast.walk(tree):
        # Bare except Exception
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                pass # print(f"{filepath}:{node.lineno}: Bare except")
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception' and node.name is None:
                # print(f"{filepath}:{node.lineno}: Bare 'except Exception:' without 'as'")
                pass

        # Blocking calls in async
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute):
                        if child.func.attr == 'run' and isinstance(child.func.value, ast.Name) and child.func.value.id == 'subprocess':
                            print(f"{filepath}:{child.lineno}: Blocking subprocess.run in async function '{node.name}'")
                        if child.func.attr == 'sleep' and isinstance(child.func.value, ast.Name) and child.func.value.id == 'time':
                            print(f"{filepath}:{child.lineno}: Blocking time.sleep in async function '{node.name}'")

        # requests.get in async
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute) and child.func.attr in ('get', 'post', 'put', 'delete'):
                        if isinstance(child.func.value, ast.Name) and child.func.value.id == 'requests':
                            print(f"{filepath}:{child.lineno}: Blocking requests.{child.func.attr} in async function '{node.name}'")

        # Mutable default args
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, (ast.List, ast.Dict)):
                    print(f"{filepath}:{node.lineno}: Mutable default argument in function '{node.name}'")
                    
        # Check for un-awaited tasks?
        # Check for duplicate dictionary keys
        if isinstance(node, ast.Dict):
            keys = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    if k.value in keys:
                        print(f"{filepath}:{node.lineno}: Duplicate dictionary key '{k.value}'")
                    keys.add(k.value)

def main():
    for root, _, files in os.walk('src'):
        for file in files:
            if file.endswith('.py'):
                check_file(os.path.join(root, file))

if __name__ == '__main__':
    main()

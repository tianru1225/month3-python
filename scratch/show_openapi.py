import json
import sys

data = json.load(sys.stdin)

for path,methods in data["paths"].items():
    for method,spec in methods.items():
        print(method.upper(),path)
        print("tags",spec.get("tags"))
        print("summary",spec.get("summary"))
        print("responses",",".join(spec.get("responses",{})))

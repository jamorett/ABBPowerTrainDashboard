import os
with open(".env", "r") as f:
    text = f.read()

if "ABB_API_KEY=" not in text:
    with open(".env", "a") as f:
        f.write("\nABB_API_KEY=42914eb454a44b22b3d0d8b775d9fa5b55ca4098022b406ebf790036553b76fb\n")

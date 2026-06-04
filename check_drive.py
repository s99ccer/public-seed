import requests

url = "https://drive.usercontent.google.com/download?id=1O_24P2YVSFlDjM9cZGmUdBsWlI2eI6zv&export=download"
r = requests.get(url, allow_redirects=True)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")
print(f"Content-Length: {len(r.content)}")
print(f"First 50 bytes: {r.content[:50]}")
print(f"First 200 chars: {r.text[:200]}")

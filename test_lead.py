import urllib.request, json

data = json.dumps({
    "name": "Rashed",
    "phone": "01712345678",
    "message": "ami chakri korte chai",
    "intent": "job_inquiry",
    "source": "test"
}).encode()

req = urllib.request.Request(
    "http://localhost:8100/leads/capture",
    data=data,
    headers={"Content-Type": "application/json"},
)
resp = urllib.request.urlopen(req)
print(resp.read().decode())

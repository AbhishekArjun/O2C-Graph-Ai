import urllib.request
req = urllib.request.Request("http://127.0.0.1:5001/api/chat", data=b'{"message":"What is the total revenue?"}', headers={"Content-Type":"application/json"})
try:
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print("ERROR:")
    print(e.read().decode())

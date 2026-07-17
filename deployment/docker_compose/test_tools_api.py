import requests

s = requests.Session()
r1 = s.post('http://localhost:3000/api/auth/callback/credentials', json={'username':'admin_user@example.com','password':'TestPassword123!'})
r2 = s.get('http://localhost:3000/api/tool')
print(f'Status: {r2.status_code}')
print(r2.text)

import socket
import requests

API_KEY = 'your_api_key'
API_URL = 'https://geo.ipify.org/api/v1'

if __name__ == '__main__' :

	with open ('ip.txt') as ip_f, open ('output.txt', 'w') as out_f:
		
		for ip in ip_f:

			r = requests.get(
				url=API_URL,
				params={
					'apiKey': API_KEY,
					'ipAddress': ip
				},
			)
			
			print(r.json(), file=out_f)

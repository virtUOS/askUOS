import requests
import pickle
import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# taken from https://www.webscrapingapi.com/how-to-make-a-web-crawler-using-python


url = 'https://www.uni-osnabrueck.de/studieninteressierte/bewerbung/'

response = requests.get(url)
html = response.text

links = []

soup = BeautifulSoup(html, 'html.parser')

for link in soup.find_all('a'):

    path = link.get('href')

    if path and path.startswith('/'):
        path = urljoin(url, path)

    links.append(path)

# save list to pickle file

with open('data/links.pickle', 'wb') as f:
    pickle.dump(links, f)



# print(json.dumps(links, sort_keys=True, indent=2))

print()
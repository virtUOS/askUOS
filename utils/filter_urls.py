import pickle
from urllib.parse import urlparse

def filter_links(original_list, prefix):
    filtered_list = [link for link in original_list if urlparse(link).scheme == 'https' and (link.startswith(prefix) )]
    return filtered_list


# load links from pickle file
with open('../data/links.pickle', 'rb') as f:
    links = pickle.load(f)


filtered_links = filter_links(links, "https://www.uni-osnabrueck.de/studieninteressierte/bewerbung/")

# save filtered links to pickle file
with open('data/filtered_links_bewerbung.pickle', 'wb') as f:
    pickle.dump(filtered_links, f)
"""Get articles from the New York Times API.

Usage:
    get_goodnews.py [options]

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.

"""
import sys
sys.path.append("../")

import json
import os
import re

import ptvsd
import pymongo
import requests
from bs4 import BeautifulSoup
from docopt import docopt
from langdetect import detect
from pymongo import MongoClient
from schema import And, Or, Schema, Use
from tqdm import tqdm

from tell.utils import setup_logger
from scripts.get_articles_goodnews import strip_html, remove_between_square_brackets, denoise_text

logger = setup_logger()

def validate(args):
    """Validate command line arguments."""
    args = {k.lstrip('-').lower().replace('-', '_'): v
            for k, v in args.items()}
    schema = Schema({
        'ptvsd': Or(None, And(Use(int), lambda port: 1 <= port <= 65535)),
    })
    args = schema.validate(args)
    return args

def count(collection):
    cursor = collection.find({"facenet_details": { '$ne': None }})
    for sample in tqdm(cursor):
        pass

def main():
    args = docopt(__doc__, version='0.0.1')
    args = validate(args)

    if args['ptvsd']:
        address = ('0.0.0.0', args['ptvsd'])
        ptvsd.enable_attach(address)
        ptvsd.wait_for_attach()

    # root_dir = args['root_dir']
    # img_dir = os.path.join(root_dir, 'images')
    # os.makedirs(img_dir, exist_ok=True)

    client = MongoClient(host='localhost', port=27017)
    db = client.visualnews
    count(db.splits)

if __name__ == '__main__':
    main()

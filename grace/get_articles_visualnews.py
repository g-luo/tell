"""Get articles from the New York Times API.

Usage:
    get_goodnews.py [options]

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.
    -r --root-dir DIR   Root directory of data [default: data/goodnews].

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

def get_visualnews_articles(root_dir, db):
    """
        Generates a properly structured MongoDB database
        From the data.json and article metadata from Visual News.
        Assumes images are already downloaded.
    """

    data = json.load(open(f"{root_dir}/data.json"))
    split = 'train'

    logger.info('Inserting VisualNews articles.')
    for article in tqdm(data):
        # There is only one image per article in VisualNews
        id_ = article['id']
        result = db.articles.find_one({'_id': id_})
        if result is None:
            article['_id'] = id_

            caption = article["caption"].strip()
            article['images'] = {'0': denoise_text(caption)}

            # Add additional article context
            article_path = os.path.join(root_dir, 'origin', article['article_path'])
            article['article'] = open(article_path, 'r').read()
            context = article['article'].strip()
            # Assume language is English
            article['language'] = 'en'
            article['context'] = context

            # TODO: find url
            # article['web_url'] = article['article_url']
            # TODO: find the title
            # try:
            #     title = article['headline']['main'].strip()
            #     context = title + '\n\n' + context
            # except KeyError:
            #     pass

            db.articles.insert_one(article)

        result = db.splits.find_one({'_id': id_})
        if result is None:
            db.splits.insert_one({
                '_id': id_,
                'article_id': id_,
                'image_index': 0,
                'split': split,
            })

    db.splits.create_index([
        ('split', pymongo.ASCENDING),
        ('_id', pymongo.ASCENDING),
    ])


def validate(args):
    """Validate command line arguments."""
    args = {k.lstrip('-').lower().replace('-', '_'): v
            for k, v in args.items()}
    schema = Schema({
        'ptvsd': Or(None, And(Use(int), lambda port: 1 <= port <= 65535)),
        'root_dir': os.path.exists
    })
    args = schema.validate(args)
    return args


def main():
    args = docopt(__doc__, version='0.0.1')
    args = validate(args)

    if args['ptvsd']:
        address = ('0.0.0.0', args['ptvsd'])
        ptvsd.enable_attach(address)
        ptvsd.wait_for_attach()

    root_dir = args['root_dir']
    img_dir = os.path.join(root_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)

    client = MongoClient(host='localhost', port=27017)
    db = client.visualnews

    # root_dir should incude visual_news/origin
    get_visualnews_articles(root_dir, db)


if __name__ == '__main__':
    main()

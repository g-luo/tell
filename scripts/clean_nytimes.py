"""Get articles from the New York Times API.

Usage:
    clean_nytimes.py [options]

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.
    -h --host HOST      Mongo host name [default: localhost]

"""
import functools
import os
from datetime import datetime
from multiprocessing import Pool

import numpy as np
import ptvsd
import pymongo
import torch
from docopt import docopt
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import DocumentTooLarge
from schema import And, Or, Schema, Use
from tqdm import tqdm

from newser.facenet import MTCNN, InceptionResnetV1
from newser.utils import setup_logger

logger = setup_logger()


def validate(args):
    """Validate command line arguments."""
    args = {k.lstrip('-').lower().replace('-', '_'): v
            for k, v in args.items()}
    schema = Schema({
        'ptvsd': Or(None, And(Use(int), lambda port: 1 <= port <= 65535)),
        'host': str,
    })
    args = schema.validate(args)
    return args


def clean_with_host(host):
    client = MongoClient(host=host, port=27017)
    db = client.nytimes

    start = datetime(2019, 6, 1)
    end = datetime(2019, 9, 1)
    article_cursor = db.articles.find({
        'pub_date': {'$gte': start, '$lt': end},
    }, no_cursor_timeout=True).batch_size(128)
    for article in tqdm(article_cursor):
        article['split'] = 'test'
        db.articles.find_one_and_update(
            {'_id': article['_id']}, {'$set': article})

    db.articles.create_index([
        ('split', pymongo.ASCENDING),
        ('_id', pymongo.ASCENDING),
    ])

    start = datetime(2000, 1, 1)
    end = datetime(2019, 5, 1)
    article_cursor = db.articles.find({
        'pub_date': {'$gte': start, '$lt': end},
    }, no_cursor_timeout=True).batch_size(128)
    for article in tqdm(article_cursor):
        article['split'] = 'train'
        db.articles.find_one_and_update(
            {'_id': article['_id']}, {'$set': article})

    start = datetime(2019, 5, 1)
    end = datetime(2019, 6, 1)
    article_cursor = db.articles.find({
        'pub_date': {'$gte': start, '$lt': end},
    }, no_cursor_timeout=True).batch_size(128)
    for article in tqdm(article_cursor):
        article['split'] = 'valid'
        db.articles.find_one_and_update(
            {'_id': article['_id']}, {'$set': article})


def main():
    args = docopt(__doc__, version='0.0.1')
    args = validate(args)

    if args['ptvsd']:
        address = ('0.0.0.0', args['ptvsd'])
        ptvsd.enable_attach(address)
        ptvsd.wait_for_attach()

    clean_with_host(args['host'])


if __name__ == '__main__':
    main()

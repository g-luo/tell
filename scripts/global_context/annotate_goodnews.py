"""Annotate Good News with parts of speech.

Usage:
    annotate_goodnews.py [options]

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.
    -h --host HOST      MongoDB host [default: localhost].
    -c --context_key CONTEXTKEY  Context key

"""

import sys
sys.path.append("../../")

import ptvsd
import spacy
from docopt import docopt
from pymongo import MongoClient
from schema import And, Or, Schema, Use
from tqdm import tqdm

from tell.utils import setup_logger

logger = setup_logger()


def main():
    print("Running annotation")   
    context_key = sys.argv[1]
    # db_iteration = sys.argv[2]

    # if args['ptvsd']:
    #     address = ('0.0.0.0', args['ptvsd'])
    #     ptvsd.enable_attach(address)
    #     ptvsd.wait_for_attach()

    logger.info('Loading spacy.')
    nlp = spacy.load("en_core_web_lg")
    client = MongoClient(host='localhost', port=27017)
    db = client.goodnews

    # if db_iteration == "splits":
    #     sample_cursor = db.splits.find({}, no_cursor_timeout=True).batch_size(128)
    #     id_key = 'article_id'
    # else:
    # sample_cursor = db.articles.find({'context_abstract': { '$exists': False }}, no_cursor_timeout=True).batch_size(128)
    sample_cursor = db.articles.find({}, no_cursor_timeout=True).batch_size(128)
    id_key = '_id'

    done_article_ids = set()
    for sample in tqdm(sample_cursor):

        article = db.articles.find_one({
            '_id': {'$eq': sample[id_key]},
        })

        context = article['context'].strip()
        # Automatically truncate context for saving
        # context = ' '.join(article['context'].strip().split(' ')[:500])
        
        # Remove the headline
        if article.get("headline", {}).get("main", None):
            context = context.replace(article["headline"]["main"] + "\n\n", "")

        if context_key == "context_abstract":
            if article["abstract"] is None:
                article[context_key] = None
                article[f'{context_key}_ner'] = None
                continue
            else:
                context = article["abstract"] + "\n\n" + context

        article[context_key] = context
        context_doc = nlp(context)
        get_context_ner(context_doc, article, context_key)
        db.articles.find_one_and_update(
            {'_id': article['_id']}, {'$set': article})

def get_context_ner(doc, article, context_key):
    ner = []
    for ent in doc.ents:
        ent_info = {
            'start': ent.start_char,
            'end': ent.end_char,
            'text': ent.text,
            'label': ent.label_,
        }
        ner.append(ent_info)

    article[f'{context_key}_ner'] = ner

if __name__ == "__main__":
    main()
"""Get articles from the New York Times API.

Usage:
    compute_metrics.py [options] FILE

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.
    FILE                Path to the json file.
    -c --counters PATH  Path to the word counters.

"""
import json
import os
import pickle
import re
from datetime import datetime

import numpy as np
import ptvsd
import spacy
from docopt import docopt
from pycocoevalcap.bleu.bleu_scorer import BleuScorer
from pycocoevalcap.cider.cider_scorer import CiderScorer
from pycocoevalcap.meteor.meteor import Meteor
from pycocoevalcap.rouge.rouge import Rouge
from schema import And, Or, Schema, Use
from tqdm import tqdm

from newser.utils import setup_logger

logger = setup_logger()


def validate(args):
    """Validate command line arguments."""
    args = {k.lstrip('-').lower().replace('-', '_'): v
            for k, v in args.items()}
    schema = Schema({
        'ptvsd': Or(None, And(Use(int), lambda port: 1 <= port <= 65535)),
        'file': os.path.exists,
        'counters': Or(None, os.path.exists),
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

    with open(args['counters'], 'rb') as f:
        counters = pickle.load(f)

    full_counter = counters['context'] + counters['caption']

    bleu_scorer = BleuScorer(n=4)
    rouge_scorer = Rouge()
    rouge_scores = []
    cider_scorer = CiderScorer(n=4, sigma=6.0)
    meteor_scorer = Meteor()
    meteor_scores = []
    eval_line = 'EVAL'
    meteor_scorer.lock.acquire()
    count = 0
    recalls, precisions = [], []
    rare_recall, rare_recall_total = 0, 0
    rare_precision, rare_precision_total = 0, 0
    full_recall, full_recall_total = 0, 0
    full_precision, full_precision_total = 0, 0
    full_rare_recall, full_rare_recall_total = 0, 0
    full_rare_precision, full_rare_precision_total = 0, 0
    lengths, gt_lengths = [], []
    n_uniques, gt_n_uniques = [], []

    with open(args['file']) as f:
        for line in tqdm(f):
            obj = json.loads(line)
            caption = obj['raw_caption']
            generation = obj['generation']

            if obj['caption_names']:
                recalls.append(compute_recall(obj))
            if obj['generated_names']:
                precisions.append(compute_precision(obj))

            c, t = compute_full_recall(obj)
            full_recall += c
            full_recall_total += t

            c, t = compute_full_precision(obj)
            full_precision += c
            full_precision_total += t

            c, t = compute_rare_recall(obj, counters['caption'])
            rare_recall += c
            rare_recall_total += t

            c, t = compute_rare_precision(obj, counters['caption'])
            rare_precision += c
            rare_precision_total += t

            c, t = compute_rare_recall(obj, full_counter)
            full_rare_recall += c
            full_rare_recall_total += t

            c, t = compute_rare_precision(obj, full_counter)
            full_rare_precision += c
            full_rare_precision_total += t

            # Remove punctuation
            caption = re.sub(r'[^\w\s]', '', caption)
            generation = re.sub(r'[^\w\s]', '', generation)

            lengths.append(len(generation.split()))
            gt_lengths.append(len(caption.split()))

            n_uniques.append(len(set(generation.split())))
            gt_n_uniques.append(len(set(caption.split())))

            bleu_scorer += (generation, [caption])
            rouge_score = rouge_scorer.calc_score([generation], [caption])
            rouge_scores.append(rouge_score)
            cider_scorer += (generation, [caption])

            stat = meteor_scorer._stat(generation, [caption])
            eval_line += ' ||| {}'.format(stat)
            count += 1

    meteor_scorer.meteor_p.stdin.write('{}\n'.format(eval_line).encode())
    meteor_scorer.meteor_p.stdin.flush()
    for _ in range(count):
        meteor_scores.append(float(
            meteor_scorer.meteor_p.stdout.readline().strip()))
    meteor_score = float(meteor_scorer.meteor_p.stdout.readline().strip())
    meteor_scorer.lock.release()

    blue_score, _ = bleu_scorer.compute_score(option='closest')
    print(f'BLEU-1: {blue_score[0]}')
    print(f'BLEU-2: {blue_score[1]}')
    print(f'BLEU-3: {blue_score[2]}')
    print(f'BLEU-4: {blue_score[3]}')

    rouge_score = np.mean(np.array(rouge_scores))
    print(f'ROUGE: {rouge_score}')

    cider_score, _ = cider_scorer.compute_score()
    print(f'CIDEr: {cider_score}')

    print(f'METEOR: {meteor_score}')

    print(f'Recall: {sum(recalls) / len(recalls)}')
    print(f'Precision: {sum(precisions) / len(precisions)}')

    print(f'Full Recall: {full_recall} / {full_recall_total} = '
          f'{full_recall / full_recall_total}')
    print(f'Full Precision: {full_precision} / {full_precision_total} = '
          f'{full_precision / full_precision_total}')

    print(f'Rare Recall: {rare_recall} / {rare_recall_total} = '
          f'{rare_recall / rare_recall_total}')
    print(f'Rare Precision: {rare_precision} / {rare_precision_total} = '
          f'{rare_precision / rare_precision_total}')

    print(f'Full Rare Recall: {full_rare_recall} / {full_rare_recall_total} = '
          f'{full_rare_recall / full_rare_recall_total}')
    print(f'Full Rare Precision: {full_rare_precision} / {full_rare_precision_total} = '
          f'{full_rare_precision / full_rare_precision_total}')

    print(f'Length - generation: {sum(lengths) / len(lengths)}')
    print(f'Length - reference: {sum(gt_lengths) / len(gt_lengths)}')
    print(f'Unique words - generation: {sum(n_uniques) / len(n_uniques)}')
    print(
        f'Unique words  - reference: {sum(gt_n_uniques) / len(gt_n_uniques)}')


def compute_recall(obj):
    count = 0
    for name in obj['caption_names']:
        if name in obj['generated_names']:
            count += 1

    return count / len(obj['caption_names'])


def compute_precision(obj):
    count = 0
    for name in obj['generated_names']:
        if name in obj['caption_names']:
            count += 1

    return count / len(obj['generated_names'])


def compute_full_recall(obj):
    count = 0
    for name in obj['caption_names']:
        if name in obj['generated_names']:
            count += 1

    return count, len(obj['caption_names'])


def compute_full_precision(obj):
    count = 0
    for name in obj['generated_names']:
        if name in obj['caption_names']:
            count += 1

    return count, len(obj['generated_names'])


def compute_rare_recall(obj, counter):
    count = 0
    rare_names = [n for n in obj['caption_names'] if n not in counter]
    for name in rare_names:
        if name in obj['generated_names']:
            count += 1

    return count, len(rare_names)


def compute_rare_precision(obj, counter):
    count = 0
    rare_names = [n for n in obj['generated_names'] if n not in counter]
    for name in rare_names:
        if name in obj['caption_names']:
            count += 1

    return count, len(rare_names)


if __name__ == '__main__':
    main()
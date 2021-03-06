"""Get articles from the New York Times API.

Usage:
    detect_facenet_goodnews.py [options]

Options:
    -p --ptvsd PORT     Enable debug mode with ptvsd on PORT, e.g. 5678.
    -d --image-dir DIR  Image directory [default: ./data/visualnews/images].
    -f --face-dir DIR   Image directory [default: ./data/visualnews/facenet].
    -h --host HOST      Mongo host name [default: localhost]

"""
import sys
sys.path.append("../")

import os

import ptvsd
import torch
from docopt import docopt
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import DocumentTooLarge
from schema import And, Or, Schema, Use
from tqdm import tqdm

import torchvision.transforms.functional as F
import numpy as np

from tell.facenet import MTCNN, InceptionResnetV1
from tell.utils import setup_logger

logger = setup_logger()


def validate(args):
    """Validate command line arguments."""
    args = {k.lstrip('-').lower().replace('-', '_'): v
            for k, v in args.items()}
    schema = Schema({
        'ptvsd': Or(None, And(Use(int), lambda port: 1 <= port <= 65535)),
        'image_dir': str,
        'face_dir': str,
        'host': str,
    })
    args = schema.validate(args)
    return args


def detect_faces(sample, visualnews, image_dir, face_dir, mtcnn, resnet):
    if 'facenet_details' in sample:
        return

    image_path = os.path.join(image_dir, f"{sample['image_path']}")
    # try:
    #     image = Image.open(image_path)
    #     image = image.convert('RGB')
    # except (FileNotFoundError, OSError):
    #     logger.warning("File {} not found".format(image_path))
    #     return

    face_path = os.path.join(face_dir, f"{sample['image_path']}")
    with torch.no_grad():
        try:
            faces, probs = mtcnn(image, save_path=face_path,
                                 return_prob=True)
            faces = Image.open(face_path)
            # faces = F.to_tensor(np.float32(faces))
        except Exception as e:  # Strange index error on line 135 in utils/detect_face.py
            print(e)
            logger.warning(f"IndexError on image: {image_path} from sample "
                           f"{sample['_id']}")
            faces = None
        if faces is None:
            return
        embeddings, face_probs = resnet(faces)

    # We keep only top 10 faces
    sample['facenet_details'] = {
        'n_faces': len(faces[:10]),
        'embeddings': embeddings.cpu().tolist()[:10],
        'detect_probs': probs.tolist()[:10],
    }

    try:
        visualnews.splits.find_one_and_update(
            {'_id': sample['_id']}, {'$set': sample})
    except DocumentTooLarge:
        logger.warning(f"Document too large: {sample['_id']}")


def main():
    args = docopt(__doc__, version='0.0.1')
    args = validate(args)
    image_dir = args['image_dir']
    face_dir = args['face_dir']

    os.makedirs(face_dir, exist_ok=True)

    if args['ptvsd']:
        address = ('0.0.0.0', args['ptvsd'])
        ptvsd.enable_attach(address)
        ptvsd.wait_for_attach()

    client = MongoClient(host=args['host'], port=27017)
    visualnews = client.visualnews

    sample_cursor = visualnews.articles.find(
        {}, no_cursor_timeout=True).batch_size(128)

    logger.info('Loading model.')
    mtcnn = MTCNN(keep_all=True, device='cuda')
    resnet = InceptionResnetV1(pretrained='vggface2').eval()

    logger.info('Detecting faces.')
    for sample in tqdm(sample_cursor):
        detect_faces(sample, visualnews, image_dir, face_dir, mtcnn, resnet)


if __name__ == '__main__':
    main()

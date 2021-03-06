import logging
import os
import random
from typing import Dict

import numpy as np
import pymongo
from allennlp.data.dataset_readers.dataset_reader import DatasetReader
from allennlp.data.fields import ArrayField, MetadataField, TextField
from allennlp.data.instance import Instance
from allennlp.data.token_indexers import TokenIndexer
from allennlp.data.tokenizers import Tokenizer
from overrides import overrides
from PIL import Image
from pymongo import MongoClient
from torchvision.transforms import (CenterCrop, Compose, Normalize, Resize,
                                    ToTensor)
from tqdm import tqdm

from tell.data.fields import ImageField, ListTextField

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@DatasetReader.register('goodnews_face_ner_matched')
class GoodNewsFaceNERMatchedReader(DatasetReader):
    """Read from the Good News dataset.

    See the repo README for more instruction on how to download the dataset.

    Parameters
    ----------
    tokenizer : ``Tokenizer``
        We use this ``Tokenizer`` for both the premise and the hypothesis.
        See :class:`Tokenizer`.
    token_indexers : ``Dict[str, TokenIndexer]``
        We similarly use this for both the premise and the hypothesis.
        See :class:`TokenIndexer`.
    """

    def __init__(self,
                 tokenizer: Tokenizer,
                 token_indexers: Dict[str, TokenIndexer],
                 image_dir: str,
                 mongo_host: str = 'localhost',
                 mongo_port: int = 27017,
                 eval_limit: int = 5120,
                 use_caption_names: bool = True,
                 use_objects: bool = False,
                 n_faces: int = None,
                 lazy: bool = True, 
                 context_key: str = 'context',
                 with_abstract: bool = False,
                 with_ner: bool = False,
                 pog: bool = True,
                 max_end: int = 500) -> None:
        super().__init__(lazy)
        self._tokenizer = tokenizer
        self._token_indexers = token_indexers
        self.client = MongoClient(host=mongo_host, port=mongo_port)
        self.db = self.client.goodnews
        self.image_dir = image_dir
        self.preprocess = Compose([
            Resize(256), CenterCrop(224),
            ToTensor(),
            Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])])
        self.eval_limit = eval_limit
        self.use_caption_names = use_caption_names
        self.use_objects = use_objects
        self.n_faces = n_faces
        random.seed(1234)
        self.rs = np.random.RandomState(1234)

        self.context_key = context_key
        self.with_abstract = with_abstract
        self.with_ner = with_ner
        self.pog = pog
        self.max_end = 500

    @overrides
    def _read(self, split: str):
        # split can be either train, valid, or test
        if split not in ['train', 'val', 'test']:
            raise ValueError(f'Unknown split: {split}')

        # Setting the batch size is needed to avoid cursor timing out
        # We limit the validation set to 1000
        limit = self.eval_limit if split == 'val' else 0

        logger.info('Grabbing all article IDs')
        sample_cursor = self.db.splits.find({
            'split': {'$eq': split},
        }, projection=['_id'], limit=limit).sort('_id', pymongo.ASCENDING)

        ids = np.array([article['_id'] for article in tqdm(sample_cursor)])
        sample_cursor.close()
        self.rs.shuffle(ids)

        for sample_id in ids:
            sample = self.db.splits.find_one({'_id': {'$eq': sample_id}})
            projection = ['_id', self.context_key, 'images', 'web_url', 'caption_ner', f'{self.context_key}_ner']
            if self.with_abstract:
                projection.append('context_abstract')

            # Find the corresponding article
            article = self.db.articles.find_one({
                '_id': {'$eq': sample['article_id']},
            }, projection=projection)

            # Grace: If the key is None, continue even for no_headline case
            if self.with_abstract and article.get('context_abstract', None) is None:
                print("No abstract found")
                continue

            # Load the image
            image_path = os.path.join(self.image_dir, f"{sample['_id']}.jpg")
            try:
                image = Image.open(image_path)
            except (FileNotFoundError, OSError):
                print(f"Image not found {image_path}")
                continue

            # named_entities = sorted(self._get_named_entities(article))

            if self.n_faces is not None:
                n_persons = self.n_faces
            elif self.use_caption_names:
                n_persons = len(self._get_person_names(
                    article, sample['image_index']))
            else:
                n_persons = 4

            if 'facenet_details' not in sample or n_persons == 0:
                face_embeds = np.array([[]])
            else:
                face_embeds = sample['facenet_details']['embeddings']
                # Keep only the top faces (sorted by size)
                face_embeds = np.array(face_embeds[:n_persons])

            obj_feats = None
            if self.use_objects:
                obj = self.db.objects.find_one({'_id': sample['_id']})
                if obj is not None:
                    obj_feats = obj['object_features']
                    if len(obj_feats) == 0:
                        obj_feats = np.array([[]])
                    else:
                        obj_feats = np.array(obj_feats)
                else:
                    obj_feats = np.array([[]])

            yield self.article_to_instance(article, face_embeds,
                                           image, sample['image_index'],
                                           image_path, obj_feats)

    def article_to_instance(self, article, face_embeds, image,
                            image_index, image_path, obj_feats) -> Instance:
        
        named_entities = sorted(self._get_named_entities(article))
        if self.with_ner:
            ner = ", ".join(named_entities) + ".\n\n"
            context = ner + article[self.context_key].strip()
            context = ' '.join(context.split(' ')[:self.max_end])
        else:
            context = ' '.join(article[self.context_key].strip().split(' ')[:self.max_end])

        caption = article['images'][image_index]
        caption = caption.strip()

        context_tokens = self._tokenizer.tokenize(context)
        caption_tokens = self._tokenizer.tokenize(caption)
            
        name_token_list = [self._tokenizer.tokenize(n) for n in named_entities]
        if name_token_list:
            name_field = [TextField(tokens, self._token_indexers)
                          for tokens in name_token_list]
        else:
            stub_field = ListTextField(
                [TextField(caption_tokens, self._token_indexers)])
            name_field = stub_field.empty_field()

        fields = {
            'context': TextField(context_tokens, self._token_indexers),
            'names': ListTextField(name_field),
            'image': ImageField(image, self.preprocess),
            'caption': TextField(caption_tokens, self._token_indexers),
            'face_embeds': ArrayField(face_embeds, padding_value=np.nan),
        }

        if obj_feats is not None:
            fields['obj_embeds'] = ArrayField(obj_feats, padding_value=np.nan)

        metadata = {'context': context,
                    'caption': caption,
                    'names': named_entities,
                    'web_url': article['web_url'],
                    'image_path': image_path}
        fields['metadata'] = MetadataField(metadata)

        return Instance(fields)

    def _get_named_entities(self, article):
        # These name indices have the right end point excluded
        names = set()
        context_ner = f'{self.context_key}_ner'
        if context_ner in article:
            ners = article[context_ner]
            for ner in ners:
                if not self.pog or (ner['label'] in ['PERSON', 'ORG', 'GPE']):
                    # if not self.truncated or (ner['end'] < self.max_end):
                    names.add(ner['text'])
        return names

    def _get_person_names(self, article, pos):
        # These name indices have the right end point excluded
        names = set()

        if 'caption_ner' in article:
            ners = article['caption_ner'][pos]
            for ner in ners:
                if ner['label'] in ['PERSON']:
                    names.add(ner['text'])

        return names

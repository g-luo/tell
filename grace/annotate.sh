python3 -u get_articles_visualnews.py  -r /shared/g-luo/datasets/news/visual_news
python3 -u annotate_visualnews.py
python3 -u detect_facenet_visualnews.py -d /shared/g-luo/datasets/news/visual_news/origin -f /shared/g-luo/datasets/news/visual_news/visual_news_metadata/facenet_features
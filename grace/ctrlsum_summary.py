from transformers import AutoModelForSeq2SeqLM, PreTrainedTokenizerFast
import json
from tqdm import tqdm
import numpy as np

device = "cuda"

def summarize(entities, article):
    data = tokenizer(f"{entities} => {article}", return_tensors="pt")
    input_ids, attention_mask = data["input_ids"], data["attention_mask"]
    if max_input_length > input_ids.shape[1]:
        print("Input is size", input_ids.shape[1], "which is greater than max length", max_input_length)
    input_ids, attention_mask = input_ids[:, :max_input_length], attention_mask[:, :max_input_length]
    input_ids, attention_mask = input_ids.to(device), attention_mask.to(device)
    return tokenizer.batch_decode(model.generate(input_ids, attention_mask=attention_mask, num_beams=num_beams, max_length=max_generation_length))[0]

model = AutoModelForSeq2SeqLM.from_pretrained("hyunwoongko/ctrlsum-cnndm")
tokenizer = PreTrainedTokenizerFast.from_pretrained("hyunwoongko/ctrlsum-cnndm")
model = model.to(device)

num_beams = 5
max_input_length = 1024
max_generation_length = 256

nytimes = json.load(open("/shared/g-luo/datasets/transform-and-tell/nytimes/cleaned/train.json"))
articles = {a["_id"]: a for a in nytimes["articles"]}

coverages = []
summaries = []
for caption in tqdm(nytimes["captions"]):
    article = articles[caption["_id"]]["text"]
    # named_entities = ", ".join([n["text"] for n in caption["named_entities"]])
    # summary = summarize(named_entities, article)
    summary = summarize(caption["text"], article)
    summaries.append(summary)

json.dump(summaries, open("/shared/g-luo/datasets/transform-and-tell/nytimes/cleaned/caption_summaries.json", "w"))
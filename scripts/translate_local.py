"""Bounded JSON batch worker. Does not call any network service."""
import json
from pathlib import Path
import re
import sys
import ctranslate2
import langid
import sentencepiece

MODELS=Path(__file__).resolve().parent.parent/'data/translation-models'
ENGINES={}
CLASSIFIER=langid.langid.LanguageIdentifier.from_modelstring(langid.langid.model,norm_probs=True)
CLASSIFIER.set_languages(['en','fr','de','es','pt','it','nl','ja','ko','ru','zh'])


class BPETokenizer:
    def __init__(self,path,source,target):
        from sacremoses import MosesTokenizer, MosesDetokenizer, MosesPunctNormalizer
        from subword_nmt.apply_bpe import BPE
        self.tokenizer=MosesTokenizer(source)
        self.detokenizer=MosesDetokenizer(target)
        self.normalizer=MosesPunctNormalizer(source)
        with path.open(encoding='utf-8') as codes:self.bpe=BPE(codes)

    def encode(self,text,out_type=str):
        tokens=self.tokenizer.tokenize(self.normalizer.normalize(text))
        return self.bpe.process_line(' '.join(tokens)).split()

    def decode(self,tokens):
        return self.detokenizer.detokenize(' '.join(tokens).replace('@@ ','').split())


def engine(source,target):
    pair=f'{source}_{target}'
    if pair not in ENGINES:
        folder=MODELS/pair
        metadata=json.loads((folder/'metadata.json').read_text())
        tokenizer=(sentencepiece.SentencePieceProcessor(model_file=str(folder/'sentencepiece.model'))
                   if (folder/'sentencepiece.model').exists() else BPETokenizer(folder/'bpe.model',source,target))
        translator=ctranslate2.Translator(str(folder/'model'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=2)
        ENGINES[pair]=(tokenizer,translator,metadata.get('target_prefix',''))
    return ENGINES[pair]


def apply(text,source,target):
    tokenizer,translator,prefix=engine(source,target)
    # Preserve paragraphs and translate complete bounded sentence pieces without dropping a long tail.
    paragraphs=[]
    for paragraph in text.split('\n'):
        if not paragraph.strip():paragraphs.append('');continue
        chunks=re.findall(r'.{1,300}(?:\s+|$)|\S{1,300}',paragraph)
        tokens=[tokenizer.encode(chunk,out_type=str) for chunk in chunks]
        results=translator.translate_batch(tokens,beam_size=4,max_input_length=0,max_decoding_length=600,
                                           replace_unknowns=True,target_prefix=[[prefix]]*len(tokens) if prefix else None)
        output=' '.join(tokenizer.decode(r.hypotheses[0]) for r in results)
        if prefix and output.startswith(prefix):output=output[len(prefix):]
        paragraphs.append(output.replace('▁',' ').strip())
    return '\n'.join(paragraphs)


def translate(text):
    # Public handles, links and hashtags are source identifiers, not prose.
    parts=re.split(r'(https?://\S+|#[\w]+|@[\w.]+|[\U0001F000-\U0001FAFF\u2600-\u27BF][\uFE0F\u200D\U0001F000-\U0001FAFF]*)',text)
    prose=' '.join(parts[::2])
    language,confidence=CLASSIFIER.classify(prose)
    if confidence<0.8:language='en'
    if language!='en' and not (MODELS/f'{language}_en').exists():return None
    for i in range(0,len(parts),2):
        part=parts[i]
        if not re.search(r'[A-Za-z]{2}',part):continue
        if language!='en':part=apply(part,language,'en')
        parts[i]=apply(part,'en','zh')
    return ' '.join(part for part in parts if part)


if __name__=='__main__':
    texts=json.load(sys.stdin)
    results=[]
    for text in texts:
        try:results.append(translate(text))
        except Exception:results.append(None)
    print(json.dumps(results,ensure_ascii=False))

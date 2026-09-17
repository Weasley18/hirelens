# Training (Phases 4 and 5)

The GPU lives in Colab, the code lives here. Keep it that way — a notebook that only exists
in Google Drive is not reviewable and not part of the project.

## Order of operations

The build guide puts fine-tuning (Phase 4) before RAG (Phase 6). Do it the other way round:
`prepare_dataset.py` attaches retrieved context to each training example so the training
prompt matches the request-time prompt exactly. Ingest the knowledge base first.

```
rag/ingest.py  ->  data_gen/*  ->  training/prepare_dataset.py  ->  train.py
```

If you want to train before the knowledge base exists, run
`python -m training.prepare_dataset --context none` and accept the format mismatch.

## In Colab

`Runtime > Change runtime type > T4 GPU`, then:

```python
!pip install -q unsloth trl datasets jsonschema
!git clone https://github.com/<you>/hirelens.git
%cd hirelens/apps/ml-service

# upload data/dataset_clean.jsonl, or pull it from your Drive
!python -m training.prepare_dataset --heldout 20 --context none
!python -m training.train
!python -m training.evaluate
```

A T4 fine-tunes 3B at rank 16 on ~300 examples in roughly 20-40 minutes for 3 epochs.
Colab disconnects idle sessions, so keep the tab open.

## What to check before moving on

`evaluate.py` prints four numbers. The one that decides the phase is `matches schema`:
above 95% means the format is learned. Below that, adding epochs mostly adds overfitting —
go back to `dataset_clean.jsonl` and look at what the teacher actually produced.

Also read five generated outputs yourself. Valid JSON that says nothing useful still passes
every automated check here.

## Then quantize

```python
!python -m training.merge_and_export     # LoRA -> standalone weights
!bash scripts/quantize.sh hirelens-merged
```

Download `hirelens-q4.gguf` before the session ends, or push it to a Hugging Face model
repo from inside Colab — a disconnected runtime takes the file with it.

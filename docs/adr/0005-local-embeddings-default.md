# ADR-0005: Local ONNX embeddings by default

Status: Accepted (2026-08-22)

## Context
Semantic matching needs embeddings. A hosted embedding API means every resume section leaves the
server, which conflicts with the privacy posture and adds per-request cost and latency. Local
sentence-transformers would pull in torch (large install).

## Decision
Default to fastembed (Apache-2.0) running bge-small-en-v1.5 on onnxruntime, in-process on CPU. Keep
an EmbeddingProvider interface with a remote adapter available via EMBEDDING_BACKEND.

## Consequences
Resume text never leaves the server for semantic matching, embeddings cost nothing per call, and the
system works fully offline. Model weights (about 130 MB) are downloaded once at build/startup and
cached at the image level, never per session. If the runtime fails to load, semantic components
report unavailable and the scoring engine renormalises weights with a visible notice.

# Inference servers

Primer ships no model and runs no inference. These are the two servers the
reference configuration
(`deploy/helm/primer/values-selfhosted.yaml`) expects, as manifests you can
apply and edit.

Both are CPU-only. That is a constraint worth stating rather than a
recommendation: they are shaped for a deployment whose GPUs are committed to
chat models. With a GPU free, most of the tuning here becomes irrelevant and
you should reach for larger models.

| File | Serves | Model |
| --- | --- | --- |
| `embeddings.yaml` | `/v1/embeddings` | `onnx-community/Qwen3-Embedding-0.6B-ONNX` |
| `reranker.yaml` | `/rerank` | `BAAI/bge-reranker-base` |

The flags in both are load-bearing and the reasoning is in the comments.
[docs/operations/models.md](../../docs/operations/models.md) covers the
measurements behind them and how to pick different models.

Neither manifest carries a `namespace`, so apply them into whichever one
Primer runs in:

```bash
kubectl -n primer apply -f embeddings.yaml -f reranker.yaml
```

The service names match the URLs in `values-selfhosted.yaml`. If you rename
them, update `inference.embeddings.baseUrl` and `inference.rerank.baseUrl`
to match.

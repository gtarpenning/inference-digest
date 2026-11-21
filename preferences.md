# What counts as noteworthy

The reader is a backend engineer who builds ML infrastructure. They want to keep up with inference engineering:
how models are served fast and cheaply. Their interest is overwhelmingly on the software side. Most days that
is zero to three things.

## Include

- **Serving systems.** Design posts and major releases of vLLM, SGLang, TensorRT-LLM, Dynamo, llm-d, LMCache,
  llama.cpp and similar engines, when they change what is possible or how fast. A release is worth an item
  only for its headline features, not its changelog.
- **Optimization techniques with results.** Speculative decoding (EAGLE, MTP, draft models), attention kernels
  (FlashAttention, FlashInfer, FlashMLA), KV-cache management (paging, prefix caching, offload and tiering,
  compression), prefill/decode disaggregation, quantization (FP8, FP4, low-bit), MoE and expert parallelism,
  batching and scheduling, compilers and megakernels, long-context and sparse attention.
- **Papers.** New arXiv papers and top-venue papers (MLSys, OSDI, SOSP, NSDI, ISCA, ASPLOS, EuroSys, NeurIPS,
  ICML, ICLR) with a measured gain in throughput, latency, memory or cost.
- **Engineering blogs from inference companies** (Baseten, Fireworks, Together, Modal and the like) when they
  explain how something works and give numbers. A "model X is now live on our platform" post is not enough.
- **Frontier labs writing about inference.** Anthropic, OpenAI, Google DeepMind, Meta and others are mostly
  out of scope, but any post on how they serve models, cut latency or cost, or design for inference is in.
- **Open-weight models that matter for serving.** A popular open model's release (DeepSeek, Qwen, Kimi, GLM,
  MiniMax, Llama and the like) when its architecture or serving story is news: a new attention variant, MTP
  heads, an unusual MoE layout, day-0 support with throughput numbers.
- **Economics, rarely.** Only something very compelling: a real step change in $/M-token for a major model, a
  credible public analysis of serving costs, or a new provider that is clearly different.
- **Hardware, rarely.** Only a major release or result that changes inference software (a new accelerator
  generation with published inference numbers, a new number format).

## Leave out

- Product launches, pricing pages and "now available on" posts with no technical content.
- Provider marketing with no numbers, and "best inference API" listicles.
- Funding rounds, partnerships and business news.
- Training-only work (pretraining, RL, fine-tuning) unless it bears directly on inference.
- Routine point releases and changelogs.
- Agent frameworks, prompting and app-level tooling.
- Weekly roundups that only repeat items already seen.
- Anything already in a digest from the past week, unless there is a material new development.

## Weighing

- Primary sources over coverage of them. Link the paper, the engine's own post or the release, not the article
  about it.
- A result with numbers beats a claim without them. Say what hardware and model the numbers are for.
- Software over hardware, technique over product.
- For arXiv, most of what the filter lets through is incremental. Pick a paper only if it has a clear idea and
  a large measured gain, or comes from a group whose work tends to ship (the vLLM, SGLang, FlashAttention and
  similar teams, or the big labs).
- Popularity is weak evidence. A 500-point Hacker News thread can be about consumer hardware.
- Fresh means the article itself is new. Something first published more than a week ago is not today's news:
  leave it out, unless it is important, no digest has carried it, and nothing newer says the same thing.
- A new post about an older paper or release is fine. Its summary gives the older item's date.
- When in doubt, leave it out. An empty day is a correct answer.

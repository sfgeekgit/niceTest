# System prompt sources

Research done 2026-10-03 on what system prompts are available for making API calls resemble each vendor's consumer chat product. Findings were gathered by a research pass over the sources below; items marked "not opened" were not read. Extracted prompts are unofficial and unverified unless stated.

## Layout

```
prompts/
  conditions.json          the experiment's user messages
  system/                  official prompts, ready to send (date placeholder intact)
  unofficial/              extracted prompts, one file each, as downloaded
    manifest.json          repo, commit hash, path, size for every file
    asgeirtj__system_prompts_leaks/<Vendor>/<file>
    elder-plinius__CL4R1T4S/...
    jujumilk3__leaked-system-prompts/...
    xai-org__grok-prompts/...        (official xAI repo, kept here with the other downloads)
```

Only `unofficial/manifest.json` is kept in the repository; the extracted prompt files themselves are not redistributed here. Run `python3 prompts/fetch_unofficial.py` to download them at the pinned commits. They are raw downloads. None has been cleaned for use: they contain the capturer's location, dates, memory blocks and tool sections.

## Who publishes

Only Anthropic (current) and xAI (stale, stops at Grok 4.1, last commit 2025-11-17) publish consumer system prompts. OpenAI, Google, Meta, DeepSeek, Z.ai and Alibaba publish nothing; the Future of Life Institute's indicator (Nov 2025) says the same: https://futureoflife.org/wp-content/uploads/2025/11/Indicator-System_Prompt_Transparency.pdf

## Collections

| Repo | Last push | Use |
|---|---|---|
| https://github.com/asgeirtj/system_prompts_leaks | 2026-10-03 | Best. Current ChatGPT, Gemini, Grok, DeepSeek, Qwen, Kimi, Meta, Mistral, claude.ai with tools. |
| https://github.com/elder-plinius/CL4R1T4S | 2026-09-22 | Current for Claude only; stale elsewhere. |
| https://github.com/jujumilk3/leaked-system-prompts | 2026-09-23 | Mostly coding agents in 2026. Has Microsoft Copilot (2026-03-28). |
| https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools | 2026-08-11 | Coding tools only. Not useful here. |
| https://github.com/xai-org/grok-prompts | 2025-11-17 | Official, Grok 4.1 and earlier. |

## Per product

Local paths are relative to `prompts/unofficial/asgeirtj__system_prompts_leaks/` unless another directory is named.

| Product | Local file | Version / date | Size | Tool definitions | Confidence |
|---|---|---|---|---|---|
| ChatGPT, GPT-5.6 Sol | `OpenAI/gpt-5.6-sol.md` | 2026-08-22, "Sol, extra high" | 127 KB | python, genui, web, automations | Medium; single extractor |
| ChatGPT, GPT-5.5 Thinking | `OpenAI/gpt-5.5-thinking.md` | 2026-05-23 | 116 KB | Yes | Medium |
| ChatGPT, GPT-5.5 Instant | `OpenAI/gpt-5.5-instant.md` | 2026-07-21 | 85 KB | web, python, file_search; memory and ads sections | Medium; logged-in capture |
| OpenAI API hidden prompt | `OpenAI/gpt-5.5-api.md` | 2026-04-29 | 0.9 KB | n/a | Medium-high |
| Gemini app, 3.8 Flash | `Google/gemini-3.8-flash.md` | committed 2026-09-13, Paid tier | 58 KB | search, image, file_gen, canvas | Medium |
| Gemini app, 3.7 Flash | `Google/gemini-3.7-flash.md` | 2026-08-18 | 33 KB | not checked | Medium |
| Gemini app, 3.1 Pro | `Google/gemini-3.1-pro.md` | 2026-05-18 | 26 KB | partial | Medium; five months old |
| Grok 4.7, grok.com | `xAI/grok-4.7.md` | committed 2026-10-03 | 45 KB | about 30 tools | Medium |
| Grok 4.6 | `xAI/grok-4.6.md` | not opened | 36 KB | not checked | Unverified |
| Grok 4.1, official | `xai-org__grok-prompts/*.j2` | 2025-11-17 | 7 KB each | Jinja templates | High for 4.1 only |
| DeepSeek chat | `DeepSeek/deepseek-chat.md` | 2026-07-14 | 0.4 KB | search tool only | Medium; no persona prompt, just date, location, search |
| Qwen 3.8 Max | `Qwen/qwen3.8-max.md` | 2026-08-05 | 2.4 KB | code interpreter, web search | Medium; almost nothing beyond tools and date |
| Kimi K3 | `Kimi/kimi-3.md` | committed 2026-07-17 | 36 KB | Yes | Medium; may be agent mode, not plain chat |
| GLM, chat.z.ai | `GLM/README.md` | committed 2026-07-14 | one sentence | n/a | Low-medium; claims no system prompt, no evidence shown |
| Mistral Le Chat | `Mistral/mistral-medium-3.5.md` | 2026-07-07 | 22 KB | web, image, code, canvas | Medium |
| Meta AI | `Meta/muse-spark-1.1.md` | committed 2026-07-12 | 72 KB | not checked | Medium; likely outdated (OpenRouter lists Muse Spark 1.3) |
| Microsoft Copilot | `jujumilk3__leaked-system-prompts/microsoft-copilot_20260328.md` | 2026-03-28 | 51 KB | not checked | Medium; six months old |

## claude.ai with tool sections

Anthropic's official page omits the tool sections (web search, artifacts, citations, memory). Extracted full prompts:

| Model | Local file | Date | Size | Notes |
|---|---|---|---|---|
| Opus 4.6, full | `Anthropic/claude-opus-4.6.md` | committed 2026-07-17 | 180 KB | web_search, web_fetch, artifacts, citations, memory, about 20 tool definitions |
| Opus 4.6, tools disabled | `Anthropic/claude-opus-4.6-no-tools.md` | — | 50 KB | Behaviour prompt only |
| Opus 4.6, raw | `Anthropic/raw/claude-opus-4.6-raw.md` | — | 232 KB | Not opened |
| Opus 4.6, launch-day | `elder-plinius__CL4R1T4S/ANTHROPIC/Claude_Opus_4.6.txt` | 2026-02-06 | 103 KB | Earlier, shorter capture |
| Opus 5.5 | `Anthropic/claude-opus-5.5.md` | 2026-09-22 | 478 KB | Search, artifacts, citations |
| Sonnet 5.5 | `Anthropic/claude-sonnet-5.5.md` | 2026-09-30 | 481 KB | Not opened |
| Fable 5.1 | `Anthropic/claude-fable-5.1.md` | — | 476 KB | Not opened |

Checks against the official Opus 4.6 text (`prompts/system/claude-opus-4-6.txt`), by overlap of 8-word sequences:

- 98% of the official text appears in the extracted tools-disabled file. This is the only place an extraction can be checked against vendor ground truth, and it passes.
- Only 26% of the official text appears verbatim in the extracted full file (July). The behaviour text served alongside tools appears to have drifted from the February official text.
- The February and July full captures share about 36% with each other.
- The jujumilk3 Opus 4.6 file is a copy of the CL4R1T4S one, not an independent source.

## Official statements on chat product versus API

- **OpenAI.** The Model Spec (https://model-spec.openai.com/2026-08-18.html) says developers may not know the system message exists; the ChatGPT prompt is not published. `chat-latest` is documented as the Instant model used in ChatGPT (https://developers.openai.com/docs/models/chat-latest); OpenRouter lists `openai/gpt-chat-latest`. API calls reportedly get a hidden system message saying the model is accessed via an API (https://simonwillison.net/2025/Aug/15/gpt-5-has-a-hidden-system-prompt/), unconfirmed by OpenAI.
- **Google.** Nothing official found on the Gemini app prompt or app-versus-API differences.
- **xAI.** The official repo also lists injected API prefix prompts for some Grok API models.
- **DeepSeek.** Docs use "You are a helpful assistant." only as an example. Default temperature 1.0; 1.3 recommended for general conversation (https://api-docs.deepseek.com/quick_start/parameter_settings). Nothing official on the web app's settings.

## Prior work

- Wang, Baumann, Ho, Koyejo, "API Benchmark Scores Do Not Reliably Transfer to Chatbot Interfaces", Sept 2026, https://arxiv.org/abs/2609.08861. Compared API and chat interface for ChatGPT, Claude and Gemini. Approximated system prompts with publicly circulated ones. Adding them barely moved the accuracy gap (6.5 to 6.4 points); they attribute the rest to routing, retrieval, tool policies, personalisation and post-processing. Details here come from a summary of the paper, not a line-by-line read.
- Kirgis et al., "LLM Spirals of Delusion", Feb 2026, https://arxiv.org/abs/2604.06188. API arm via OpenRouter with ChatGPT-labelled models; chat arm by hand in ChatGPT temporary chats. Found large API-versus-chat differences.

## Caveats

1. Extractions are model self-reports and may contain paraphrase or invention. Outside Claude nothing can be verified, and two repos agreeing often means one copied the other.
2. Prompts are specific to a tier, mode and date, and change often.
3. Tool sections describe tools that cannot be supplied through OpenRouter; including them may cause attempted tool calls or claims of browsing, and removing them departs from the product.
4. Captures embed the capturer's location, dates, memory placeholders and ads sections, which need templating or removal.
5. The vendor's own hidden API layer (OpenAI, xAI) cannot be removed; our system prompt sits beneath it.
6. The system prompt is not the whole gap, per Wang et al. The API model snapshot may also differ from what the chat product serves.
7. Gemini Pro coverage is thin: one extraction from May, and OpenRouter lists only a 3.1 Pro preview.

## Recommendations (not yet decided)

- Claude: official prompt as the base; the extracted full files if tool sections are wanted.
- ChatGPT: the extracted GPT-5.5 and GPT-5.6 prompts; consider `openai/gpt-chat-latest` for the Instant condition.
- Gemini: extracted 3.8 Flash prompt with `google/gemini-3.8-flash`; the 3.1 Pro one for Pro.
- Grok: extracted Grok 4.7 prompt; the official repo only as a structural check.
- DeepSeek, Qwen, GLM: no system prompt or a date line only; DeepSeek at temperature 1.3. Do not invent "You are a helpful assistant".
- Kimi, Mistral, Meta: usable at lower confidence; check the model version matches.
- In any write-up: cite the commit hashes in `unofficial/manifest.json` and describe these as publicly circulated approximations.

## Open questions

- The extracted full claude.ai Opus 4.6 prompt is about eight times the size of the official text we sent and overlaps it only partly. A five-conversation side arm using it would test whether the missing sections explain why the pilot did not reproduce the blog's result.
- OpenAI's hidden API message means "no system prompt" is not a neutral baseline for GPT models.
- `openai/gpt-chat-latest` exists and is the closest official match to ChatGPT.
- The Wang et al. paper is the nearest prior work and worth reading in full before the write-up.

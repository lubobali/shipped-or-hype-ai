# shipped-or-hype-ai

A weekly AI news email where **every line has a source** and **the AI can't make up links**.

Every Sunday it reads 12 feeds (release notes, builders, papers, podcasts), and on Monday
morning you get one plain-text email:

1. **Shipped this week:** what really came out, with the link to the primary source
2. **Build ideas:** 3 small projects (2 days or less) that use something new, fitted to *your* stack
3. **Podcast claims, checked:** big claims from podcasts, with the exact quote, held up against
   the week's real sources
4. **Model moves:** price, quality or deprecation news that changes which model you should use

I built it because I listen to AI podcasts every week and wanted to know which claims were real.
LLM summaries are also known to invent links and quotes, so I didn't want to trust one blindly.

## How it stays honest

The model never writes a link or a quote. Python does.

- **Links:** the model sees the week's items **numbered, with no URLs**, and answers with item
  numbers only (strict JSON schema). Python attaches each link from the item it fetched. An
  unknown number is dropped, and any URL the model writes anyway is stripped. No link, no line.
- **Quotes:** for a podcast, the model pulls up to 5 claims from the transcript, each with the
  exact words. A claim is **thrown away unless its quote is really in the transcript** (case,
  spacing and curly quotes ignored).
- **Labels:** a claim is `BACKED BY A SOURCE` only if a non-podcast item confirms its specifics
  (names, numbers, dates). Otherwise it's `PARTLY BACKED`, `SOURCES SAY OTHERWISE` or
  `UNVERIFIED`. A podcast can never back a podcast.
- **Failure:** if the model fails or the key hits its credit limit, you still get the email, with
  **links only** and the reason at the top. A silent miss is the worst case.
- **Untrusted input:** feed text is data, never instructions. The model has no tools. XML goes
  through `defusedxml`, fetches are HTTPS-only with a 5 MB cap and 20 s timeout, and the email is
  plain text, so nothing from a feed can render as HTML.

## A real example (week 44, 2026: one section, word for word from a real run)

```
3. PODCAST CLAIMS, CHECKED
[UNVERIFIED]
  "OpenAI reported that its coding agents disabled safety monitors in two internal incidents and lied about it, with no satisfying explanation." (Moonshots (Diamandis))
  Quote: "This month, in two internal incidents, its coding agents switched off its monitors. I'll say it again, it switched off its monitors."
  What the evidence says: No item reports these incidents. OpenAI's post on securing its training environment covers stronger containment, but says nothing about agents switching off monitors.
  Evidence: https://openai.com/index/securing-our-frontier-model-training-environment
  Episode: https://traffic.megaphone.fm/DVVTS2164439111.mp3

[UNVERIFIED]
  "Chamath predicts a massive compute shortage over the next three to four years because of power and build-out constraints." (Moonshots (Diamandis))
  Quote: "We are probably gonna see a massive, massive, massive compute shortage in the next three or four years."
  What the evidence says: No item shows a shortage. NVIDIA's GPU-sharing post only notes that giving small workloads a whole GPU leaves capacity idle.
  Evidence: https://developer.nvidia.com/blog/memory-enforced-gpu-sharing-in-kubernetes-with-nvidia-cuda-13-4/
  Episode: https://traffic.megaphone.fm/DVVTS7398139491.mp3
```

## Sources

`radar/sources.yaml`, each with a trust level the email respects:

| Trust | Sources |
|---|---|
| primary (what shipped) | Claude Platform release notes, Claude Code releases, OpenAI news, NVIDIA developer blog |
| builder (hands-on) | Simon Willison, Latent Space, Hacker News (300+ points, AI titles) |
| research | Hugging Face daily papers (50+ upvotes), Interconnects, Import AI |
| opinion (checked, never trusted alone) | Moonshots, Dwarkesh Podcast |

Edit the file to use your own. A broken feed is listed at the bottom of the email and never stops
the others. Items already sent are remembered for 60 days, so nothing repeats.

## Run it

Python 3.12+.

```bash
pip install -r requirements.txt
cp .env.example my.env && chmod 600 my.env    # fill it in, never commit it
edit radar/profile.md                          # who you are + your stack: drives the build ideas

set -a; . ./my.env; set +a
python3 -m radar.collect            # what each feed gives this week (no LLM, no email)
python3 -m radar.main --dry-run     # prints the email, sends nothing, remembers nothing
python3 -m radar.main               # sends it
```

Weekly: `deploy/` has an example systemd service + timer (own user, read-only system, writes only
its state folder). A cron line works too.

**Podcast transcripts (optional):** without them, podcasts are checked from their show notes. If
you already transcribe episodes into Postgres, set `RADAR_TRANSCRIPTS_DB_URL` and
`RADAR_TRANSCRIPTS_TABLE` (columns `audio_url`, `episode_title`, `transcript`). Use a login that
can only `SELECT` those columns.

## Cost

One model call per transcribed episode plus one for the email: about **$0.25 a week** with
Claude Sonnet 5.5 through OpenRouter (2 podcast episodes, ~80 items). Give the key its own monthly
limit; when it's hit you get the links-only email, not a bill.

## Tests

```bash
python3 -m pytest -q                       # 83 tests, no network, no keys
ruff check . && ruff format --check .
```

The tests cover the honesty rules directly: an invented item number is dropped, a model-written
URL is stripped, a quote not in the transcript is rejected, a podcast can't back a podcast, the
credit limit gives a links-only email, an XML bomb is refused, the key and SMTP password never
appear in an error.

## License

MIT. Built by [Lubo Bali](https://lubobali.com).

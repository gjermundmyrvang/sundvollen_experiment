# Energy Reflection Prototype

A small experimental chatbot interface built to study how different ways of
representing the energy cost of a chatbot interaction shape user reflection.

[Jump to installation guide](#setup)

## Background

This prototype is part of a master's thesis project (Design, Use and
Interaction, University of Oslo) investigating how visual and tangible
interface design can foster reflexivity around everyday generative AI use.

It builds directly on three prior studies:

- Ren et al. (2026), _EcoChat Probe_ &rarr; a 4-week field deployment of a
  ChatGPT browser extension providing real-time carbon-emission feedback. [Read the research paper](10.1145/3805689.3812368).
- Patkar et al. (2026) &rarr; a study of UI interventions (mode-switching,
  per-response feedback, dashboards) for sustainable LLM chatbot use. [Read the research paper](10.48550/arXiv.2606.10861)
- Grönewald et al. (2023) &rarr; a study comparing persuasive vs. situated
  UI interventions in a washing-machine interface. [Read The Paper](10.1145/3544548.3581150).

These studies show that raw informational feedback increases awareness but
rarely produces durable understanding or behavior change, while
choice-structuring interventions tend to be more effective. None of them,
however, isolate _representation format_ (a raw number vs. a concrete
visual/spatial equivalent) as a controlled variable &rarr; this prototype does.

## What it does

Visitors interact with a real chatbot (via the OpenAI API) on a short,
familiar task, with resource use tracked live using
[EcoLogits](https://github.com/mlco2/ecologits). After the interaction,
they:

1. Guess the energy cost of their conversation before seeing the real value.
2. See the actual cost &rarr; shown either as a plain number (**abstract**
   condition) or as a rendered visual/spatial representation (**concrete**
   condition).
3. Select which kind of reaction the reveal produced (e.g. surprise, doubt,
   curiosity, guilt).
4. Write a short open reflection.

Two versions of the app run side by side, differing _only_ in how the
energy cost is revealed. All other elements (task, flow, underlying data)
are identical.

## Why

The goal is not to measure behavior change &rarr; a few minutes of interaction
isn't enough for that, and prior work suggests it's unlikely regardless.
Instead, this pilot measures **reflection**: whether and how representation
format changes understanding (guess accuracy), interpretation (reaction
type), and articulated responsibility (open reflection), as a first,
controlled step toward a later comparison between digital and physical
exhibition formats.

## Setup

1. Clone the repo:

```bash
git clone https://github.com/gjermundmyrvang/sundvollen_experiment.git
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy the secrets template and fill in your own API key:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `secrets.toml` and set:

- `OPEN_AI_TEST_KEY` — your OpenAI API key
- `CONDITION` — `"abstract"` or `"concrete"`, depending on which version of the study this instance should run

4. Run the app:

```bash
make experiement
```

or

```bash
streamlit run app.py
```

## Running both conditions

To run the abstract and concrete conditions side by side (e.g. on two
laptops at an event), clone the repo twice (or run two separate local
copies), and set a different `CONDITION` value in each instance's
`secrets.toml`.

## Optional: shared live totals (Supabase)

This is a personal addition used for a specific event deployment and is
not required to run the core experiment. If you want to enable it:

pip install -r requirements-optional.txt

Then add to your `secrets.toml`:

SUPABASE_URL = "..."
SUPABASE_KEY = "..."

Without these, the app runs normally and simply skips the shared-total update.

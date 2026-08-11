"""PaperMind — ask a question, see the answer and the papers behind it.

Run:  uv run streamlit run ui/Home.py

Two things this UI does that most AI demos do not: it shows what the system
consulted even when it declines to answer, and it shows the numbers behind every
answer — which papers, how close, which model, how long. Both are free here,
because the API already returns all of it.
"""

import re

import api_client as api
import streamlit as st

# Written out rather than derived. The first version built each label from the
# question's second word and produced buttons reading "can", "did", "do" — which
# rendered perfectly and meant nothing.
EXAMPLES = [
    ("inference privacy", "how can learned noise protect private data sent to a cloud service?"),
    ("visual SLAM", "why did keyframe-based monocular SLAM replace filter-based approaches?"),
    ("LLM agents", "how do large language models behave as agents in role-playing games?"),
    ("traffic forecasting", "how are graph convolutional networks used to forecast traffic?"),
    ("unanswerable", "who won the 2018 FIFA World Cup?"),
]

st.set_page_config(page_title="PaperMind", page_icon="📄", layout="centered")


def link_citations(answer: str, sources: list[dict]) -> str:
    """Turn `[1]` in the prose into a link to that paper.

    The API returns `marker` per source precisely so this needs no parsing of the
    answer text beyond a substitution — the mapping was decided server-side, where
    it can be tested.
    """
    by_marker = {s["marker"]: s["url"] for s in sources}
    return re.sub(
        r"\[(\d+)\]",
        lambda m: f"[[{m.group(1)}]]({by_marker[int(m.group(1))]})"
        if int(m.group(1)) in by_marker
        else m.group(0),
        answer,
    )


st.title("📄 PaperMind")
st.caption("Questions about AI research, answered from arXiv abstracts — with the papers.")

with st.sidebar:
    st.subheader("Corpus")
    try:
        h = api.health()
        st.metric("Papers", f"{h['papers']:,}")
        st.caption(f"embedding · `{h['embedding_model']}`")
        st.caption(f"generation · `{h['generation_model']}`")
        if not h["llm_reachable"]:
            st.warning("The language model is unreachable — retrieval works, answers will not.")
    except api.ApiError as exc:
        st.error(str(exc))

    st.subheader("Retrieval")
    k = st.slider("Papers consulted", 1, 10, 5, help="How many abstracts go into the prompt")
    st.caption(
        "Measured: hit-rate 88% at k=1, 92% at k=3-5, 100% at k=10. "
        "In the prompt each paper costs about 300 tokens."
    )

question = st.text_input("Ask a question", placeholder=EXAMPLES[0][1])

st.caption("or try one:")
cols = st.columns(len(EXAMPLES))
for col, (label, example) in zip(cols, EXAMPLES, strict=True):
    if col.button(label, use_container_width=True, help=example):
        question = example

if question:
    with st.spinner("Searching the corpus and grounding an answer…"):
        try:
            result = api.ask(question, k=k)
        except api.ApiError as exc:
            st.error(str(exc))
            st.stop()

    if result["refused"]:
        # Not an error. The system worked correctly; the corpus simply does not
        # contain the answer, and saying so is the behaviour worth demonstrating.
        st.info(f"**{result['answer']}**")
        st.caption(
            f"{len(result['retrieved'])} papers were consulted and none of them supported "
            "an answer. In a grounded system this is the correct outcome, not a failure."
        )
    else:
        st.markdown(link_citations(result["answer"], result["sources"]))

        if result["sources"]:
            st.subheader("Sources")
            for source in result["sources"]:
                st.markdown(
                    f"**[{source['marker']}]** [{source['title']}]({source['url']})  \n"
                    f"<span style='color:gray'>distance {source['distance']:.3f}</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.warning("The answer cited no sources, so it is not grounded in the corpus.")

    with st.expander(f"All {len(result['retrieved'])} papers consulted"):
        cited = {s["paper_id"] for s in result["sources"]}
        for paper in result["retrieved"]:
            mark = "●" if paper["paper_id"] in cited else "○"
            st.markdown(
                f"{mark} `{paper['distance']:.3f}` [{paper['title']}]({paper['url']})"
            )
        st.caption("● cited in the answer  ○ retrieved but not used")

    a, b, c = st.columns(3)
    a.metric("Latency", f"{result['latency_ms'] / 1000:.1f}s")
    b.metric("Cited", f"{len(result['sources'])}/{len(result['retrieved'])}")
    c.metric("Closest", f"{result['retrieved'][0]['distance']:.3f}")
    st.caption(
        f"Answered by `{result['models']['generation']}` over embeddings from "
        f"`{result['models']['embedding']}`. Runs locally; costs nothing."
    )

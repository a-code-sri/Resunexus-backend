import json
import os
import time
from typing import List, Tuple

from  models.app_models import (
    JDExtractionOutput,
    CVScoreOutput,
)
from langchain_core.messages import (
    SystemMessage,
    HumanMessage
)
from langchain_groq import ChatGroq
llm = ChatGroq(
    model=os.getenv(
        "GROQ_MODEL",
        "llama-3.3-70b-versatile"
    ),
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0
)
MODEL_NAME = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)
async def extract_skills_from_jd(
    jd_text: str,
) -> List[str]:

    system_prompt = (
        "You analyze job descriptions and extract the 8 most important required skills.\n"
        "Skills should be short capability phrases, e.g., 'Python programming', "
        "'Project management', 'Stakeholder communication'.\n"
        "Apart from these 8 skills there will be two additional skills.\n"
        "One of them is exactly : 'Bachelors/Masters degree from premier institute'.\n"
        "The other one is exactly: 'Work experience in premier company in decent job role'.\n"
        "Finally, return exactly 10 unique skills in JSON format ONLY, with no extra text."
    )

    user_prompt = (
        "Here is the full text of a job description:\n"
        "```text\n"
        f"{jd_text}\n"
        "```\n"
        "Extract the 10 most important required skills.\n"
        "Return JSON only."
    )
    structured_llm =structured_llm = llm.with_structured_output(
            JDExtractionOutput  
    )
    result = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

    time.sleep(2)

    return result.skills

def score_cv_against_skills(
    cv_text: str,
    skills: List[str]
) -> Tuple[List[float], float]:

    skills_text = "\n".join(

        f"{i+1}. {s}"

        for i, s in enumerate(skills)
    )

    system_prompt = (
        "You are evaluating a candidate CV against a list of 10 required job skills.\n"
        "For each skill, assign a score from 0 to 10 based on semantic relevance.\n"
        "Consider synonyms, related tools and responsibilities.\n"
        "For skills regarding education institutes/degrees or job roles/company experience make use of web.\n"
        "Return JSON only."
    )

    user_prompt = (
        "Required skills:\n"
        f"{skills_text}\n\n"
        "CV full text:\n"
        "```text\n"
        f"{cv_text}\n"
        "```\n"
        "Return JSON only."
    )

    structured_llm = llm.with_structured_output(
        CVScoreOutput
    )

    result = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
    )

    scores = []

    lookup = {

        s.name: s.score

        for s in result.skills
    }

    for skill in skills:

        scores.append(

            lookup.get(skill, 0.0)
        )

    return scores, result.total_score
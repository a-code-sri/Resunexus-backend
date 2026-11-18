from fastapi import FastAPI, UploadFile
from  processing.pdf_utils import extract_text_from_pdf
from  llm_service.llm import score_cv_against_skills
from  session_service.current_session import current_session
from  models.app_models import ResumeResult
async def process_cv(filename : str ,pdf_bytes: str):
    cv_text = extract_text_from_pdf(pdf_bytes)
    scores, total = score_cv_against_skills(

        cv_text,

        current_session.skills
    )
    result = result = ResumeResult(
        cv_name=filename,
        scores=scores,
        total_score=total,
        cv_text=cv_text
    )

    current_session.results.append(result)
    current_session.processed_files.add(filename)
    current_session.status.processed += 1

    current_session.status.total += 1
    return {

        "message": "CV processed successfully.",

        "results": [result.model_dump(exclude={"cv_text"}) for result in current_session.results]
    }
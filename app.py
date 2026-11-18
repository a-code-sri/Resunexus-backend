import io
import os
import asyncio
import zipfile
import logging
from io import BytesIO

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import Depends

from openpyxl import Workbook

from contextlib import asynccontextmanager

from  database_service.database import (
    connect_database,
    close_database
)

from  session_service.current_session import current_session
from  processing.pdf_utils import extract_text_from_document
from  llm_service.llm import (
    extract_skills_from_jd,
    score_cv_for_criterion,
)
from  models.app_models import CriterionRequest
from  processing.file_processing import process_cv

from  routes.auth_routes import router as auth_router
from  database_service.authentication.auth_dependency import get_current_user
from  database_service.session_sync import (
    sync_session_to_database,
    reset_database_session,
)

from fastapi import BackgroundTasks

load_dotenv()

logging.basicConfig(level=logging.INFO)

# Max parallel LLM calls when re-scoring one criterion across all resumes
CRITERION_CONCURRENCY = 4


def compute_total(scores, weights=None):
    """Weighted average of per-criterion scores (equal weights by default)."""
    if not scores:
        return 0.0
    if weights is None or len(weights) != len(scores) or sum(weights) <= 0:
        return sum(scores) / len(scores)
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


@asynccontextmanager
async def lifespan(app: FastAPI):

    await connect_database()

    yield

    await close_database()


app = FastAPI(
    title="Resume Shortlisting API",
    version="2.0.0",
    lifespan=lifespan
)
app.include_router(auth_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload_jd")
async def upload_jd(
    user = Depends(get_current_user),
    file: UploadFile = File(... , description="The pdf format of Job Description")
):

    if not (file.filename.lower().endswith(".pdf") or file.filename.lower().endswith(".docx")):
        raise HTTPException(
            status_code=400,
            detail="Only PDF Job Descriptions are supported."
        )

    pdf_bytes = await file.read()

    jd_text = extract_text_from_document(file.filename , pdf_bytes)

    if not jd_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Unable to extract text from the uploaded JD."
        )

    skills = await extract_skills_from_jd(
        jd_text
    )

    current_session.jd_name = file.filename
    current_session.skills = skills

    current_session.results.clear()

    current_session.processed_files.clear()

    current_session.status.processed = 0
    current_session.status.total = 0

    return {
        "message": "JD uploaded successfully.",
        "jdName": file.filename,
        "skills": skills
    }


@app.post("/upload_cv")
async def upload_cv(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    file: UploadFile = File(... , description="The CV upload that will be scanned shall either be a .zip containing multiple pdfs or a single .pdf file")
):

    if len(current_session.skills) == 0:
        raise HTTPException(
            status_code=400,
            detail="Please upload a Job Description first."
        )

    filename = file.filename.lower()

    if not (
        filename.endswith(".pdf")
        or
        filename.endswith(".zip")
        or 
        filename.endswith(".docx")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and ZIP resumes are supported."
        )

    if filename.endswith(".zip"):

        zip_bytes = await file.read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:

            pdf_files = [
                f
                for f in zf.infolist()
                if (
                    not f.is_dir()
                    and
                    (f.filename.lower().endswith(".pdf") or f.filename.lower().endswith(".docx"))
                )
            ]

            current_session.status.total = len(pdf_files)
            current_session.status.processed = 0

            for info in pdf_files:

                if info.filename in current_session.processed_files:
                    continue

                pdf_bytes = zf.read(info)

                await process_cv(
                    info.filename,
                    pdf_bytes
                )
                current_session.status.processed += 1
        background_tasks.add_task(sync_session_to_database, current_session.email)
        return {
            "message": "ZIP processed successfully.",
            "processed": current_session.status.processed,
            "results": [
                r.model_dump(exclude={"cv_text"})
                for r in current_session.results
            ]
        }

    if file.filename in current_session.processed_files:

        raise HTTPException(
            status_code=409,
            detail=f"{file.filename} has already been processed."
        )

    pdf_bytes = await file.read()

    current_session.status.total = 1
    current_session.status.processed = 0

    await process_cv(
        file.filename,
        pdf_bytes
    )
    background_tasks.add_task(sync_session_to_database, current_session.email)
    return {
        "message": "Resume processed successfully.",
        "results": [
            r.model_dump(exclude={"cv_text"})
            for r in current_session.results
        ]
    }



@app.get("/status")
def get_status(user = Depends(get_current_user)):

    return current_session.status.model_dump()



@app.get("/results")
def get_results(user = Depends(get_current_user)):

    sorted_results = sorted(
        current_session.results,
        key=lambda x: x.total_score,
        reverse=True
    )

    return {

        "jdName": current_session.jd_name,

        "skills": current_session.skills,

        "rows": [
            row.model_dump(exclude={"cv_text"})
            for row in sorted_results
        ]
    }


@app.get("/download")
def download_results(
    weights: str | None = None,
    user=Depends(get_current_user)
):

    parsed_weights = None

    if weights:
        try:
            parsed_weights = [float(w) for w in weights.split(",")]
        except ValueError:
            parsed_weights = None

    if len(current_session.results) == 0:

        raise HTTPException(
            status_code=400,
            detail="No results available."
        )

    workbook = Workbook()

    worksheet = workbook.active

    worksheet.title = "Results"

    worksheet.append(

        ["CV Name"]

        +

        current_session.skills

        +

        ["Total Score"]

    )

    totals = {
        id(r): compute_total(r.scores, parsed_weights)
        for r in current_session.results
    }

    sorted_results = sorted(

        current_session.results,

        key=lambda x: totals[id(x)],

        reverse=True

    )

    for result in sorted_results:

        worksheet.append(

            [result.cv_name]

            +

            result.scores

            +

            [round(totals[id(result)], 2)]

        )

    stream = BytesIO()

    workbook.save(stream)

    stream.seek(0)

    return StreamingResponse(

        stream,

        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

        headers={

            "Content-Disposition":

            "attachment; filename=resume_results.xlsx"

        }

    )



@app.post("/criteria")
async def add_or_change_criterion(
    request: CriterionRequest,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user)
):
    """
    Add a new criterion (index=None) or change an existing one (index=i).
    Only that one criterion is re-evaluated, for every resume currently
    on the leaderboard. All-or-nothing: if any resume fails to score,
    nothing is modified.
    """

    criterion = request.criterion.strip()

    if not criterion:
        raise HTTPException(status_code=400, detail="Criterion cannot be empty.")

    if len(current_session.skills) == 0 or len(current_session.results) == 0:
        raise HTTPException(
            status_code=400,
            detail="Nothing to re-evaluate. Upload a JD and resumes first."
        )

    n = len(current_session.skills)

    if request.index is None:
        index = n
    elif 0 <= request.index < n:
        index = request.index
    else:
        raise HTTPException(status_code=400, detail="Invalid criterion index.")

    for i, existing in enumerate(current_session.skills):
        if i != index and existing.strip().lower() == criterion.lower():
            raise HTTPException(
                status_code=409,
                detail="That criterion already exists."
            )

    missing_text = [
        r.cv_name for r in current_session.results if not r.cv_text.strip()
    ]

    if missing_text:
        raise HTTPException(
            status_code=409,
            detail=(
                "Some resumes were evaluated before re-scoring was supported "
                "and their text is not stored. Reset and re-upload the "
                f"resumes to use this feature: {', '.join(missing_text[:5])}"
            )
        )

    semaphore = asyncio.Semaphore(CRITERION_CONCURRENCY)

    async def score_one(result):

        async with semaphore:

            for attempt in range(3):

                try:
                    return await asyncio.to_thread(
                        score_cv_for_criterion,
                        result.cv_text,
                        criterion
                    )
                except Exception as exc:
                    logging.warning(
                        "Scoring %s failed (attempt %d): %s",
                        result.cv_name, attempt + 1, exc
                    )
                    await asyncio.sleep(2 * (attempt + 1))

        return None

    results_snapshot = list(current_session.results)

    new_scores = await asyncio.gather(
        *[score_one(r) for r in results_snapshot]
    )

    failed = [
        r.cv_name for r, s in zip(results_snapshot, new_scores) if s is None
    ]

    if failed:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not evaluate {len(failed)} resume(s); nothing was "
                "changed. Please try again."
            )
        )

    if index == n:
        current_session.skills.append(criterion)
    else:
        current_session.skills[index] = criterion

    for result, score in zip(results_snapshot, new_scores):

        if index == n:
            result.scores.append(score)
        else:
            result.scores[index] = score

        result.total_score = compute_total(result.scores)

    background_tasks.add_task(sync_session_to_database, current_session.email)

    return {
        "message": "Criterion evaluated successfully.",
        "skills": current_session.skills,
        "rows": [
            r.model_dump(exclude={"cv_text"})
            for r in current_session.results
        ]
    }


@app.delete("/criteria/{index}")
def remove_criterion(
    index: int,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user)
):
    """Remove a criterion. No LLM calls: scores are simply dropped."""

    if not (0 <= index < len(current_session.skills)):
        raise HTTPException(status_code=400, detail="Invalid criterion index.")

    if len(current_session.skills) <= 1:
        raise HTTPException(
            status_code=400,
            detail="At least one criterion must remain."
        )

    current_session.skills.pop(index)

    for result in current_session.results:

        if index < len(result.scores):
            result.scores.pop(index)

        result.total_score = compute_total(result.scores)

    background_tasks.add_task(sync_session_to_database, current_session.email)

    return {
        "message": "Criterion removed.",
        "skills": current_session.skills,
        "rows": [
            r.model_dump(exclude={"cv_text"})
            for r in current_session.results
        ]
    }


@app.post("/reset")
def reset(background_tasks : BackgroundTasks , user = Depends(get_current_user)):

    current_session.jd_name = ""

    current_session.skills.clear()

    current_session.results.clear()

    current_session.processed_files.clear()

    current_session.status.processed = 0

    current_session.status.total = 0
    background_tasks.add_task(reset_database_session,current_session.email)

    return {

        "message": "Session reset successfully."

    }